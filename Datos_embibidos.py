import sys
import json
import msgpack
import base64
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import traceback
import os
import glob
from PIL import Image, ImageTk
import io
import re
import threading
from typing import Optional

# Verificar dependencias
try:
    from kkloader import KoikatuCharaData
except ImportError:
    print("Error: No se puede importar kkloader")
    print("Instala con: pip install kkloader")
    sys.exit(1)

# Lista de IDs de plugin organizados por categorías
PLUGIN_CATEGORIES = {
    "Universal AutoResolver": "com.bepis.sideloader.universalautoresolver",
    "More Accessories": "moreAccessories",
    "KSOX": "KSOX",
    "KCOX": "KCOX",
    "Become Trap": "marco.becometrap",
    "Hair Accessory Customizer": "com.deathweasel.bepinex.hairaccessorycustomizer",
    "Invisible Body": "KK_InvisibleBody",
    "Material Editor": "com.deathweasel.bepinex.materialeditor",
    "Push Up": "com.deathweasel.bepinex.pushup",
    "Studio Colliders": "com.deathweasel.bepinex.studiocolliders",
    "Uncensor Selector": "com.deathweasel.bepinex.uncensorselector",
    "ABM Data": "KKABMPlugin.ABMData",
    "Pregnancy": "KK_Pregnancy",
    "Author Data": "marco.authordata",
    "Skin Effects": "Marco.SkinEffects",
}

def unpack_msgpack(data_bytes):
    """Intenta deserializar MessagePack; si falla, devuelve bytes crudos."""
    try:
        return msgpack.unpackb(data_bytes, raw=False)
    except (msgpack.exceptions.ExtraData, 
            msgpack.exceptions.InvalidData,
            msgpack.exceptions.OutOfRange,
            ValueError) as e:
        return data_bytes
    except Exception as e:
        return data_bytes

def bytes_to_base64(data_bytes):
    """Convierte bytes a base64 string."""
    try:
        return base64.b64encode(data_bytes).decode('ascii')
    except Exception as e:
        return str(data_bytes)

def make_serializable(obj):
    """Convierte recursivamente estructuras con bytes en representaciones serializables."""
    if isinstance(obj, (bytes, bytearray)):
        return bytes_to_base64(obj)
    elif isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [make_serializable(i) for i in obj]
    elif isinstance(obj, set):
        return list(make_serializable(i) for i in obj)
    else:
        return obj

def extraer_segunda_imagen_embebida(ruta_archivo: str) -> Optional[Image.Image]:
    """Extrae la segunda imagen embebida del archivo PNG"""
    try:
        with open(ruta_archivo, "rb") as f:
            data = f.read()
        
        # Buscar patrones de imágenes
        patron_png = re.compile(b'\x89PNG\r\n\x1a\n.*?\x49\x45\x4e\x44\xae\x42\x60\x82', re.DOTALL)
        patron_jpg = re.compile(b'\xff\xd8.*?\xff\xd9', re.DOTALL)
        
        imagenes_png = [m.group() for m in patron_png.finditer(data)]
        imagenes_jpg = [m.group() for m in patron_jpg.finditer(data)]
        
        # Combinar todas las imágenes encontradas
        todas_imagenes = imagenes_png + imagenes_jpg
        
        if len(todas_imagenes) < 2:
            return None
        
        # Intentar cargar la segunda imagen
        try:
            return Image.open(io.BytesIO(todas_imagenes[1])).convert("RGBA")
        except Exception:
            # Si falla la segunda, probar con las siguientes
            for i in range(2, len(todas_imagenes)):
                try:
                    return Image.open(io.BytesIO(todas_imagenes[i])).convert("RGBA")
                except Exception:
                    continue
            return None
            
    except Exception as e:
        print(f"Error extrayendo imagen embebida: {e}")
        return None

class KoikatuCardBrowser:
    def __init__(self, root):
        self.root = root
        self.root.title("Koikatu Card Browser")
        self.root.geometry("1400x900")
        
        self.current_folder = ""
        self.card_files = []
        self.current_index = 0
        self.current_card_data = None
        self.image_cache = {}
        self.loading = False
        
        self.setup_ui()
        self.bind_keys()
        
    def setup_ui(self):
        """Configura la interfaz de usuario"""
        # Frame principal
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Panel superior - Selección de carpeta y navegación
        top_frame = tk.Frame(main_frame)
        top_frame.pack(fill="x", pady=(0, 5))
        
        # Selección de carpeta
        folder_frame = tk.Frame(top_frame)
        folder_frame.pack(fill="x", pady=(0, 5))
        
        tk.Label(folder_frame, text="Carpeta:").pack(side="left")
        self.folder_var = tk.StringVar()
        tk.Entry(folder_frame, textvariable=self.folder_var, width=80).pack(side="left", padx=5)
        tk.Button(folder_frame, text="Examinar...", command=self.browse_folder).pack(side="left")
        
        # Navegación
        nav_frame = tk.Frame(top_frame)
        nav_frame.pack(fill="x", pady=(5, 0))
        
        tk.Button(nav_frame, text="◀◀ Anterior (Z)", command=self.previous_card).pack(side="left")
        tk.Button(nav_frame, text="▶▶ Siguiente (X)", command=self.next_card).pack(side="left", padx=5)
        
        self.card_info_var = tk.StringVar()
        self.card_info_var.set("No hay cartas cargadas")
        tk.Label(nav_frame, textvariable=self.card_info_var).pack(side="left", padx=10)
        
        # Panel principal dividido
        paned_window = tk.PanedWindow(main_frame, orient="horizontal")
        paned_window.pack(fill="both", expand=True)
        
        # Panel izquierdo - Imágenes
        left_frame = tk.Frame(paned_window)
        paned_window.add(left_frame, width=400)
        
        # Preview de la carta (imagen principal)
        preview_frame = tk.LabelFrame(left_frame, text="Vista Previa (Imagen Principal)", padx=5, pady=5)
        preview_frame.pack(fill="both", expand=True, pady=(0, 5))
        
        self.preview_label = tk.Label(preview_frame, text="No hay imagen", bg="gray90")
        self.preview_label.pack(fill="both", expand=True)
        
        # Segunda imagen embebida
        embedded_frame = tk.LabelFrame(left_frame, text="Segunda Imagen Embebida", padx=5, pady=5)
        embedded_frame.pack(fill="both", expand=True)
        
        self.embedded_image_label = tk.Label(embedded_frame, text="No hay imagen embebida", bg="gray90")
        self.embedded_image_label.pack(fill="both", expand=True)
        
        # Panel derecho - Datos de plugins
        right_frame = tk.Frame(paned_window)
        paned_window.add(right_frame, width=900)
        
        # Notebook para organizar plugins por categorías
        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill="both", expand=True)
        
        # Crear pestañas para cada categoría de plugin
        self.plugin_tabs = {}
        for category, plugin_id in PLUGIN_CATEGORIES.items():
            frame = tk.Frame(self.notebook)
            self.notebook.add(frame, text=category)
            
            # Área de texto para cada plugin
            text_widget = scrolledtext.ScrolledText(frame, wrap=tk.WORD, font=("Consolas", 9))
            text_widget.pack(fill="both", expand=True, padx=5, pady=5)
            
            self.plugin_tabs[plugin_id] = text_widget
        
        # Pestaña adicional para resumen
        summary_frame = tk.Frame(self.notebook)
        self.notebook.add(summary_frame, text="Resumen")
        self.summary_text = scrolledtext.ScrolledText(summary_frame, wrap=tk.WORD, font=("Consolas", 9))
        self.summary_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Barra de estado
        self.status_var = tk.StringVar()
        self.status_var.set("Listo - Selecciona una carpeta para comenzar")
        status_bar = tk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side="bottom", fill="x", pady=(5, 0))
        
        # Botones de guardado
        save_frame = tk.Frame(main_frame)
        save_frame.pack(fill="x", pady=(5, 0))
        
        tk.Button(save_frame, text="Guardar Datos Actuales", command=self.save_current_data).pack(side="left")
        tk.Button(save_frame, text="Exportar Todo", command=self.export_all_data).pack(side="left", padx=5)
    
    def bind_keys(self):
        """Vincula las teclas para navegación"""
        self.root.bind('<KeyPress-z>', lambda e: self.previous_card())
        self.root.bind('<KeyPress-x>', lambda e: self.next_card())
        self.root.bind('<KeyPress-Z>', lambda e: self.previous_card())
        self.root.bind('<KeyPress-X>', lambda e: self.next_card())
        self.root.bind('<Left>', lambda e: self.previous_card())
        self.root.bind('<Right>', lambda e: self.next_card())
        self.root.focus_set()  # Para que las teclas funcionen
    
    def browse_folder(self):
        """Abre diálogo para seleccionar carpeta"""
        folder = filedialog.askdirectory(title="Selecciona carpeta con cartas PNG")
        if folder:
            self.folder_var.set(folder)
            self.load_folder(folder)
    
    def load_folder(self, folder_path):
        """Carga todos los archivos PNG de la carpeta"""
        self.current_folder = folder_path
        self.card_files = glob.glob(os.path.join(folder_path, "*.png"))
        self.card_files.sort()
        self.image_cache.clear()  # Limpiar caché de imágenes
        
        if self.card_files:
            self.current_index = 0
            self.status_var.set(f"Cargadas {len(self.card_files)} cartas")
            self.load_current_card()
        else:
            self.status_var.set("No se encontraron archivos PNG en la carpeta")
            messagebox.showinfo("Sin cartas", "No se encontraron archivos PNG en la carpeta seleccionada.")
    
    def load_current_card(self):
        """Carga y muestra la carta actual"""
        if not self.card_files or self.loading:
            return
        
        self.loading = True
        current_file = self.card_files[self.current_index]
        filename = os.path.basename(current_file)
        
        # Actualizar información de navegación
        self.card_info_var.set(f"Carta {self.current_index + 1} de {len(self.card_files)}: {filename}")
        
        try:
            # Cargar datos de la carta
            self.status_var.set("Cargando carta...")
            self.root.update()
            
            # Cargar con kkloader
            kc = KoikatuCharaData.load(current_file)
            
            # Cargar datos de plugins
            self.load_plugin_data(kc)
            
            # Cargar imágenes en un hilo separado
            threading.Thread(target=self.load_images_threaded, args=(current_file, kc), daemon=True).start()
            
            self.current_card_data = kc
            
        except Exception as e:
            error_msg = f"Error al cargar {filename}: {str(e)}"
            self.status_var.set(error_msg)
            self.clear_all_displays()
            print(f"Error detallado: {traceback.format_exc()}")
        finally:
            self.loading = False
    
    def load_images_threaded(self, current_file, kc):
        """Carga las imágenes en un hilo separado"""
        try:
            filename = os.path.basename(current_file)
            
            # Cargar imagen principal desde kkloader
            img_principal = None
            if hasattr(kc, 'image') and kc.image:
                img_principal = Image.open(io.BytesIO(kc.image))
            
            # Cargar segunda imagen embebida usando la función especializada
            img_embebida = None
            if current_file in self.image_cache:
                img_embebida = self.image_cache[current_file]
            else:
                img_embebida = extraer_segunda_imagen_embebida(current_file)
                if img_embebida:
                    self.image_cache[current_file] = img_embebida
            
            # Actualizar UI en el hilo principal
            self.root.after(0, self.update_images_ui, img_principal, img_embebida, filename)
            
        except Exception as e:
            print(f"Error cargando imágenes: {e}")
            self.root.after(0, self.status_var.set, f"Error cargando imágenes: {e}")
    
    def update_images_ui(self, img_principal, img_embebida, filename):
        """Actualiza las imágenes en la interfaz de usuario"""
        try:
            # Actualizar imagen principal
            if img_principal:
                img_principal_copy = img_principal.copy()
                img_principal_copy.thumbnail((350, 350), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img_principal_copy)
                self.preview_label.configure(image=photo, text="")
                self.preview_label.image = photo  # Mantener referencia
            else:
                self.preview_label.configure(image="", text="No hay imagen principal")
                self.preview_label.image = None
            
            # Actualizar imagen embebida
            if img_embebida:
                img_embebida_copy = img_embebida.copy()
                img_embebida_copy.thumbnail((350, 350), Image.Resampling.LANCZOS)
                photo_embedded = ImageTk.PhotoImage(img_embebida_copy)
                self.embedded_image_label.configure(image=photo_embedded, text="")
                self.embedded_image_label.image = photo_embedded  # Mantener referencia
            else:
                self.embedded_image_label.configure(image="", text="No hay imagen embebida")
                self.embedded_image_label.image = None
            
            self.status_var.set(f"Carta cargada: {filename}")
            
        except Exception as e:
            print(f"Error actualizando UI: {e}")
            self.status_var.set(f"Error actualizando interfaz: {e}")
    
    def load_plugin_data(self, kc):
        """Carga los datos de plugins en las pestañas correspondientes"""
        # Limpiar todas las pestañas
        for text_widget in self.plugin_tabs.values():
            text_widget.delete(1.0, tk.END)
        self.summary_text.delete(1.0, tk.END)
        
        try:
            # Verificar que existe el bloque KKEx
            kkex_block = getattr(kc, "KKEx", None)
            if not kkex_block:
                self.summary_text.insert(tk.END, "No se encontró el bloque KKEx en esta carta.\n")
                return
            
            kkex_data = kkex_block.data
            if not kkex_data:
                self.summary_text.insert(tk.END, "El bloque KKEx está vacío.\n")
                return
            
            # Cargar datos para cada plugin
            found_plugins = []
            summary_info = []
            
            for category, plugin_id in PLUGIN_CATEGORIES.items():
                text_widget = self.plugin_tabs[plugin_id]
                
                if plugin_id in kkex_data:
                    val = kkex_data[plugin_id]
                    
                    # Procesar datos si son bytes
                    if isinstance(val, (bytes, bytearray)):
                        original_val = val
                        val = unpack_msgpack(val)
                        
                        # Mostrar información sobre el procesamiento
                        text_widget.insert(tk.END, f"=== {category} ===\n")
                        text_widget.insert(tk.END, f"Tamaño original: {len(original_val)} bytes\n")
                        text_widget.insert(tk.END, f"Tipo después de unpack: {type(val)}\n\n")
                    
                    # Convertir a formato serializable y mostrar
                    serializable_val = make_serializable(val)
                    json_str = json.dumps(serializable_val, ensure_ascii=False, indent=2)
                    text_widget.insert(tk.END, json_str)
                    
                    found_plugins.append(category)
                    summary_info.append(f"✓ {category}: {len(json_str)} caracteres")
                else:
                    text_widget.insert(tk.END, f"No se encontraron datos para {category}")
                    summary_info.append(f"✗ {category}: No encontrado")
            
            # Actualizar resumen
            self.summary_text.insert(tk.END, f"=== RESUMEN DE PLUGINS ===\n")
            self.summary_text.insert(tk.END, f"Archivo: {os.path.basename(self.card_files[self.current_index])}\n")
            self.summary_text.insert(tk.END, f"Plugins encontrados: {len(found_plugins)}\n")
            self.summary_text.insert(tk.END, f"Plugins activos: {', '.join(found_plugins)}\n\n")
            
            for info in summary_info:
                self.summary_text.insert(tk.END, info + "\n")
                
        except Exception as e:
            error_msg = f"Error al procesar plugins: {str(e)}\n\n{traceback.format_exc()}"
            self.summary_text.insert(tk.END, error_msg)
    
    def clear_all_displays(self):
        """Limpia todas las áreas de visualización"""
        self.preview_label.configure(image="", text="Error al cargar")
        self.embedded_image_label.configure(image="", text="Error al cargar")
        
        for text_widget in self.plugin_tabs.values():
            text_widget.delete(1.0, tk.END)
            text_widget.insert(tk.END, "Error al cargar datos")
        
        self.summary_text.delete(1.0, tk.END)
        self.summary_text.insert(tk.END, "Error al cargar datos")
    
    def previous_card(self):
        """Navega a la carta anterior"""
        if not self.card_files or self.loading:
            return
        
        if self.current_index > 0:
            self.current_index -= 1
        else:
            self.current_index = len(self.card_files) - 1  # Circular
        
        self.load_current_card()
    
    def next_card(self):
        """Navega a la carta siguiente"""
        if not self.card_files or self.loading:
            return
        
        if self.current_index < len(self.card_files) - 1:
            self.current_index += 1
        else:
            self.current_index = 0  # Circular
        
        self.load_current_card()
    
    def save_current_data(self):
        """Guarda los datos de la carta actual"""
        if not self.current_card_data:
            messagebox.showwarning("Sin datos", "No hay datos para guardar.")
            return
        
        filename = os.path.basename(self.card_files[self.current_index])
        default_name = os.path.splitext(filename)[0] + "_data.json"
        
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialvalue=default_name,
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            title="Guardar datos de la carta actual"
        )
        
        if path:
            try:
                # Extraer datos de plugins
                kkex_block = getattr(self.current_card_data, "KKEx", None)
                if kkex_block and kkex_block.data:
                    result = {}
                    for plugin_id in PLUGIN_CATEGORIES.values():
                        if plugin_id in kkex_block.data:
                            val = kkex_block.data[plugin_id]
                            if isinstance(val, (bytes, bytearray)):
                                val = unpack_msgpack(val)
                            result[plugin_id] = val
                    
                    serializable_result = make_serializable(result)
                    
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(serializable_result, f, ensure_ascii=False, indent=2)
                    
                    messagebox.showinfo("Guardado", f"Datos guardados en: {path}")
                    self.status_var.set(f"Datos guardados: {os.path.basename(path)}")
                else:
                    messagebox.showwarning("Sin datos", "No hay datos de plugins para guardar.")
                    
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo guardar:\n{e}")
    
    def export_all_data(self):
        """Exporta datos de todas las cartas"""
        if not self.card_files:
            messagebox.showwarning("Sin cartas", "No hay cartas para exportar.")
            return
        
        folder = filedialog.askdirectory(title="Selecciona carpeta para exportar datos")
        if not folder:
            return
        
        try:
            exported_count = 0
            for i, card_file in enumerate(self.card_files):
                self.status_var.set(f"Exportando {i+1}/{len(self.card_files)}: {os.path.basename(card_file)}")
                self.root.update()
                
                try:
                    kc = KoikatuCharaData.load(card_file)
                    kkex_block = getattr(kc, "KKEx", None)
                    
                    if kkex_block and kkex_block.data:
                        result = {}
                        for plugin_id in PLUGIN_CATEGORIES.values():
                            if plugin_id in kkex_block.data:
                                val = kkex_block.data[plugin_id]
                                if isinstance(val, (bytes, bytearray)):
                                    val = unpack_msgpack(val)
                                result[plugin_id] = val
                        
                        if result:  # Solo guardar si hay datos
                            filename = os.path.basename(card_file)
                            json_filename = os.path.splitext(filename)[0] + "_data.json"
                            json_path = os.path.join(folder, json_filename)
                            
                            serializable_result = make_serializable(result)
                            
                            with open(json_path, "w", encoding="utf-8") as f:
                                json.dump(serializable_result, f, ensure_ascii=False, indent=2)
                            
                            exported_count += 1
                            
                except Exception as e:
                    print(f"Error al exportar {card_file}: {e}")
                    continue
            
            messagebox.showinfo("Exportación completa", f"Se exportaron {exported_count} archivos a {folder}")
            self.status_var.set(f"Exportación completa: {exported_count} archivos")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error durante la exportación:\n{e}")

if __name__ == "__main__":
    # Verificación de versión Python
    if sys.version_info < (3, 8):
        messagebox.showerror("Requisito Python", "¡Necesitas Python 3.8 o superior!")
        sys.exit(1)
    
    try:
        root = tk.Tk()
        app = KoikatuCardBrowser(root)
        root.mainloop()
    except Exception as e:
        print(f"Error fatal: {e}")
        traceback.print_exc()
        sys.exit(1)