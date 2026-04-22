import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import time
from pathlib import Path
import shutil
import logging
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('kksp_converter.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class KKSPConverter:
    def __init__(self):
        self.ventana = tk.Tk()
        self.setup_ui()
        self.carpeta_seleccionada = ""
        self.conversion_en_progreso = False
        
    def setup_ui(self):
        """Configurar la interfaz de usuario"""
        self.ventana.title("Convertidor KKSP → KK v2.0")
        self.ventana.geometry("500x400")
        self.ventana.resizable(True, True)
        
        # Centrar ventana
        self.ventana.update_idletasks()
        x = (self.ventana.winfo_screenwidth() // 2) - (500 // 2)
        y = (self.ventana.winfo_screenheight() // 2) - (400 // 2)
        self.ventana.geometry(f"+{x}+{y}")
        
        # Frame principal
        main_frame = ttk.Frame(self.ventana, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Título
        titulo = ttk.Label(main_frame, text="Convertidor KKSP → KK", 
                          font=('Arial', 16, 'bold'))
        titulo.pack(pady=(0, 20))
        
        # Descripción
        descripcion = ttk.Label(main_frame, 
                               text="Convierte cartas de Koikatsu Sunshine (KKSP) a formato Koikatsu (KK)",
                               font=('Arial', 10))
        descripcion.pack(pady=(0, 20))
        
        # Frame para selección de carpeta
        carpeta_frame = ttk.LabelFrame(main_frame, text="Carpeta de origen", padding="10")
        carpeta_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.label_carpeta = ttk.Label(carpeta_frame, text="Ninguna carpeta seleccionada", 
                                      foreground="gray")
        self.label_carpeta.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.boton_seleccionar = ttk.Button(carpeta_frame, text="Seleccionar carpeta", 
                                          command=self.seleccionar_carpeta)
        self.boton_seleccionar.pack(side=tk.RIGHT, padx=(10, 0))
        
        # Frame para opciones
        opciones_frame = ttk.LabelFrame(main_frame, text="Opciones", padding="10")
        opciones_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.crear_backup = tk.BooleanVar(value=True)
        ttk.Checkbutton(opciones_frame, text="Crear backup antes de convertir", 
                       variable=self.crear_backup).pack(anchor=tk.W)
        
        self.incluir_subcarpetas = tk.BooleanVar(value=False)
        ttk.Checkbutton(opciones_frame, text="Incluir subcarpetas", 
                       variable=self.incluir_subcarpetas).pack(anchor=tk.W)
        
        self.validar_archivos = tk.BooleanVar(value=True)
        ttk.Checkbutton(opciones_frame, text="Validar archivos después de conversión", 
                       variable=self.validar_archivos).pack(anchor=tk.W)
        
        # Frame para botones de acción
        botones_frame = ttk.Frame(main_frame)
        botones_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.boton_convertir = ttk.Button(botones_frame, text="Convertir", 
                                        command=self.iniciar_conversion, 
                                        state=tk.DISABLED)
        self.boton_convertir.pack(side=tk.LEFT, padx=(0, 10))
        
        self.boton_cancelar = ttk.Button(botones_frame, text="Cancelar", 
                                       command=self.cancelar_conversion, 
                                       state=tk.DISABLED)
        self.boton_cancelar.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(botones_frame, text="Abrir Log", 
                  command=self.abrir_log).pack(side=tk.RIGHT)
        
        # Frame para progreso
        progreso_frame = ttk.LabelFrame(main_frame, text="Progreso", padding="10")
        progreso_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.progress_bar = ttk.Progressbar(progreso_frame, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))
        
        self.label_progreso = ttk.Label(progreso_frame, text="Listo para comenzar")
        self.label_progreso.pack()
        
        # Área de texto para resultados
        resultado_frame = ttk.LabelFrame(main_frame, text="Resultados", padding="10")
        resultado_frame.pack(fill=tk.BOTH, expand=True)
        
        # Crear scrollbar para el texto
        scrollbar = ttk.Scrollbar(resultado_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.texto_resultado = tk.Text(resultado_frame, height=8, wrap=tk.WORD, 
                                     yscrollcommand=scrollbar.set)
        self.texto_resultado.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.texto_resultado.yview)
        
        # Configurar el cierre de la aplicación
        self.ventana.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def seleccionar_carpeta(self):
        """Seleccionar carpeta de origen"""
        carpeta = filedialog.askdirectory(title="Selecciona la carpeta con cartas KKSP")
        if carpeta:
            self.carpeta_seleccionada = carpeta
            self.label_carpeta.config(text=f"...{carpeta[-50:]}" if len(carpeta) > 50 else carpeta, 
                                    foreground="black")
            self.boton_convertir.config(state=tk.NORMAL)
            self.log_mensaje(f"Carpeta seleccionada: {carpeta}")
            
    def log_mensaje(self, mensaje):
        """Agregar mensaje al área de texto y al log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        mensaje_completo = f"[{timestamp}] {mensaje}"
        
        self.texto_resultado.insert(tk.END, mensaje_completo + "\n")
        self.texto_resultado.see(tk.END)
        self.ventana.update()
        
        logging.info(mensaje)
        
    def crear_backup_carpeta(self, carpeta):
        """Crear backup de la carpeta"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(carpeta, f"_BACKUP_{timestamp}")
        
        try:
            os.makedirs(backup_path, exist_ok=True)
            archivos_png = [f for f in os.listdir(carpeta) 
                          if f.lower().endswith('.png') and os.path.isfile(os.path.join(carpeta, f))]
            
            for archivo in archivos_png:
                shutil.copy2(os.path.join(carpeta, archivo), 
                           os.path.join(backup_path, archivo))
            
            self.log_mensaje(f"Backup creado en: {backup_path}")
            return True
        except Exception as e:
            self.log_mensaje(f"Error al crear backup: {str(e)}")
            return False
            
    def obtener_archivos_png(self, carpeta):
        """Obtener lista de archivos PNG"""
        archivos = []
        
        if self.incluir_subcarpetas.get():
            for root, dirs, files in os.walk(carpeta):
                for file in files:
                    if file.lower().endswith('.png'):
                        archivos.append(os.path.join(root, file))
        else:
            for archivo in os.listdir(carpeta):
                ruta_completa = os.path.join(carpeta, archivo)
                if archivo.lower().endswith('.png') and os.path.isfile(ruta_completa):
                    archivos.append(ruta_completa)
                    
        return archivos
        
    def validar_conversion(self, ruta_archivo):
        """Validar que la conversión fue exitosa"""
        try:
            with open(ruta_archivo, 'rb') as f:
                data = f.read()
            return b"KoiKatuChara" in data and b"KoiKatuCharaSP" not in data
        except Exception:
            return False
            
    def convertir_cartas_kksp(self):
        """Convertir cartas KKSP a formato KK"""
        try:
            carpeta = self.carpeta_seleccionada
            
            # Crear backup si está habilitado
            if self.crear_backup.get():
                if not self.crear_backup_carpeta(carpeta):
                    messagebox.showerror("Error", "No se pudo crear el backup. Conversión cancelada.")
                    return
                    
            # Crear carpeta de salida
            salida = os.path.join(carpeta, "_KKSP_CONVERTED_")
            os.makedirs(salida, exist_ok=True)
            
            # Obtener archivos
            archivos_png = self.obtener_archivos_png(carpeta)
            
            if not archivos_png:
                self.log_mensaje("No se encontraron archivos PNG en la carpeta seleccionada")
                return
                
            total = len(archivos_png)
            convertidas = 0
            ignoradas = 0
            errores = 0
            
            self.progress_bar.config(maximum=total)
            self.log_mensaje(f"Iniciando conversión de {total} archivos...")
            
            for i, ruta_original in enumerate(archivos_png):
                if not self.conversion_en_progreso:
                    self.log_mensaje("Conversión cancelada por el usuario")
                    break
                    
                archivo = os.path.basename(ruta_original)
                self.label_progreso.config(text=f"Procesando: {archivo}")
                
                try:
                    with open(ruta_original, "rb") as f:
                        data = f.read()
                        
                    if b"KoiKatuCharaSP" in data:
                        # Reemplazo manteniendo longitud (14 bytes)
                        data = data.replace(b"KoiKatuCharaSP", b"KoiKatuChara\x00\x00")
                        
                        # Crear archivo convertido
                        ruta_convertida = os.path.join(salida, f"KK_{archivo}")
                        with open(ruta_convertida, "wb") as f:
                            f.write(data)
                            
                        # Validar conversión si está habilitado
                        if self.validar_archivos.get():
                            if not self.validar_conversion(ruta_convertida):
                                self.log_mensaje(f"⚠️ Error de validación: {archivo}")
                                errores += 1
                                continue
                                
                        self.log_mensaje(f"✅ Convertida: {archivo}")
                        convertidas += 1
                        
                        # Eliminar archivo original después de conversión exitosa
                        os.remove(ruta_original)
                        
                    else:
                        self.log_mensaje(f"⏩ Ignorada (no es KKSP): {archivo}")
                        ignoradas += 1
                        
                except Exception as e:
                    self.log_mensaje(f"❌ Error con {archivo}: {str(e)}")
                    errores += 1
                    
                # Actualizar progreso
                self.progress_bar.config(value=i + 1)
                self.ventana.update()
                
            # Mostrar resumen
            self.mostrar_resumen(total, convertidas, ignoradas, errores, salida)
            
        except Exception as e:
            self.log_mensaje(f"Error crítico: {str(e)}")
            messagebox.showerror("Error", f"Error durante la conversión: {str(e)}")
        finally:
            self.finalizar_conversion()
            
    def mostrar_resumen(self, total, convertidas, ignoradas, errores, salida):
        """Mostrar resumen de la conversión"""
        mensaje = (
            f"🧾 Total archivos procesados: {total}\n"
            f"✅ Cartas convertidas: {convertidas}\n"
            f"⏩ Cartas ignoradas (no eran KKSP): {ignoradas}\n"
            f"❌ Errores: {errores}\n\n"
            f"📂 Las cartas convertidas están en:\n{salida}"
        )
        
        self.log_mensaje("=== RESUMEN DE CONVERSIÓN ===")
        self.log_mensaje(mensaje.replace('\n', ' | '))
        
        messagebox.showinfo("Conversión completa", mensaje)
        
    def iniciar_conversion(self):
        """Iniciar conversión en hilo separado"""
        if not self.carpeta_seleccionada:
            messagebox.showerror("Error", "Por favor selecciona una carpeta primero")
            return
            
        self.conversion_en_progreso = True
        self.boton_convertir.config(state=tk.DISABLED)
        self.boton_cancelar.config(state=tk.NORMAL)
        self.boton_seleccionar.config(state=tk.DISABLED)
        
        # Limpiar área de texto
        self.texto_resultado.delete(1.0, tk.END)
        
        # Iniciar hilo de conversión
        thread = threading.Thread(target=self.convertir_cartas_kksp)
        thread.daemon = True
        thread.start()
        
    def cancelar_conversion(self):
        """Cancelar conversión"""
        self.conversion_en_progreso = False
        self.log_mensaje("Cancelando conversión...")
        
    def finalizar_conversion(self):
        """Finalizar conversión y restaurar UI"""
        self.conversion_en_progreso = False
        self.boton_convertir.config(state=tk.NORMAL)
        self.boton_cancelar.config(state=tk.DISABLED)
        self.boton_seleccionar.config(state=tk.NORMAL)
        self.label_progreso.config(text="Conversión finalizada")
        
    def abrir_log(self):
        """Abrir archivo de log"""
        log_path = "kksp_converter.log"
        if os.path.exists(log_path):
            os.startfile(log_path) if os.name == 'nt' else os.system(f'open {log_path}')
        else:
            messagebox.showinfo("Info", "El archivo de log no existe aún")
            
    def on_closing(self):
        """Manejar cierre de la aplicación"""
        if self.conversion_en_progreso:
            if messagebox.askokcancel("Confirmar", "¿Deseas cancelar la conversión y cerrar la aplicación?"):
                self.conversion_en_progreso = False
                self.ventana.destroy()
        else:
            self.ventana.destroy()
            
    def run(self):
        """Ejecutar la aplicación"""
        self.ventana.mainloop()

if __name__ == "__main__":
    # Habilita impresión UTF-8 si hay consola
    if sys.stdout:
        sys.stdout.reconfigure(encoding='utf-8')
        
    app = KKSPConverter()
    app.run()