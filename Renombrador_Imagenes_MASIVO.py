import os
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from pathlib import Path
from datetime import datetime
import threading

class RenombradorMultimedia:
    def __init__(self, root):
        self.root = root
        self.root.title("Renombrador de Imágenes y Videos por Fecha de Creación")
        self.root.geometry("700x600")
        self.root.resizable(True, True)
        
        # Variables
        self.ruta_seleccionada = tk.StringVar()
        
        # Extensiones soportadas (ampliadas)
        self.extensiones_imagen = {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
            '.webp', '.heic', '.heif', '.svg', '.ico', '.raw', '.cr2',
            '.nef', '.orf', '.sr2', '.psd', '.xcf'
        }
        
        self.extensiones_video = {
            '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm',
            '.m4v', '.mpg', '.mpeg', '.3gp', '.3g2', '.mts', '.m2ts',
            '.vob', '.ogv', '.gifv', '.mxf', '.roq', '.nsv', '.f4v',
            '.f4p', '.f4a', '.f4b'
        }
        
        self.todas_extensiones = self.extensiones_imagen | self.extensiones_video
        
        self.crear_interfaz()
    
    def crear_interfaz(self):
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configurar peso de las filas y columnas
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(3, weight=1)
        
        # Título
        titulo = ttk.Label(main_frame, text="Renombrador de Imágenes y Videos por Fecha de Creación", 
                          font=("Arial", 16, "bold"))
        titulo.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Selección de carpeta
        ttk.Label(main_frame, text="Carpeta Principal:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        entrada_ruta = ttk.Entry(main_frame, textvariable=self.ruta_seleccionada, width=50)
        entrada_ruta.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        btn_examinar = ttk.Button(main_frame, text="Examinar...", command=self.seleccionar_carpeta)
        btn_examinar.grid(row=1, column=2, padx=5, pady=5)
        
        # Botón de renombrar
        self.btn_renombrar = ttk.Button(main_frame, text="Renombrar Archivos", 
                                       command=self.iniciar_renombrado, style="Accent.TButton")
        self.btn_renombrar.grid(row=2, column=0, columnspan=3, pady=20)
        
        # Área de log
        ttk.Label(main_frame, text="Registro de actividad:").grid(row=3, column=0, 
                                                                   columnspan=3, sticky=tk.W, pady=(0, 5))
        
        self.log_text = scrolledtext.ScrolledText(main_frame, height=20, width=80, 
                                                  state='disabled', wrap=tk.WORD)
        self.log_text.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Barra de progreso
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        # Información
        info_text = ("Este programa renombra todas las imágenes y videos en cada subcarpeta\n"
                    "de forma cronológica por FECHA DE CREACIÓN (de más vieja a más nueva).\n"
                    "Soporta: JPG, PNG, GIF, MP4, AVI, MOV, MKV y muchos más formatos.")
        ttk.Label(main_frame, text=info_text, font=("Arial", 9), 
                 foreground="gray").grid(row=6, column=0, columnspan=3, pady=10)
    
    def seleccionar_carpeta(self):
        carpeta = filedialog.askdirectory(title="Selecciona la carpeta principal")
        if carpeta:
            self.ruta_seleccionada.set(carpeta)
            self.agregar_log(f"Carpeta seleccionada: {carpeta}\n")
    
    def agregar_log(self, mensaje):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, mensaje)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.root.update_idletasks()
    
    def iniciar_renombrado(self):
        ruta = self.ruta_seleccionada.get()
        
        if not ruta:
            messagebox.showwarning("Advertencia", "Por favor selecciona una carpeta primero.")
            return
        
        if not os.path.exists(ruta):
            messagebox.showerror("Error", "La carpeta seleccionada no existe.")
            return
        
        # Confirmar acción
        respuesta = messagebox.askyesno("Confirmar", 
                                       "¿Estás seguro de que deseas renombrar los archivos?\n\n"
                                       "Esta acción no se puede deshacer.")
        if not respuesta:
            return
        
        # Limpiar log
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        
        # Ejecutar en un hilo separado para no bloquear la interfaz
        self.btn_renombrar.config(state='disabled')
        self.progress.start()
        
        thread = threading.Thread(target=self.renombrar_archivos, args=(ruta,))
        thread.daemon = True
        thread.start()
    
    def determinar_tipo_archivo(self, extension):
        """Determina si el archivo es imagen o video"""
        ext_lower = extension.lower()
        if ext_lower in self.extensiones_imagen:
            return "imagen"
        elif ext_lower in self.extensiones_video:
            return "video"
        return None
    
    def renombrar_archivos(self, ruta_principal):
        try:
            ruta_principal = Path(ruta_principal)
            
            self.agregar_log("=" * 60 + "\n")
            self.agregar_log("Iniciando proceso de renombrado...\n")
            self.agregar_log("=" * 60 + "\n\n")
            
            # Obtener subcarpetas
            subcarpetas = [d for d in ruta_principal.iterdir() if d.is_dir()]
            
            if not subcarpetas:
                self.agregar_log("❌ No se encontraron subcarpetas en la ruta especificada.\n")
                self.finalizar_proceso()
                return
            
            self.agregar_log(f"📁 Se encontraron {len(subcarpetas)} subcarpetas\n\n")
            
            total_renombradas = 0
            total_imagenes = 0
            total_videos = 0
            
            # Procesar cada subcarpeta
            for idx, subcarpeta in enumerate(subcarpetas, 1):
                self.agregar_log(f"[{idx}/{len(subcarpetas)}] Procesando: {subcarpeta.name}\n")
                
                # Obtener todos los archivos multimedia
                archivos = []
                for archivo in subcarpeta.iterdir():
                    if archivo.is_file() and archivo.suffix.lower() in self.todas_extensiones:
                        fecha_creacion = archivo.stat().st_ctime
                        tipo = self.determinar_tipo_archivo(archivo.suffix)
                        archivos.append((archivo, fecha_creacion, tipo))
                
                if not archivos:
                    self.agregar_log(f"  ⚠️  No se encontraron archivos multimedia\n\n")
                    continue
                
                # Contar tipos
                imagenes_carpeta = sum(1 for a in archivos if a[2] == "imagen")
                videos_carpeta = sum(1 for a in archivos if a[2] == "video")
                
                self.agregar_log(f"  📊 {imagenes_carpeta} imágenes, {videos_carpeta} videos\n")
                
                # Ordenar por fecha de creación (de más vieja a más nueva)
                archivos.sort(key=lambda x: x[1])
                
                # Paso 1: Renombrar temporalmente para evitar conflictos
                temp_nombres = []
                for idx_temp, (archivo_original, fecha, tipo) in enumerate(archivos):
                    extension = archivo_original.suffix
                    temp_nombre = f"___temp_{idx_temp}___{extension}"
                    temp_ruta = archivo_original.parent / temp_nombre
                    
                    try:
                        archivo_original.rename(temp_ruta)
                        temp_nombres.append((temp_ruta, fecha, tipo))
                    except Exception as e:
                        self.agregar_log(f"  ❌ Error temporal en {archivo_original.name}: {e}\n")
                
                # Paso 2: Renombrar con nombres finales separados por tipo
                contador_imagen = 1
                contador_video = 1
                
                for temp_ruta, fecha, tipo in temp_nombres:
                    extension = temp_ruta.suffix
                    
                    if tipo == "imagen":
                        nuevo_nombre = f"Imagen ({contador_imagen}){extension}"
                        contador_imagen += 1
                        total_imagenes += 1
                        icono = "🖼️"
                    else:  # video
                        nuevo_nombre = f"Video ({contador_video}){extension}"
                        contador_video += 1
                        total_videos += 1
                        icono = "🎬"
                    
                    nueva_ruta = temp_ruta.parent / nuevo_nombre
                    
                    try:
                        temp_ruta.rename(nueva_ruta)
                        fecha_str = datetime.fromtimestamp(fecha).strftime('%Y-%m-%d %H:%M:%S')
                        self.agregar_log(f"  {icono} {nuevo_nombre} (Creación: {fecha_str})\n")
                        total_renombradas += 1
                    except Exception as e:
                        self.agregar_log(f"  ❌ Error al renombrar final: {e}\n")
                        # Intentar recuperar el archivo temporal
                        try:
                            nombre_recuperado = f"ERROR_{tipo}_{extension}"
                            temp_ruta.rename(temp_ruta.parent / nombre_recuperado)
                        except:
                            pass
                
                self.agregar_log(f"  ✓ Total en esta carpeta: {contador_imagen - 1} imágenes, {contador_video - 1} videos\n\n")
            
            self.agregar_log("=" * 60 + "\n")
            self.agregar_log(f"✅ ¡Proceso completado!\n")
            self.agregar_log(f"📊 Estadísticas finales:\n")
            self.agregar_log(f"   • Total de archivos renombrados: {total_renombradas}\n")
            self.agregar_log(f"   • Imágenes: {total_imagenes}\n")
            self.agregar_log(f"   • Videos: {total_videos}\n")
            self.agregar_log("=" * 60 + "\n")
            
            messagebox.showinfo("Completado", 
                              f"¡Proceso completado con éxito!\n\n"
                              f"Total de archivos renombrados: {total_renombradas}\n"
                              f"• Imágenes: {total_imagenes}\n"
                              f"• Videos: {total_videos}")
            
        except Exception as e:
            self.agregar_log(f"\n❌ Error general: {e}\n")
            messagebox.showerror("Error", f"Ocurrió un error: {e}")
        
        finally:
            self.finalizar_proceso()
    
    def finalizar_proceso(self):
        self.progress.stop()
        self.btn_renombrar.config(state='normal')


if __name__ == "__main__":
    root = tk.Tk()
    app = RenombradorMultimedia(root)
    root.mainloop()