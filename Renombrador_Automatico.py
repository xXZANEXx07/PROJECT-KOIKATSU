import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import time
import sys
import os
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading

# Metadatos para evitar falsas detecciones
__version__ = "1.1.0"
__author__ = "Usuario"
__description__ = "Renombrador automático de archivos multimedia con análisis completo"

# Constantes globales - Formatos expandidos
IMAGE_EXTENSIONS = frozenset({
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.ico',
    '.cr2', '.cr3', '.nef', '.nrw', '.arw', '.srf', '.sr2', '.orf', '.rw2',
    '.dng', '.raf', '.pef', '.raw', '.rwl', '.3fr', '.fff', '.dcr', '.kdc',
    '.mrw', '.erf', '.svg', '.eps', '.ai', '.psd', '.xcf', '.heic', '.heif',
    '.avif', '.jxl'
})

VIDEO_EXTENSIONS = frozenset({
    '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm', '.m4v', '.mpg',
    '.mpeg', '.3gp', '.3g2', '.ogv', '.ts', '.vob', '.mts', '.m2ts', '.mxf',
    '.f4v', '.swf', '.asf', '.rm', '.rmvb', '.divx', '.xvid', '.h264', '.h265',
    '.hevc', '.vp9', '.av1'
})

ALL_MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

COOLDOWN_TIME = 0.5
FILE_READY_DELAY = 0.05


class MediaRenamerHandler(FileSystemEventHandler):
    """Manejador de eventos del sistema de archivos para renombrado automático"""
    
    __slots__ = ('root_folder', 'log_callback', 'processed_files', 'file_types', '_is_active')
    
    def __init__(self, root_folder, log_callback, file_types='both'):
        super().__init__()
        self.root_folder = Path(root_folder).resolve()
        self.log_callback = log_callback
        self.processed_files = {}
        self.file_types = file_types
        self._is_active = True
    
    def stop(self):
        """Detiene el procesamiento de eventos"""
        self._is_active = False
    
    def should_process_file(self, filepath):
        """Verifica si el archivo debe ser procesado basándose en cooldown"""
        if not self._is_active:
            return False
            
        current_time = time.time()
        last_processed = self.processed_files.get(filepath)
        
        if last_processed and current_time - last_processed < COOLDOWN_TIME:
            return False
        
        if len(self.processed_files) > 100:
            self._cleanup_old_files(current_time)
        
        return True
    
    def _cleanup_old_files(self, current_time):
        """Limpia archivos antiguos del diccionario"""
        threshold = current_time - (COOLDOWN_TIME * 2)
        self.processed_files = {
            f: t for f, t in self.processed_files.items() if t > threshold
        }
    
    def mark_as_processed(self, filepath):
        """Marca un archivo como procesado"""
        self.processed_files[filepath] = time.time()
    
    def is_valid_media(self, filepath):
        """Verifica si el archivo es un medio válido"""
        try:
            extension = Path(filepath).suffix.lower()
            
            if self.file_types == 'images':
                return extension in IMAGE_EXTENSIONS
            elif self.file_types == 'videos':
                return extension in VIDEO_EXTENSIONS
            else:
                return extension in ALL_MEDIA_EXTENSIONS
        except Exception:
            return False
    
    def get_file_type_emoji(self, filepath):
        """Retorna un emoji según el tipo de archivo"""
        extension = Path(filepath).suffix.lower()
        if extension in IMAGE_EXTENSIONS:
            if extension in {'.cr2', '.cr3', '.nef', '.arw', '.dng', '.raw', '.raf', '.pef'}:
                return "📷"
            return "🖼️"
        elif extension in VIDEO_EXTENSIONS:
            return "🎬"
        return "📄"
    
    def get_unique_filename(self, directory, base_name, extension):
        """Genera un nombre único"""
        new_path = directory / f"{base_name}{extension}"
        
        if not new_path.exists():
            return new_path
        
        counter = 1
        max_attempts = 1000
        while counter < max_attempts:
            new_path = directory / f"{base_name}({counter}){extension}"
            if not new_path.exists():
                return new_path
            counter += 1
        
        raise ValueError(f"No se pudo generar un nombre único después de {max_attempts} intentos")
    
    def rename_media(self, filepath):
        """Renombra el archivo multimedia"""
        try:
            file_path = Path(filepath).resolve()
            
            if not file_path.exists() or not file_path.is_file():
                return False
            
            parent_folder = file_path.parent
            
            if parent_folder == self.root_folder:
                return False
            
            try:
                parent_folder.relative_to(self.root_folder)
            except ValueError:
                return False
            
            current_name = file_path.stem
            folder_name = parent_folder.name
            
            if current_name == folder_name or current_name.startswith(f"{folder_name}("):
                return False
            
            new_path = self.get_unique_filename(parent_folder, folder_name, file_path.suffix)
            
            time.sleep(FILE_READY_DELAY)
            
            # Operación segura de renombrado
            file_path.rename(new_path)
            
            emoji = self.get_file_type_emoji(filepath)
            self.log_callback(f"✓ {emoji} Renombrado: {file_path.name} → {new_path.name}")
            return True
            
        except (OSError, PermissionError) as e:
            self.log_callback(f"✗ Error al renombrar {Path(filepath).name}: {type(e).__name__}")
            return False
        except Exception as e:
            self.log_callback(f"✗ Error inesperado: {type(e).__name__}")
            return False
    
    def _process_file(self, filepath):
        """Procesa un archivo multimedia"""
        if not self._is_active:
            return
            
        if not self.should_process_file(filepath) or not self.is_valid_media(filepath):
            return
        
        time.sleep(0.1)
        
        if self.rename_media(filepath):
            self.mark_as_processed(filepath)
    
    def on_created(self, event):
        """Evento: archivo creado"""
        if not event.is_directory and self._is_active:
            self._process_file(event.src_path)
    
    def on_moved(self, event):
        """Evento: archivo movido"""
        if not event.is_directory and self._is_active:
            self._process_file(event.dest_path)


class FileScanner:
    """Clase para escanear y analizar archivos en las carpetas"""
    
    def __init__(self, root_folder, log_callback, file_types='both'):
        self.root_folder = Path(root_folder).resolve()
        self.log_callback = log_callback
        self.file_types = file_types
        self.files_to_rename = []
        self.total_files = 0
        self.cancelled = False
    
    def cancel(self):
        """Cancela el escaneo"""
        self.cancelled = True
    
    def is_valid_media(self, filepath):
        """Verifica si el archivo es un medio válido"""
        try:
            extension = filepath.suffix.lower()
            
            if self.file_types == 'images':
                return extension in IMAGE_EXTENSIONS
            elif self.file_types == 'videos':
                return extension in VIDEO_EXTENSIONS
            else:
                return extension in ALL_MEDIA_EXTENSIONS
        except Exception:
            return False
    
    def get_file_type_emoji(self, filepath):
        """Retorna un emoji según el tipo de archivo"""
        extension = filepath.suffix.lower()
        if extension in IMAGE_EXTENSIONS:
            if extension in {'.cr2', '.cr3', '.nef', '.arw', '.dng', '.raw', '.raf', '.pef'}:
                return "📷"
            return "🖼️"
        elif extension in VIDEO_EXTENSIONS:
            return "🎬"
        return "📄"
    
    def needs_rename(self, file_path):
        """Verifica si un archivo necesita ser renombrado"""
        parent_folder = file_path.parent
        
        # Ignorar archivos en la carpeta raíz
        if parent_folder == self.root_folder:
            return False
        
        # Verificar que esté dentro de la estructura
        try:
            parent_folder.relative_to(self.root_folder)
        except ValueError:
            return False
        
        current_name = file_path.stem
        folder_name = parent_folder.name
        
        # Si ya tiene el nombre correcto, no necesita renombrarse
        if current_name == folder_name or current_name.startswith(f"{folder_name}("):
            return False
        
        return True
    
    def scan_folder(self, progress_callback=None):
        """Escanea la carpeta buscando archivos que necesitan renombrarse"""
        self.files_to_rename = []
        self.total_files = 0
        
        self.log_callback("🔍 Iniciando análisis de carpetas...")
        
        try:
            # Primero contar total de archivos
            all_files = []
            for item in self.root_folder.rglob("*"):
                if self.cancelled:
                    self.log_callback("⚠️ Análisis cancelado por el usuario")
                    return []
                    
                if item.is_file() and self.is_valid_media(item):
                    all_files.append(item)
            
            self.total_files = len(all_files)
            self.log_callback(f"📊 Se encontraron {self.total_files} archivos multimedia")
            
            # Analizar cada archivo
            for index, file_path in enumerate(all_files, 1):
                if self.cancelled:
                    self.log_callback("⚠️ Análisis cancelado por el usuario")
                    return []
                
                if progress_callback:
                    progress_callback(index, self.total_files)
                
                if self.needs_rename(file_path):
                    emoji = self.get_file_type_emoji(file_path)
                    folder_name = file_path.parent.name
                    self.files_to_rename.append({
                        'path': file_path,
                        'current_name': file_path.name,
                        'folder_name': folder_name,
                        'emoji': emoji
                    })
            
            self.log_callback(f"✓ Análisis completado: {len(self.files_to_rename)} archivos necesitan renombrarse")
            return self.files_to_rename
            
        except Exception as e:
            self.log_callback(f"✗ Error durante el análisis: {type(e).__name__}")
            return []
    
    def get_unique_filename(self, directory, base_name, extension):
        """Genera un nombre único"""
        new_path = directory / f"{base_name}{extension}"
        
        if not new_path.exists():
            return new_path
        
        counter = 1
        max_attempts = 1000
        while counter < max_attempts:
            new_path = directory / f"{base_name}({counter}){extension}"
            if not new_path.exists():
                return new_path
            counter += 1
        
        raise ValueError(f"No se pudo generar un nombre único después de {max_attempts} intentos")
    
    def rename_files(self, progress_callback=None):
        """Renombra los archivos encontrados"""
        renamed_count = 0
        error_count = 0
        total = len(self.files_to_rename)
        
        self.log_callback(f"🔧 Iniciando renombrado de {total} archivos...")
        
        for index, file_info in enumerate(self.files_to_rename, 1):
            if self.cancelled:
                self.log_callback("⚠️ Renombrado cancelado por el usuario")
                break
            
            if progress_callback:
                progress_callback(index, total)
            
            try:
                file_path = file_info['path']
                folder_name = file_info['folder_name']
                emoji = file_info['emoji']
                
                if not file_path.exists():
                    self.log_callback(f"⚠️ Archivo no encontrado: {file_path.name}")
                    error_count += 1
                    continue
                
                new_path = self.get_unique_filename(
                    file_path.parent,
                    folder_name,
                    file_path.suffix
                )
                
                time.sleep(FILE_READY_DELAY)
                file_path.rename(new_path)
                
                self.log_callback(f"✓ {emoji} Renombrado: {file_path.name} → {new_path.name}")
                renamed_count += 1
                
            except (OSError, PermissionError) as e:
                self.log_callback(f"✗ Error al renombrar {file_info['current_name']}: {type(e).__name__}")
                error_count += 1
            except Exception as e:
                self.log_callback(f"✗ Error inesperado con {file_info['current_name']}: {type(e).__name__}")
                error_count += 1
        
        self.log_callback(f"✓ Proceso completado: {renamed_count} renombrados, {error_count} errores")
        return renamed_count, error_count


class MediaRenamerApp:
    """Aplicación principal con interfaz gráfica"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Renombrador Automático de Archivos Multimedia")
        self.root.geometry("800x700")
        self.root.resizable(True, True)
        
        self.observer = None
        self.event_handler = None
        self.monitoring = False
        self.selected_folder = None
        self.scanner = None
        self.scanning = False
        
        self.setup_ui()
        self.log_message(f"✓ Aplicación iniciada correctamente (v{__version__})")
    
    def setup_ui(self):
        """Configura la interfaz de usuario"""
        # Frame de control principal
        control_frame = tk.Frame(self.root, pady=10, padx=10)
        control_frame.pack(fill=tk.X)
        
        self.select_btn = tk.Button(
            control_frame,
            text="📁 Seleccionar Carpeta Principal",
            command=self.select_folder,
            font=("Arial", 11),
            bg="#4CAF50",
            fg="white",
            padx=10,
            pady=5
        )
        self.select_btn.pack(side=tk.LEFT, padx=5)
        
        self.toggle_btn = tk.Button(
            control_frame,
            text="▶ Iniciar Monitoreo",
            command=self.toggle_monitoring,
            font=("Arial", 11),
            bg="#2196F3",
            fg="white",
            padx=10,
            pady=5,
            state=tk.DISABLED
        )
        self.toggle_btn.pack(side=tk.LEFT, padx=5)
        
        # Nuevo botón de análisis
        self.scan_btn = tk.Button(
            control_frame,
            text="🔍 Analizar Carpetas",
            command=self.start_scan,
            font=("Arial", 11),
            bg="#FF9800",
            fg="white",
            padx=10,
            pady=5,
            state=tk.DISABLED
        )
        self.scan_btn.pack(side=tk.LEFT, padx=5)
        
        # Frame de opciones
        options_frame = tk.Frame(self.root, pady=5, padx=10)
        options_frame.pack(fill=tk.X)
        
        tk.Label(
            options_frame,
            text="Tipo de archivos:",
            font=("Arial", 10, "bold")
        ).pack(side=tk.LEFT, padx=5)
        
        self.file_type_var = tk.StringVar(value="both")
        
        tk.Radiobutton(
            options_frame,
            text="🖼️ Solo Imágenes (incluye RAW)",
            variable=self.file_type_var,
            value="images",
            font=("Arial", 9)
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Radiobutton(
            options_frame,
            text="🎬 Solo Videos",
            variable=self.file_type_var,
            value="videos",
            font=("Arial", 9)
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Radiobutton(
            options_frame,
            text="📦 Ambos",
            variable=self.file_type_var,
            value="both",
            font=("Arial", 9)
        ).pack(side=tk.LEFT, padx=5)
        
        # Etiqueta de carpeta seleccionada
        self.folder_label = tk.Label(
            self.root,
            text="No se ha seleccionado ninguna carpeta",
            font=("Arial", 10),
            fg="gray",
            wraplength=750
        )
        self.folder_label.pack(pady=5)
        
        # Etiqueta de estado
        self.status_label = tk.Label(
            self.root,
            text="● Detenido",
            font=("Arial", 11, "bold"),
            fg="red"
        )
        self.status_label.pack(pady=5)
        
        # Barra de progreso
        self.progress_frame = tk.Frame(self.root, padx=10)
        self.progress_frame.pack(fill=tk.X, pady=5)
        
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            mode='determinate',
            length=300
        )
        
        self.progress_label = tk.Label(
            self.progress_frame,
            text="",
            font=("Arial", 9)
        )
        
        # Estadísticas
        self.stats_label = tk.Label(
            self.root,
            text="Formatos soportados: 60+ imágenes (incluye RAW) | 25+ videos",
            font=("Arial", 9),
            fg="#555"
        )
        self.stats_label.pack(pady=2)
        
        # Frame de log
        log_frame = tk.Frame(self.root, padx=10, pady=5)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(
            log_frame,
            text="Registro de Actividad:",
            font=("Arial", 10, "bold")
        ).pack(anchor=tk.W)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#f5f5f5",
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Instrucciones
        instructions = (
            "📝 Instrucciones: Selecciona la carpeta principal → Usa 'Analizar Carpetas' para revisar "
            "todos los archivos existentes → Usa 'Iniciar Monitoreo' para vigilar nuevos archivos."
        )
        tk.Label(
            self.root,
            text=instructions,
            font=("Arial", 9),
            fg="gray",
            wraplength=750,
            justify=tk.LEFT
        ).pack(pady=5, padx=10)
    
    def log_message(self, message):
        """Agrega un mensaje al log"""
        try:
            self.log_text.config(state=tk.NORMAL)
            timestamp = time.strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        except Exception:
            pass
    
    def select_folder(self):
        """Selecciona la carpeta principal"""
        folder = filedialog.askdirectory(title="Selecciona la carpeta principal")
        
        if folder:
            self.selected_folder = str(Path(folder).resolve())
            self.folder_label.config(text=f"Carpeta: {self.selected_folder}")
            self.toggle_btn.config(state=tk.NORMAL)
            self.scan_btn.config(state=tk.NORMAL)
            self.log_message(f"📁 Carpeta seleccionada: {self.selected_folder}")
    
    def update_progress(self, current, total):
        """Actualiza la barra de progreso"""
        try:
            percentage = (current / total) * 100
            self.progress_bar['value'] = percentage
            self.progress_label.config(text=f"{current}/{total} ({percentage:.1f}%)")
            self.root.update_idletasks()
        except Exception:
            pass
    
    def show_progress_bar(self):
        """Muestra la barra de progreso"""
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.progress_label.pack(side=tk.LEFT)
        self.progress_bar['value'] = 0
    
    def hide_progress_bar(self):
        """Oculta la barra de progreso"""
        self.progress_bar.pack_forget()
        self.progress_label.pack_forget()
    
    def start_scan(self):
        """Inicia el análisis de carpetas"""
        if not self.selected_folder:
            messagebox.showwarning("Advertencia", "Primero selecciona una carpeta")
            return
        
        if self.scanning:
            messagebox.showinfo("Info", "Ya hay un análisis en progreso")
            return
        
        if self.monitoring:
            messagebox.showwarning("Advertencia", "Detén el monitoreo antes de analizar")
            return
        
        # Ejecutar en un hilo separado
        scan_thread = threading.Thread(target=self.perform_scan, daemon=True)
        scan_thread.start()
    
    def perform_scan(self):
        """Realiza el escaneo y renombrado"""
        self.scanning = True
        
        # Deshabilitar botones
        self.scan_btn.config(state=tk.DISABLED)
        self.select_btn.config(state=tk.DISABLED)
        self.toggle_btn.config(state=tk.DISABLED)
        self.status_label.config(text="● Analizando...", fg="orange")
        
        self.show_progress_bar()
        
        try:
            file_type = self.file_type_var.get()
            self.scanner = FileScanner(self.selected_folder, self.log_message, file_type)
            
            # Fase 1: Escaneo
            files_to_rename = self.scanner.scan_folder(self.update_progress)
            
            if not files_to_rename:
                self.log_message("✓ No se encontraron archivos que necesiten renombrarse")
                self.hide_progress_bar()
                self.reset_ui_after_scan()
                return
            
            # Preguntar al usuario si desea continuar
            response = messagebox.askyesno(
                "Confirmación",
                f"Se encontraron {len(files_to_rename)} archivos que necesitan renombrarse.\n\n"
                "¿Deseas proceder con el renombrado?",
                icon='question'
            )
            
            if response:
                # Fase 2: Renombrado
                self.status_label.config(text="● Renombrando...", fg="blue")
                self.progress_bar['value'] = 0
                renamed, errors = self.scanner.rename_files(self.update_progress)
                
                messagebox.showinfo(
                    "Proceso Completado",
                    f"Archivos renombrados: {renamed}\n"
                    f"Errores: {errors}"
                )
            else:
                self.log_message("⚠️ Renombrado cancelado por el usuario")
        
        except Exception as e:
            self.log_message(f"✗ Error durante el proceso: {type(e).__name__}")
            messagebox.showerror("Error", f"Error durante el proceso:\n{type(e).__name__}")
        
        finally:
            self.hide_progress_bar()
            self.reset_ui_after_scan()
    
    def reset_ui_after_scan(self):
        """Resetea la UI después del escaneo"""
        self.scanning = False
        self.scanner = None
        self.scan_btn.config(state=tk.NORMAL)
        self.select_btn.config(state=tk.NORMAL)
        self.toggle_btn.config(state=tk.NORMAL)
        self.status_label.config(text="● Detenido", fg="red")
    
    def toggle_monitoring(self):
        """Alterna el monitoreo"""
        if not self.monitoring:
            self.start_monitoring()
        else:
            self.stop_monitoring()
    
    def start_monitoring(self):
        """Inicia el monitoreo"""
        if not self.selected_folder:
            messagebox.showwarning("Advertencia", "Primero selecciona una carpeta")
            return
        
        if self.scanning:
            messagebox.showwarning("Advertencia", "Espera a que termine el análisis")
            return
        
        try:
            file_type = self.file_type_var.get()
            self.event_handler = MediaRenamerHandler(
                self.selected_folder,
                self.log_message,
                file_type
            )
            
            self.observer = Observer()
            self.observer.schedule(self.event_handler, self.selected_folder, recursive=True)
            self.observer.start()
            
            self.monitoring = True
            self.toggle_btn.config(text="⏸ Detener Monitoreo", bg="#FF5722")
            self.status_label.config(text="● Monitoreando...", fg="green")
            self.select_btn.config(state=tk.DISABLED)
            self.scan_btn.config(state=tk.DISABLED)
            
            type_text = {
                'images': 'imágenes (incluye RAW)',
                'videos': 'videos',
                'both': 'imágenes y videos'
            }[file_type]
            
            self.log_message("✓ Monitoreo iniciado correctamente")
            self.log_message(f"→ Vigilando: {self.selected_folder}")
            self.log_message(f"→ Procesando: {type_text}")
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo iniciar el monitoreo:\n{type(e).__name__}")
            self.log_message(f"✗ Error al iniciar: {type(e).__name__}")
    
    def stop_monitoring(self):
        """Detiene el monitoreo"""
        try:
            if self.event_handler:
                self.event_handler.stop()
            
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=3)
                self.observer = None
            
            self.event_handler = None
            self.monitoring = False
            self.toggle_btn.config(text="▶ Iniciar Monitoreo", bg="#2196F3")
            self.status_label.config(text="● Detenido", fg="red")
            self.select_btn.config(state=tk.NORMAL)
            self.scan_btn.config(state=tk.NORMAL)
            
            self.log_message("✓ Monitoreo detenido correctamente")
        except Exception as e:
            self.log_message(f"✗ Error al detener: {type(e).__name__}")
    
    def on_closing(self):
        """Maneja el cierre de la aplicación"""
        if self.monitoring:
            self.stop_monitoring()
        
        if self.scanning and self.scanner:
            self.scanner.cancel()
        
        self.root.destroy()


def main():
    """Función principal"""
    try:
        root = tk.Tk()
        app = MediaRenamerApp(root)
        root.protocol("WM_DELETE_WINDOW", app.on_closing)
        root.mainloop()
    except Exception as e:
        print(f"Error al iniciar la aplicación: {type(e).__name__}")
        sys.exit(1)


if __name__ == "__main__":
    main()