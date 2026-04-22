import os
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import threading
import re
from datetime import datetime

class RenombradorArchivos:
    def __init__(self, root):
        self.root = root
        self.configurar_ventana()
        self.crear_variables()
        self.crear_interfaz()
        self.archivos_preview = []
        
    def configurar_ventana(self):
        self.root.title("Renombrador de Archivos Masivo v2.0")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)
        
        # Configurar el estilo
        style = ttk.Style()
        style.theme_use('clam')
        
    def crear_variables(self):
        self.ruta_var = tk.StringVar()
        self.prefijo_var = tk.StringVar(value="Scene_1")
        self.inicio_var = tk.StringVar(value="1")
        self.filtro_var = tk.StringVar(value="*")
        self.patron_var = tk.StringVar()
        self.mantener_extension_var = tk.BooleanVar(value=True)
        self.incluir_fecha_var = tk.BooleanVar(value=False)
        self.modo_var = tk.StringVar(value="secuencial")
        
    def crear_interfaz(self):
        # Frame principal con scroll
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Notebook para pestañas
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Pestaña de configuración
        config_frame = ttk.Frame(notebook)
        notebook.add(config_frame, text="Configuración")
        
        # Pestaña de vista previa
        preview_frame = ttk.Frame(notebook)
        notebook.add(preview_frame, text="Vista Previa")
        
        # Pestaña de resultado
        result_frame = ttk.Frame(notebook)
        notebook.add(result_frame, text="Resultado")
        
        self.crear_config_tab(config_frame)
        self.crear_preview_tab(preview_frame)
        self.crear_result_tab(result_frame)
        
    def crear_config_tab(self, parent):
        # Frame de selección de carpeta
        carpeta_frame = ttk.LabelFrame(parent, text="Selección de Carpeta", padding="10")
        carpeta_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(carpeta_frame, text="Carpeta:").grid(row=0, column=0, padx=5, sticky="e")
        self.entry_carpeta = ttk.Entry(carpeta_frame, textvariable=self.ruta_var, width=50)
        self.entry_carpeta.grid(row=0, column=1, padx=5)
        ttk.Button(carpeta_frame, text="Buscar...", command=self.seleccionar_carpeta).grid(row=0, column=2, padx=5)
        
        # Frame de filtros
        filtros_frame = ttk.LabelFrame(parent, text="Filtros", padding="10")
        filtros_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(filtros_frame, text="Extensiones:").grid(row=0, column=0, padx=5, sticky="e")
        self.combo_filtro = ttk.Combobox(filtros_frame, textvariable=self.filtro_var, 
                                        values=["*", "*.jpg", "*.png", "*.pdf", "*.txt", "*.mp4", "*.avi"])
        self.combo_filtro.grid(row=0, column=1, padx=5, sticky="w")
        ttk.Label(filtros_frame, text="(* = todos los archivos)").grid(row=0, column=2, padx=5, sticky="w")
        
        # Frame de renombrado
        renombrado_frame = ttk.LabelFrame(parent, text="Configuración de Renombrado", padding="10")
        renombrado_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Modo de renombrado
        ttk.Label(renombrado_frame, text="Modo:").grid(row=0, column=0, padx=5, sticky="e")
        modo_frame = ttk.Frame(renombrado_frame)
        modo_frame.grid(row=0, column=1, columnspan=2, padx=5, sticky="w")
        
        ttk.Radiobutton(modo_frame, text="Secuencial", variable=self.modo_var, 
                       value="secuencial", command=self.cambiar_modo).pack(side=tk.LEFT)
        ttk.Radiobutton(modo_frame, text="Patrón personalizado", variable=self.modo_var, 
                       value="patron", command=self.cambiar_modo).pack(side=tk.LEFT, padx=(10, 0))
        
        # Configuración secuencial
        self.secuencial_frame = ttk.Frame(renombrado_frame)
        self.secuencial_frame.grid(row=1, column=0, columnspan=3, pady=10, sticky="ew")
        
        ttk.Label(self.secuencial_frame, text="Prefijo:").grid(row=0, column=0, padx=5, sticky="e")
        ttk.Entry(self.secuencial_frame, textvariable=self.prefijo_var, width=30).grid(row=0, column=1, padx=5)
        
        ttk.Label(self.secuencial_frame, text="Comenzar en:").grid(row=0, column=2, padx=5, sticky="e")
        ttk.Entry(self.secuencial_frame, textvariable=self.inicio_var, width=10).grid(row=0, column=3, padx=5)
        
        # Configuración de patrón
        self.patron_frame = ttk.Frame(renombrado_frame)
        self.patron_frame.grid(row=2, column=0, columnspan=3, pady=10, sticky="ew")
        
        ttk.Label(self.patron_frame, text="Patrón:").grid(row=0, column=0, padx=5, sticky="e")
        ttk.Entry(self.patron_frame, textvariable=self.patron_var, width=40).grid(row=0, column=1, padx=5)
        ttk.Label(self.patron_frame, text="Ejemplo: IMG_{fecha}_{contador:03d}").grid(row=0, column=2, padx=5, sticky="w")
        
        # Opciones adicionales
        opciones_frame = ttk.LabelFrame(parent, text="Opciones Adicionales", padding="10")
        opciones_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Checkbutton(opciones_frame, text="Mantener extensión original", 
                       variable=self.mantener_extension_var).pack(anchor="w")
        ttk.Checkbutton(opciones_frame, text="Incluir fecha actual", 
                       variable=self.incluir_fecha_var).pack(anchor="w")
        
        # Botones
        botones_frame = ttk.Frame(parent)
        botones_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(botones_frame, text="Vista Previa", command=self.generar_preview).pack(side=tk.LEFT, padx=5)
        ttk.Button(botones_frame, text="Renombrar", command=self.iniciar_proceso, 
                  style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(botones_frame, text="Deshacer", command=self.deshacer_cambios).pack(side=tk.LEFT, padx=5)
        
        self.cambiar_modo()
        
    def crear_preview_tab(self, parent):
        # Frame con scrollbar
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Treeview para mostrar vista previa
        self.tree_preview = ttk.Treeview(parent, columns=("original", "nuevo"), show="headings", height=15)
        self.tree_preview.heading("original", text="Nombre Original")
        self.tree_preview.heading("nuevo", text="Nombre Nuevo")
        self.tree_preview.column("original", width=300)
        self.tree_preview.column("nuevo", width=300)
        
        # Scrollbar para el treeview
        scrollbar_tree = ttk.Scrollbar(parent, orient="vertical", command=self.tree_preview.yview)
        self.tree_preview.configure(yscrollcommand=scrollbar_tree.set)
        
        self.tree_preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_tree.pack(side=tk.RIGHT, fill=tk.Y)
        
    def crear_result_tab(self, parent):
        # Barra de progreso
        self.barra = ttk.Progressbar(parent, orient="horizontal", length=400, mode="determinate")
        self.barra.pack(pady=10)
        
        # Etiqueta de estado
        self.estado_label = ttk.Label(parent, text="Listo para procesar")
        self.estado_label.pack(pady=5)
        
        # Área de texto para resultados
        text_frame = ttk.Frame(parent)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.salida_texto = tk.Text(text_frame, height=15, width=80)
        scrollbar_text = ttk.Scrollbar(text_frame, orient="vertical", command=self.salida_texto.yview)
        self.salida_texto.configure(yscrollcommand=scrollbar_text.set)
        
        self.salida_texto.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_text.pack(side=tk.RIGHT, fill=tk.Y)
        
    def cambiar_modo(self):
        if self.modo_var.get() == "secuencial":
            self.secuencial_frame.grid()
            self.patron_frame.grid_remove()
        else:
            self.secuencial_frame.grid_remove()
            self.patron_frame.grid()
            
    def seleccionar_carpeta(self):
        carpeta = filedialog.askdirectory(title="Selecciona la carpeta")
        if carpeta:
            self.ruta_var.set(carpeta)
            
    def obtener_archivos(self):
        carpeta = self.ruta_var.get()
        filtro = self.filtro_var.get()
        
        if not carpeta or not os.path.exists(carpeta):
            return []
            
        try:
            archivos = []
            for archivo in os.listdir(carpeta):
                if os.path.isfile(os.path.join(carpeta, archivo)) and not archivo.startswith(('.', '~')):
                    if filtro == "*" or archivo.lower().endswith(filtro.replace("*", "").lower()):
                        archivos.append(archivo)
            return sorted(archivos)
        except Exception as e:
            messagebox.showerror("Error", f"Error al leer la carpeta: {str(e)}")
            return []
            
    def generar_nombres(self, archivos):
        nuevos_nombres = []
        inicio = int(self.inicio_var.get()) if self.inicio_var.get().isdigit() else 1
        
        for i, archivo in enumerate(archivos):
            nombre, extension = os.path.splitext(archivo)
            
            if self.modo_var.get() == "secuencial":
                prefijo = self.prefijo_var.get().strip()
                contador = inicio + i
                nuevo_nombre = f"{prefijo}_{contador:04d}"
            else:
                # Patrón personalizado
                patron = self.patron_var.get()
                fecha_actual = datetime.now().strftime("%Y%m%d")
                contador = inicio + i
                
                nuevo_nombre = patron.replace("{fecha}", fecha_actual)
                nuevo_nombre = nuevo_nombre.replace("{contador}", str(contador))
                nuevo_nombre = nuevo_nombre.replace("{contador:03d}", f"{contador:03d}")
                nuevo_nombre = nuevo_nombre.replace("{contador:04d}", f"{contador:04d}")
                
            if self.incluir_fecha_var.get() and self.modo_var.get() == "secuencial":
                fecha_actual = datetime.now().strftime("%Y%m%d")
                nuevo_nombre = f"{nuevo_nombre}_{fecha_actual}"
                
            if self.mantener_extension_var.get():
                nuevo_nombre += extension
                
            nuevos_nombres.append(nuevo_nombre)
            
        return nuevos_nombres
        
    def generar_preview(self):
        archivos = self.obtener_archivos()
        if not archivos:
            messagebox.showwarning("Sin archivos", "No se encontraron archivos para procesar.")
            return
            
        nuevos_nombres = self.generar_nombres(archivos)
        
        # Limpiar tree
        for item in self.tree_preview.get_children():
            self.tree_preview.delete(item)
            
        # Agregar items al tree
        for original, nuevo in zip(archivos, nuevos_nombres):
            self.tree_preview.insert("", tk.END, values=(original, nuevo))
            
        # Verificar conflictos
        conflictos = self.verificar_conflictos(nuevos_nombres)
        if conflictos:
            messagebox.showwarning("Conflictos detectados", 
                                 f"Se encontraron {len(conflictos)} nombres duplicados. "
                                 "Revisa la configuración.")
            
    def verificar_conflictos(self, nombres):
        return [nombre for nombre in nombres if nombres.count(nombre) > 1]
        
    def validar_configuracion(self):
        if not self.ruta_var.get() or not os.path.exists(self.ruta_var.get()):
            messagebox.showerror("Error", "Selecciona una carpeta válida.")
            return False
            
        if self.modo_var.get() == "secuencial":
            if not self.prefijo_var.get().strip():
                messagebox.showerror("Error", "Ingresa un prefijo válido.")
                return False
        else:
            if not self.patron_var.get().strip():
                messagebox.showerror("Error", "Ingresa un patrón válido.")
                return False
                
        return True
        
    def iniciar_proceso(self):
        if not self.validar_configuracion():
            return
            
        # Ejecutar en hilo separado para no bloquear la UI
        thread = threading.Thread(target=self.renombrar_archivos)
        thread.daemon = True
        thread.start()
        
    def renombrar_archivos(self):
        try:
            archivos = self.obtener_archivos()
            if not archivos:
                messagebox.showwarning("Sin archivos", "No se encontraron archivos para renombrar.")
                return
                
            nuevos_nombres = self.generar_nombres(archivos)
            carpeta = self.ruta_var.get()
            
            # Limpiar área de texto
            self.salida_texto.delete(1.0, tk.END)
            self.barra["value"] = 0
            
            # Guardar lista para deshacer
            self.cambios_realizados = []
            
            total = len(archivos)
            for i, (archivo, nuevo_nombre) in enumerate(zip(archivos, nuevos_nombres)):
                ruta_antigua = os.path.join(carpeta, archivo)
                ruta_nueva = os.path.join(carpeta, nuevo_nombre)
                
                # Verificar si ya existe
                if os.path.exists(ruta_nueva) and ruta_antigua != ruta_nueva:
                    self.salida_texto.insert(tk.END, f"⚠️  Omitido (ya existe): {archivo}\n")
                    continue
                    
                os.rename(ruta_antigua, ruta_nueva)
                self.cambios_realizados.append((ruta_nueva, ruta_antigua))
                
                self.salida_texto.insert(tk.END, f"✅ Renombrado: {archivo} → {nuevo_nombre}\n")
                self.salida_texto.see(tk.END)
                
                # Actualizar barra de progreso
                progreso = ((i + 1) / total) * 100
                self.barra["value"] = progreso
                self.estado_label.config(text=f"Procesando: {i + 1}/{total}")
                self.root.update()
                
            self.estado_label.config(text="✅ Proceso completado")
            messagebox.showinfo("Éxito", "Archivos renombrados correctamente.")
            
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error: {str(e)}")
            self.estado_label.config(text="❌ Error en el proceso")
            
    def deshacer_cambios(self):
        if not hasattr(self, 'cambios_realizados') or not self.cambios_realizados:
            messagebox.showinfo("Información", "No hay cambios para deshacer.")
            return
            
        try:
            for ruta_actual, ruta_original in reversed(self.cambios_realizados):
                if os.path.exists(ruta_actual):
                    os.rename(ruta_actual, ruta_original)
                    
            self.cambios_realizados = []
            messagebox.showinfo("Éxito", "Cambios deshecho correctamente.")
            self.salida_texto.insert(tk.END, "🔄 Cambios deshecho\n")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al deshacer cambios: {str(e)}")

def main():
    root = tk.Tk()
    app = RenombradorArchivos(root)
    root.mainloop()

if __name__ == "__main__":
    main()