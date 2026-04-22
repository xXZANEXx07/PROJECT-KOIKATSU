import os
import shutil
import re
import logging
from collections import defaultdict
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
from typing import Dict, List, Tuple

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('koikatsu_grouper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class KoikatsuCardGrouper:
    """Clase principal para agrupar cartas de Koikatsu por nombre base."""
    
    EXTENSION_VALIDA = '.png'
    CARPETA_LOTES = 'Lotes'
    
    def __init__(self, salida_texto: tk.Text, barra_progreso: ttk.Progressbar):
        self.salida_texto = salida_texto
        self.barra_progreso = barra_progreso
        self.total_archivos = 0
        self.procesados = 0
        
    def extraer_nombre_base(self, nombre_archivo: str) -> str:
        """
        Extrae el nombre base de un archivo, removiendo números al final.
        
        Args:
            nombre_archivo: Nombre del archivo con extensión
            
        Returns:
            Nombre base sin números ni extensión
        """
        try:
            nombre_sin_ext = Path(nombre_archivo).stem
            # Patrón mejorado para capturar diferentes formatos de numeración
            patterns = [
                r"^(.*?)(?:\s+\d+)$",           # "nombre 1", "nombre 123"
                r"^(.*?)(?:\s*\(\d+\))$",       # "nombre(1)", "nombre (123)"
                r"^(.*?)(?:\s*-\s*\d+)$",       # "nombre-1", "nombre - 123"
                r"^(.*?)(?:\s*_\d+)$",          # "nombre_1", "nombre_123"
            ]
            
            for pattern in patterns:
                match = re.match(pattern, nombre_sin_ext)
                if match:
                    return match.group(1).strip()
            
            return nombre_sin_ext.strip()
            
        except Exception as e:
            logger.error(f"Error extrayendo nombre base de {nombre_archivo}: {e}")
            return Path(nombre_archivo).stem
    
    def es_archivo_valido(self, archivo: str) -> bool:
        """Verifica si el archivo tiene una extensión válida."""
        return Path(archivo).suffix.lower() == self.EXTENSION_VALIDA
    
    def log_mensaje(self, mensaje: str, nivel: str = "info"):
        """Registra un mensaje tanto en el log como en la interfaz."""
        self.salida_texto.insert(tk.END, f"{mensaje}\n")
        self.salida_texto.see(tk.END)
        self.salida_texto.update()
        
        if nivel == "error":
            logger.error(mensaje)
        elif nivel == "warning":
            logger.warning(mensaje)
        else:
            logger.info(mensaje)
    
    def actualizar_progreso(self):
        """Actualiza la barra de progreso."""
        if self.total_archivos > 0:
            progreso = (self.procesados / self.total_archivos) * 100
            self.barra_progreso["value"] = progreso
            self.barra_progreso.update()
    
    def obtener_nombre_unico(self, ruta_destino: str) -> str:
        """
        Genera un nombre único si el archivo ya existe.
        
        Args:
            ruta_destino: Ruta completa del archivo destino
            
        Returns:
            Ruta con nombre único
        """
        if not os.path.exists(ruta_destino):
            return ruta_destino
        
        directorio = os.path.dirname(ruta_destino)
        nombre_archivo = os.path.basename(ruta_destino)
        nombre_base, extension = os.path.splitext(nombre_archivo)
        
        contador = 1
        while True:
            nuevo_nombre = f"{nombre_base}_duplicate_{contador}{extension}"
            nueva_ruta = os.path.join(directorio, nuevo_nombre)
            if not os.path.exists(nueva_ruta):
                return nueva_ruta
            contador += 1
    
    def agrupar_archivos(self, ruta_base: str) -> bool:
        """
        Agrupa archivos PNG por nombre base.
        
        Args:
            ruta_base: Ruta de la carpeta base
            
        Returns:
            True si se completó exitosamente
        """
        try:
            if not os.path.exists(ruta_base):
                raise FileNotFoundError(f"La ruta {ruta_base} no existe")
            
            self.log_mensaje("🔍 Iniciando búsqueda de archivos PNG...")
            
            # Recopilar archivos
            nombres_dict = defaultdict(list)
            self.total_archivos = 0
            
            ruta_path = Path(ruta_base)
            for archivo_path in ruta_path.rglob("*"):
                if archivo_path.is_file() and self.es_archivo_valido(archivo_path.name):
                    nombre_base = self.extraer_nombre_base(archivo_path.name)
                    nombres_dict[nombre_base].append(str(archivo_path))
                    self.total_archivos += 1
            
            if self.total_archivos == 0:
                self.log_mensaje("⚠️ No se encontraron archivos PNG en la carpeta especificada", "warning")
                return False
            
            self.log_mensaje(f"📊 Se encontraron {self.total_archivos} archivos PNG")
            
            # Crear carpeta de lotes
            carpeta_lotes = os.path.join(ruta_base, self.CARPETA_LOTES)
            os.makedirs(carpeta_lotes, exist_ok=True)
            
            # Procesar grupos
            grupos_procesados = 0
            archivos_movidos = 0
            
            for nombre_base, rutas in nombres_dict.items():
                if len(rutas) > 1:
                    grupos_procesados += 1
                    carpeta_destino = os.path.join(carpeta_lotes, nombre_base)
                    os.makedirs(carpeta_destino, exist_ok=True)
                    
                    self.log_mensaje(f"📂 Procesando grupo '{nombre_base}' ({len(rutas)} archivos)")
                    
                    for ruta_origen in rutas:
                        try:
                            nombre_archivo = os.path.basename(ruta_origen)
                            ruta_destino = os.path.join(carpeta_destino, nombre_archivo)
                            ruta_destino = self.obtener_nombre_unico(ruta_destino)
                            
                            shutil.move(ruta_origen, ruta_destino)
                            
                            nombre_final = os.path.basename(ruta_destino)
                            self.log_mensaje(f"  📦 Movido: {nombre_final}")
                            archivos_movidos += 1
                            
                        except Exception as e:
                            self.log_mensaje(f"  ❌ Error moviendo {os.path.basename(ruta_origen)}: {e}", "error")
                        
                        finally:
                            self.procesados += 1
                            self.actualizar_progreso()
            
            self.log_mensaje(f"✅ Grupos procesados: {grupos_procesados}")
            self.log_mensaje(f"✅ Archivos movidos: {archivos_movidos}")
            
            # Renombrar carpetas con conteo
            self.renombrar_carpetas_con_conteo(carpeta_lotes)
            
            # Ordenar carpetas por conteo
            self.ordenar_carpetas_por_conteo(carpeta_lotes)
            
            self.barra_progreso["value"] = 100
            self.log_mensaje("🎉 ¡Agrupación completada exitosamente!")
            
            return True
            
        except Exception as e:
            self.log_mensaje(f"❌ Error durante la agrupación: {e}", "error")
            return False
    
    def renombrar_carpetas_con_conteo(self, carpeta_lotes: str):
        """Renombra las carpetas agregando el conteo de archivos."""
        self.log_mensaje("🏷️ Renombrando carpetas con conteo...")
        
        try:
            for carpeta in os.listdir(carpeta_lotes):
                ruta_completa = os.path.join(carpeta_lotes, carpeta)
                if not os.path.isdir(ruta_completa):
                    continue
                
                # Contar archivos PNG
                cantidad = sum(1 for f in os.listdir(ruta_completa) 
                             if self.es_archivo_valido(f))
                
                # Remover conteo existente
                nombre_base = re.sub(r"\s*\(\d+\)$", "", carpeta)
                nuevo_nombre = f"{nombre_base} ({cantidad})"
                nueva_ruta = os.path.join(carpeta_lotes, nuevo_nombre)
                
                if ruta_completa != nueva_ruta:
                    # Verificar que el nuevo nombre no existe
                    if os.path.exists(nueva_ruta):
                        contador = 1
                        while True:
                            temp_nombre = f"{nombre_base} ({cantidad})_{contador}"
                            temp_ruta = os.path.join(carpeta_lotes, temp_nombre)
                            if not os.path.exists(temp_ruta):
                                nueva_ruta = temp_ruta
                                nuevo_nombre = temp_nombre
                                break
                            contador += 1
                    
                    os.rename(ruta_completa, nueva_ruta)
                    self.log_mensaje(f"  📁 {carpeta} → {nuevo_nombre}")
                    
        except Exception as e:
            self.log_mensaje(f"❌ Error renombrando carpetas: {e}", "error")
    
    def ordenar_carpetas_por_conteo(self, carpeta_lotes: str):
        """Ordena las carpetas por cantidad de archivos (menor a mayor)."""
        self.log_mensaje("🔢 Ordenando carpetas por cantidad de archivos...")
        
        try:
            carpetas_info = []
            for carpeta in os.listdir(carpeta_lotes):
                ruta_completa = os.path.join(carpeta_lotes, carpeta)
                if not os.path.isdir(ruta_completa):
                    continue
                
                cantidad = sum(1 for f in os.listdir(ruta_completa) 
                             if self.es_archivo_valido(f))
                carpetas_info.append((carpeta, cantidad))
            
            # Ordenar por cantidad (menor a mayor)
            carpetas_info.sort(key=lambda x: x[1])
            
            # Renombrar con prefijo numérico
            for idx, (carpeta, cantidad) in enumerate(carpetas_info, start=1):
                prefijo = f"{idx:03d}_"
                if not carpeta.startswith(prefijo):
                    # Remover prefijo existente si lo hay
                    nombre_sin_prefijo = re.sub(r"^\d{3}_", "", carpeta)
                    nuevo_nombre = prefijo + nombre_sin_prefijo
                    
                    ruta_actual = os.path.join(carpeta_lotes, carpeta)
                    nueva_ruta = os.path.join(carpeta_lotes, nuevo_nombre)
                    
                    if os.path.exists(nueva_ruta):
                        contador = 1
                        while True:
                            temp_nombre = f"{prefijo}{nombre_sin_prefijo}_{contador}"
                            temp_ruta = os.path.join(carpeta_lotes, temp_nombre)
                            if not os.path.exists(temp_ruta):
                                nueva_ruta = temp_ruta
                                nuevo_nombre = temp_nombre
                                break
                            contador += 1
                    
                    os.rename(ruta_actual, nueva_ruta)
                    self.log_mensaje(f"  🔢 {carpeta} → {nuevo_nombre}")
                    
        except Exception as e:
            self.log_mensaje(f"❌ Error ordenando carpetas: {e}", "error")


class KoikatsuGUI:
    """Interfaz gráfica para el agrupador de cartas Koikatsu."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.ruta_var = tk.StringVar()
        self.grouper = None
        self.setup_ui()
    
    def setup_ui(self):
        """Configura la interfaz de usuario."""
        self.root.title("Agrupar cartas Koikatsu - Versión mejorada")
        self.root.geometry("700x500")
        self.root.resizable(True, True)
        
        # Configurar el estilo
        self.root.configure(bg='#f0f0f0')
        
        # Frame superior para selección de carpeta
        frame_superior = tk.Frame(self.root, bg='#f0f0f0')
        frame_superior.pack(pady=15, padx=10, fill='x')
        
        tk.Label(frame_superior, text="Ruta de las cartas:", 
                font=('Arial', 10, 'bold'), bg='#f0f0f0').grid(row=0, column=0, padx=5, sticky="w")
        
        entry_ruta = tk.Entry(frame_superior, textvariable=self.ruta_var, 
                             width=60, font=('Arial', 9))
        entry_ruta.grid(row=1, column=0, padx=5, sticky="ew")
        
        btn_buscar = tk.Button(frame_superior, text="Buscar...", 
                              command=self.seleccionar_carpeta,
                              bg='#2196F3', fg='white', font=('Arial', 9, 'bold'))
        btn_buscar.grid(row=1, column=1, padx=5)
        
        frame_superior.columnconfigure(0, weight=1)
        
        # Botón de inicio
        btn_iniciar = tk.Button(self.root, text="🚀 Iniciar agrupación", 
                               command=self.iniciar_agrupacion,
                               bg="#4CAF50", fg="white", 
                               font=('Arial', 11, 'bold'), height=2)
        btn_iniciar.pack(pady=10)
        
        # Barra de progreso
        self.barra_progreso = ttk.Progressbar(self.root, orient="horizontal", 
                                             length=500, mode="determinate")
        self.barra_progreso.pack(pady=5)
        
        # Área de texto para salida
        frame_texto = tk.Frame(self.root)
        frame_texto.pack(padx=10, pady=10, fill='both', expand=True)
        
        self.salida_texto = tk.Text(frame_texto, height=18, width=85, 
                                   font=('Consolas', 9), wrap='word')
        
        # Scrollbar para el área de texto
        scrollbar = tk.Scrollbar(frame_texto, orient="vertical", 
                                command=self.salida_texto.yview)
        self.salida_texto.configure(yscrollcommand=scrollbar.set)
        
        self.salida_texto.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Mensaje inicial
        self.salida_texto.insert(tk.END, "🎮 Bienvenido al Agrupador de Cartas Koikatsu\n")
        self.salida_texto.insert(tk.END, "📋 Selecciona una carpeta y presiona 'Iniciar agrupación'\n")
        self.salida_texto.insert(tk.END, "🔍 Solo se procesarán archivos .png\n")
        self.salida_texto.insert(tk.END, "="*60 + "\n\n")
    
    def seleccionar_carpeta(self):
        """Abre el diálogo para seleccionar carpeta."""
        carpeta = filedialog.askdirectory(title="Selecciona la carpeta con las cartas")
        if carpeta:
            self.ruta_var.set(carpeta)
            self.salida_texto.insert(tk.END, f"📁 Carpeta seleccionada: {carpeta}\n\n")
            self.salida_texto.see(tk.END)
    
    def iniciar_agrupacion(self):
        """Inicia el proceso de agrupación."""
        ruta = self.ruta_var.get().strip()
        
        if not ruta:
            messagebox.showerror("Error", "Por favor selecciona una carpeta.")
            return
        
        if not os.path.exists(ruta):
            messagebox.showerror("Error", "La carpeta seleccionada no existe.")
            return
        
        # Limpiar área de texto y reiniciar progreso
        self.salida_texto.delete(1.0, tk.END)
        self.barra_progreso["value"] = 0
        
        # Crear instancia del agrupador
        self.grouper = KoikatsuCardGrouper(self.salida_texto, self.barra_progreso)
        
        # Ejecutar agrupación
        try:
            exito = self.grouper.agrupar_archivos(ruta)
            if exito:
                messagebox.showinfo("¡Completado!", "✅ Agrupación completada exitosamente.")
            else:
                messagebox.showwarning("Atención", "⚠️ La agrupación se completó con advertencias.")
        except Exception as e:
            messagebox.showerror("Error", f"❌ Error durante la agrupación: {str(e)}")
            logger.error(f"Error en iniciar_agrupacion: {e}")
    
    def ejecutar(self):
        """Ejecuta la aplicación."""
        self.root.mainloop()


# Función principal para mantener compatibilidad con el código original
def main():
    """Función principal de la aplicación."""
    try:
        app = KoikatsuGUI()
        app.ejecutar()
    except Exception as e:
        print(f"Error crítico: {e}")
        logger.error(f"Error crítico en main: {e}")


if __name__ == "__main__":
    main()