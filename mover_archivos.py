import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import threading
import time
from pathlib import Path
import json
from datetime import datetime

class OrganizadorArchivos:
    def __init__(self, root):
        self.root = root
        self.root.title("Organizador de Archivos v2.0")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)
        
        # Variables
        self.carpeta_origen = ""
        self.carpeta_destino = ""
        self.procesando = False
        self.archivos_procesados = 0
        self.total_archivos = 0
        self.config_file = "config.json"
        
        # Cargar configuración previa
        self.cargar_configuracion()
        
        self.crear_interfaz()
        
    def crear_interfaz(self):
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configurar grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Título
        title_label = ttk.Label(main_frame, text="Organizador de Archivos", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Selección de carpetas
        self.crear_seccion_carpetas(main_frame)
        
        # Opciones
        self.crear_seccion_opciones(main_frame)
        
        # Botones de acción
        self.crear_seccion_botones(main_frame)
        
        # Barra de progreso
        self.crear_barra_progreso(main_frame)
        
        # Área de log
        self.crear_seccion_log(main_frame)
        
        # Estadísticas
        self.crear_seccion_estadisticas(main_frame)
        
    def crear_seccion_carpetas(self, parent):
        # Frame para carpetas
        carpetas_frame = ttk.LabelFrame(parent, text="Selección de Carpetas", padding="10")
        carpetas_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        carpetas_frame.columnconfigure(1, weight=1)
        
        # Carpeta origen
        ttk.Label(carpetas_frame, text="Origen:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.label_origen = ttk.Label(carpetas_frame, text="(ninguna seleccionada)", 
                                     relief="sunken", padding="5")
        self.label_origen.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Button(carpetas_frame, text="Seleccionar", 
                  command=self.seleccionar_origen).grid(row=0, column=2)
        
        # Carpeta destino
        ttk.Label(carpetas_frame, text="Destino:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        self.label_destino = ttk.Label(carpetas_frame, text="(ninguna seleccionada)", 
                                      relief="sunken", padding="5")
        self.label_destino.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(0, 5), pady=(5, 0))
        ttk.Button(carpetas_frame, text="Seleccionar", 
                  command=self.seleccionar_destino).grid(row=1, column=2, pady=(5, 0))
        
    def crear_seccion_opciones(self, parent):
        # Frame para opciones
        opciones_frame = ttk.LabelFrame(parent, text="Opciones", padding="10")
        opciones_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Variables para opciones
        self.eliminar_carpetas_vacias = tk.BooleanVar(value=True)
        self.crear_subcarpetas_por_tipo = tk.BooleanVar(value=False)
        self.crear_backup = tk.BooleanVar(value=False)
        self.filtrar_por_fecha = tk.BooleanVar(value=False)
        
        # Checkboxes
        ttk.Checkbutton(opciones_frame, text="Eliminar carpetas vacías", 
                       variable=self.eliminar_carpetas_vacias).grid(row=0, column=0, sticky=tk.W)
        ttk.Checkbutton(opciones_frame, text="Organizar por tipo de archivo", 
                       variable=self.crear_subcarpetas_por_tipo).grid(row=0, column=1, sticky=tk.W)
        ttk.Checkbutton(opciones_frame, text="Crear backup antes de mover", 
                       variable=self.crear_backup).grid(row=1, column=0, sticky=tk.W)
        ttk.Checkbutton(opciones_frame, text="Filtrar archivos por fecha", 
                       variable=self.filtrar_por_fecha).grid(row=1, column=1, sticky=tk.W)
        
    def crear_seccion_botones(self, parent):
        # Frame para botones
        botones_frame = ttk.Frame(parent)
        botones_frame.grid(row=3, column=0, columnspan=3, pady=(0, 10))
        
        # Botones
        self.btn_analizar = ttk.Button(botones_frame, text="Analizar Archivos", 
                                      command=self.analizar_archivos)
        self.btn_analizar.grid(row=0, column=0, padx=(0, 5))
        
        self.btn_iniciar = ttk.Button(botones_frame, text="Iniciar Proceso", 
                                     command=self.iniciar_proceso, state='disabled')
        self.btn_iniciar.grid(row=0, column=1, padx=5)
        
        self.btn_cancelar = ttk.Button(botones_frame, text="Cancelar", 
                                      command=self.cancelar_proceso, state='disabled')
        self.btn_cancelar.grid(row=0, column=2, padx=5)
        
        self.btn_limpiar = ttk.Button(botones_frame, text="Limpiar Log", 
                                     command=self.limpiar_log)
        self.btn_limpiar.grid(row=0, column=3, padx=(5, 0))
        
    def crear_barra_progreso(self, parent):
        # Frame para progreso
        progreso_frame = ttk.Frame(parent)
        progreso_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        progreso_frame.columnconfigure(0, weight=1)
        
        # Barra de progreso
        self.progreso = ttk.Progressbar(progreso_frame, mode='determinate')
        self.progreso.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # Etiqueta de progreso
        self.label_progreso = ttk.Label(progreso_frame, text="Listo para comenzar")
        self.label_progreso.grid(row=1, column=0, pady=(5, 0))
        
    def crear_seccion_log(self, parent):
        # Frame para log
        log_frame = ttk.LabelFrame(parent, text="Log de Actividades", padding="5")
        log_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        # Área de texto con scroll
        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configurar peso de filas para expansión
        parent.rowconfigure(5, weight=1)
        
    def crear_seccion_estadisticas(self, parent):
        # Frame para estadísticas
        stats_frame = ttk.LabelFrame(parent, text="Estadísticas", padding="5")
        stats_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E))
        
        # Labels para estadísticas
        self.label_total = ttk.Label(stats_frame, text="Total archivos: 0")
        self.label_total.grid(row=0, column=0, padx=(0, 20))
        
        self.label_procesados = ttk.Label(stats_frame, text="Procesados: 0")
        self.label_procesados.grid(row=0, column=1, padx=(0, 20))
        
        self.label_tiempo = ttk.Label(stats_frame, text="Tiempo: 0s")
        self.label_tiempo.grid(row=0, column=2)
        
    def seleccionar_origen(self):
        carpeta = filedialog.askdirectory(title="Selecciona carpeta ORIGEN")
        if carpeta:
            self.carpeta_origen = carpeta
            self.label_origen.config(text=carpeta)
            self.checar_botones()
            self.guardar_configuracion()
            
    def seleccionar_destino(self):
        carpeta = filedialog.askdirectory(title="Selecciona carpeta DESTINO")
        if carpeta:
            self.carpeta_destino = carpeta
            self.label_destino.config(text=carpeta)
            self.checar_botones()
            self.guardar_configuracion()
            
    def checar_botones(self):
        if self.carpeta_origen and self.carpeta_destino and not self.procesando:
            self.btn_analizar.config(state='normal')
        else:
            self.btn_analizar.config(state='disabled')
            
    def log(self, texto, tipo="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        iconos = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌", "process": "🔄"}
        icono = iconos.get(tipo, "ℹ️")
        
        mensaje = f"[{timestamp}] {icono} {texto}\n"
        self.log_text.insert(tk.END, mensaje)
        self.log_text.see(tk.END)
        self.root.update_idletasks()
        
    def limpiar_log(self):
        self.log_text.delete(1.0, tk.END)
        
    def analizar_archivos(self):
        if not self.validar_carpetas():
            return
            
        self.log("Analizando archivos en la carpeta origen...", "process")
        
        # Contar archivos
        self.total_archivos = 0
        tipos_archivo = {}
        
        try:
            for root, dirs, files in os.walk(self.carpeta_origen):
                for file in files:
                    self.total_archivos += 1
                    ext = Path(file).suffix.lower()
                    tipos_archivo[ext] = tipos_archivo.get(ext, 0) + 1
                    
            self.label_total.config(text=f"Total archivos: {self.total_archivos}")
            self.log(f"Se encontraron {self.total_archivos} archivos", "success")
            
            # Mostrar tipos de archivo
            if tipos_archivo:
                self.log("Tipos de archivo encontrados:", "info")
                for ext, count in sorted(tipos_archivo.items()):
                    ext_name = ext if ext else "(sin extensión)"
                    self.log(f"  {ext_name}: {count} archivos")
                    
            if self.total_archivos > 0:
                self.btn_iniciar.config(state='normal')
            else:
                self.log("No se encontraron archivos para procesar", "warning")
                
        except Exception as e:
            self.log(f"Error al analizar archivos: {str(e)}", "error")
            
    def validar_carpetas(self):
        if not self.carpeta_origen or not self.carpeta_destino:
            messagebox.showerror("Error", "Debe seleccionar carpetas origen y destino")
            return False
            
        if self.carpeta_origen == self.carpeta_destino:
            messagebox.showerror("Error", "Las carpetas origen y destino no pueden ser la misma")
            return False
            
        if not os.path.exists(self.carpeta_origen):
            messagebox.showerror("Error", "La carpeta origen no existe")
            return False
            
        return True
        
    def iniciar_proceso(self):
        if not self.validar_carpetas():
            return
            
        # Confirmar inicio
        respuesta = messagebox.askyesno(
            "Confirmar", 
            f"¿Está seguro de mover {self.total_archivos} archivos?\n\n"
            f"Origen: {self.carpeta_origen}\n"
            f"Destino: {self.carpeta_destino}"
        )
        
        if not respuesta:
            return
            
        self.procesando = True
        self.archivos_procesados = 0
        self.btn_iniciar.config(state='disabled')
        self.btn_cancelar.config(state='normal')
        self.btn_analizar.config(state='disabled')
        
        # Iniciar proceso en hilo separado
        self.hilo_proceso = threading.Thread(target=self.procesar_archivos, daemon=True)
        self.hilo_proceso.start()
        
    def procesar_archivos(self):
        inicio_tiempo = time.time()
        
        try:
            # Crear carpeta destino
            os.makedirs(self.carpeta_destino, exist_ok=True)
            
            # Crear backup si está habilitado
            if self.crear_backup.get():
                self.crear_backup_archivos()
                
            # Procesar archivos
            self.mover_archivos()
            
            # Limpiar carpetas vacías si está habilitado
            if self.eliminar_carpetas_vacias.get():
                self.eliminar_carpetas_vacias_func()
                
            tiempo_total = time.time() - inicio_tiempo
            self.label_tiempo.config(text=f"Tiempo: {tiempo_total:.1f}s")
            
            if self.procesando:  # Solo si no fue cancelado
                self.log("✅ Proceso completado exitosamente", "success")
                messagebox.showinfo("Completado", "Todos los archivos han sido procesados correctamente")
                
        except Exception as e:
            self.log(f"Error durante el proceso: {str(e)}", "error")
            messagebox.showerror("Error", f"Ocurrió un error:\n{str(e)}")
            
        finally:
            self.procesando = False
            self.btn_iniciar.config(state='normal')
            self.btn_cancelar.config(state='disabled')
            self.btn_analizar.config(state='normal')
            self.progreso['value'] = 0
            self.label_progreso.config(text="Proceso terminado")
            
    def mover_archivos(self):
        # Mapeo de extensiones a carpetas
        tipos_carpeta = {
            'imagenes': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.svg'],
            'documentos': ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt'],
            'videos': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'],
            'audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma'],
            'archivos': ['.zip', '.rar', '.7z', '.tar', '.gz'],
            'ejecutables': ['.exe', '.msi', '.deb', '.rpm', '.dmg']
        }
        
        for root, dirs, files in os.walk(self.carpeta_origen, topdown=False):
            if not self.procesando:
                break
                
            for archivo in files:
                if not self.procesando:
                    break
                    
                try:
                    ruta_origen = os.path.join(root, archivo)
                    
                    # Determinar carpeta destino
                    if self.crear_subcarpetas_por_tipo.get():
                        carpeta_tipo = self.obtener_tipo_archivo(archivo, tipos_carpeta)
                        ruta_destino_carpeta = os.path.join(self.carpeta_destino, carpeta_tipo)
                        os.makedirs(ruta_destino_carpeta, exist_ok=True)
                    else:
                        ruta_destino_carpeta = self.carpeta_destino
                        
                    # Generar nombre único si es necesario
                    ruta_destino = self.generar_nombre_unico(ruta_destino_carpeta, archivo)
                    
                    # Mover archivo
                    shutil.move(ruta_origen, ruta_destino)
                    
                    self.archivos_procesados += 1
                    self.actualizar_progreso()
                    
                    self.log(f"Movido: {archivo} → {os.path.basename(ruta_destino)}", "process")
                    
                except Exception as e:
                    self.log(f"Error moviendo {archivo}: {str(e)}", "error")
                    
    def obtener_tipo_archivo(self, archivo, tipos_carpeta):
        ext = Path(archivo).suffix.lower()
        for tipo, extensiones in tipos_carpeta.items():
            if ext in extensiones:
                return tipo
        return 'otros'
        
    def generar_nombre_unico(self, carpeta, archivo):
        ruta_base = os.path.join(carpeta, archivo)
        if not os.path.exists(ruta_base):
            return ruta_base
            
        nombre, ext = os.path.splitext(archivo)
        contador = 1
        
        while True:
            nuevo_nombre = f"{nombre}_{contador}{ext}"
            nueva_ruta = os.path.join(carpeta, nuevo_nombre)
            if not os.path.exists(nueva_ruta):
                return nueva_ruta
            contador += 1
            
    def eliminar_carpetas_vacias_func(self):
        carpetas_eliminadas = 0
        for root, dirs, files in os.walk(self.carpeta_origen, topdown=False):
            if not self.procesando:
                break
                
            if root != self.carpeta_origen and not os.listdir(root):
                try:
                    os.rmdir(root)
                    carpetas_eliminadas += 1
                    self.log(f"Carpeta vacía eliminada: {root}", "process")
                except Exception as e:
                    self.log(f"Error eliminando carpeta {root}: {str(e)}", "error")
                    
        if carpetas_eliminadas > 0:
            self.log(f"Se eliminaron {carpetas_eliminadas} carpetas vacías", "success")
            
    def crear_backup_archivos(self):
        # Implementar backup básico
        self.log("Creando backup... (funcionalidad básica)", "process")
        # Aquí puedes implementar la lógica de backup según necesites
        
    def actualizar_progreso(self):
        if self.total_archivos > 0:
            porcentaje = (self.archivos_procesados / self.total_archivos) * 100
            self.progreso['value'] = porcentaje
            self.label_progreso.config(text=f"Procesando: {self.archivos_procesados}/{self.total_archivos} ({porcentaje:.1f}%)")
            self.label_procesados.config(text=f"Procesados: {self.archivos_procesados}")
            
    def cancelar_proceso(self):
        if messagebox.askyesno("Cancelar", "¿Está seguro de cancelar el proceso?"):
            self.procesando = False
            self.log("Proceso cancelado por el usuario", "warning")
            
    def cargar_configuracion(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.carpeta_origen = config.get('origen', '')
                    self.carpeta_destino = config.get('destino', '')
        except Exception as e:
            print(f"Error cargando configuración: {e}")
            
    def guardar_configuracion(self):
        try:
            config = {
                'origen': self.carpeta_origen,
                'destino': self.carpeta_destino
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error guardando configuración: {e}")
            
    def on_closing(self):
        if self.procesando:
            if messagebox.askyesno("Salir", "Hay un proceso en curso. ¿Desea salir de todas formas?"):
                self.procesando = False
                self.root.destroy()
        else:
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = OrganizadorArchivos(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()