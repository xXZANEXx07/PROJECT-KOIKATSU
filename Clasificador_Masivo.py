import os
import shutil
import json
import re
import zipfile
from dataclasses import dataclass, asdict
from typing import Optional, Callable, Dict, Any
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import logging
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('card_classifier.log'),
        logging.StreamHandler()
    ]
)

# Tipos básicos de tarjetas - ordenados por prioridad
CARD_TYPES = [
    "KStudio",            # Primero verificar KStudio
    "KoiKatuCharaSun",    # Luego la versión más especial
    "KoiKatuCharaSP",     # Después la versión SP
    "KoiKatuCharaS",      # Luego la versión S
    "KoiKatuChara",       # Finalmente la versión básica
    "KoiKatuClothes",
    "AIS_Chara",
    "AIS_Clothes",
    "AIS_Housing",
    "AIS_Studio",
    "RG_Chara",
    "EroMakeChara",
    "EroMakeClothes",
    "EroMakeMap",
    "EroMakePose",
    "EroMakeHScene",
    "HCPChara",
    "HCPClothes",
    "HCChara",
    "HCClothes"
]

# Extensiones de archivo soportadas
SUPPORTED_EXTENSIONS = ['.png', '.zipmod']

TRADUCCIONES = {
    "es": {
        "title": "Clasificador de Tarjetas KK",
        "select_folder": "Seleccionar Carpeta",
        "start": "Iniciar Clasificación",
        "language": "Idioma",
        "processing": "Procesando...",
        "done": "¡Clasificación Completa!",
        "select_input": "Por favor seleccione la carpeta de entrada",
        "selected_folder": "Carpeta seleccionada: {}",
        "processing_file": "Procesando archivo: {}",
        "total_processed": "Total de archivos procesados: {}",
        "no_folder": "¡Por favor seleccione una carpeta primero!",
        "error": "Error",
        "complete": "Completado",
        "no_files": "No se encontraron archivos válidos en la carpeta seleccionada!",
        "copy_mode": "Modo Copia (no mover archivos)",
        "dry_run": "Simulación (solo mostrar)",
        "create_summary": "Crear resumen",
        "open_output": "Abrir carpeta de salida",
        "cancel": "Cancelar",
        "cancelled": "Operación cancelada",
        "summary_title": "Resumen de Clasificación",
        "files_processed": "Archivos procesados: {}",
        "files_by_type": "Archivos por tipo:",
        "backup_created": "Backup creado en: {}",
        "invalid_folder": "La carpeta seleccionada no es válida",
        "permission_error": "Error de permisos: {}",
        "processing_error": "Error procesando archivo {}: {}",
        "classification_interrupted": "Clasificación interrumpida",
        "settings": "Configuración",
        "save_settings": "Guardar configuración",
        "load_settings": "Cargar configuración"
    },
    "en": {
        "title": "KK Card Classifier",
        "select_folder": "Select Folder",
        "start": "Start Classification",
        "language": "Language",
        "processing": "Processing...",
        "done": "Classification Complete!",
        "select_input": "Please select input folder",
        "selected_folder": "Selected folder: {}",
        "processing_file": "Processing file: {}",
        "total_processed": "Total files processed: {}",
        "no_folder": "Please select a folder first!",
        "error": "Error",
        "complete": "Complete",
        "no_files": "No valid files found in selected folder!",
        "copy_mode": "Copy Mode (don't move files)",
        "dry_run": "Dry Run (show only)",
        "create_summary": "Create summary",
        "open_output": "Open output folder",
        "cancel": "Cancel",
        "cancelled": "Operation cancelled",
        "summary_title": "Classification Summary",
        "files_processed": "Files processed: {}",
        "files_by_type": "Files by type:",
        "backup_created": "Backup created at: {}",
        "invalid_folder": "Selected folder is not valid",
        "permission_error": "Permission error: {}",
        "processing_error": "Error processing file {}: {}",
        "classification_interrupted": "Classification interrupted",
        "settings": "Settings",
        "save_settings": "Save settings",
        "load_settings": "Load settings"
    }
}

@dataclass
class CardInfo:
    type: str
    file_size: Optional[int] = None
    mod_info: Optional[str] = None  # Para información adicional de mods
    
    def to_dict(self):
        return asdict(self)

@dataclass
class ClassificationSettings:
    copy_mode: bool = False
    dry_run: bool = False
    create_summary: bool = True
    create_backup: bool = False
    language: str = "es"
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        return cls(**data)

class CardClassifier:
    def __init__(self, input_folder: str, settings: ClassificationSettings = None):
        self.input_folder = Path(input_folder)
        self.output_folder = self.input_folder / "clasificadas"
        self.settings = settings or ClassificationSettings()
        self.cancelled = False
        self.stats = {
            "processed": 0,
            "by_type": {},
            "errors": []
        }
        
    def cancel(self):
        """Cancela la operación en curso."""
        self.cancelled = True
        
    def has_valid_files(self) -> bool:
        """Verifica si hay archivos válidos en la carpeta de entrada."""
        try:
            for ext in SUPPORTED_EXTENSIONS:
                for file_path in self.input_folder.rglob(f"*{ext}"):
                    if "clasificadas" not in str(file_path):
                        return True
        except PermissionError as e:
            logging.error(f"Permission error accessing folder: {e}")
            return False
        return False
    
    def get_valid_files(self):
        """Obtiene todos los archivos válidos (PNG y ZIPMOD)."""
        valid_files = []
        try:
            for ext in SUPPORTED_EXTENSIONS:
                for file_path in self.input_folder.rglob(f"*{ext}"):
                    if "clasificadas" not in str(file_path):
                        valid_files.append(file_path)
        except PermissionError as e:
            logging.error(f"Permission error: {e}")
        return valid_files

    def check_zipmod_type(self, file_path: Path) -> CardInfo:
        """Analiza un archivo .zipmod para determinar su tipo."""
        try:
            file_size = file_path.stat().st_size
            
            # Intentar leer el contenido del zipmod
            with zipfile.ZipFile(file_path, 'r') as zip_file:
                file_list = zip_file.namelist()
                
                # Buscar archivos característicos para determinar el tipo
                mod_type = "Mod_Desconocido"
                mod_info = ""
                
                # Verificar si contiene personajes
                if any('chara' in f.lower() or 'character' in f.lower() for f in file_list):
                    mod_type = "Mod_Personajes"
                    mod_info = "Contiene archivos de personajes"
                # Verificar si contiene ropa
                elif any('cloth' in f.lower() or 'outfit' in f.lower() for f in file_list):
                    mod_type = "Mod_Ropa"
                    mod_info = "Contiene archivos de ropa"
                # Verificar si contiene accesorios
                elif any('acc' in f.lower() or 'accessory' in f.lower() for f in file_list):
                    mod_type = "Mod_Accesorios"
                    mod_info = "Contiene accesorios"
                # Verificar si contiene mapas/escenarios
                elif any('map' in f.lower() or 'scene' in f.lower() or 'studio' in f.lower() for f in file_list):
                    mod_type = "Mod_Mapas"
                    mod_info = "Contiene mapas o escenarios"
                # Verificar si contiene poses
                elif any('pose' in f.lower() or 'anim' in f.lower() for f in file_list):
                    mod_type = "Mod_Poses"
                    mod_info = "Contiene poses o animaciones"
                # Si tiene archivos .unity3d, probablemente sea un mod de assets
                elif any(f.endswith('.unity3d') for f in file_list):
                    mod_type = "Mod_Assets"
                    mod_info = "Contiene assets Unity3D"
                else:
                    # Contar tipos de archivos para dar más información
                    extensions = {}
                    for f in file_list:
                        ext = Path(f).suffix.lower()
                        extensions[ext] = extensions.get(ext, 0) + 1
                    
                    if extensions:
                        top_ext = max(extensions, key=extensions.get)
                        mod_info = f"Principalmente archivos {top_ext} ({len(file_list)} archivos)"
                
                return CardInfo(type=mod_type, file_size=file_size, mod_info=mod_info)
                
        except zipfile.BadZipFile:
            logging.error(f"Invalid zip file: {file_path}")
            return CardInfo(type="Mod_Error", file_size=file_path.stat().st_size, mod_info="Archivo ZIP corrupto")
        except Exception as e:
            logging.error(f"Error processing zipmod {file_path}: {str(e)}")
            self.stats["errors"].append(f"{file_path.name}: {str(e)}")
            return CardInfo(type="Mod_Error", file_size=0, mod_info=str(e))

    def check_card_type(self, file_path: Path) -> CardInfo:
        """Analiza un archivo PNG para determinar su tipo de tarjeta."""
        try:
            file_size = file_path.stat().st_size
            
            with open(file_path, 'rb') as f:
                content = f.read()
                
            # Usar latin-1 para evitar errores de decodificación
            try:
                content_str = content.decode('latin-1')
            except UnicodeDecodeError:
                content_str = content.decode('utf-8', errors='ignore')

            # Verificar tipos de tarjetas en orden de prioridad
            for card_type in CARD_TYPES:
                if card_type in content_str:
                    return CardInfo(type=card_type, file_size=file_size)

            return CardInfo(type="Desconocido", file_size=file_size)

        except Exception as e:
            logging.error(f"Error processing {file_path}: {str(e)}")
            self.stats["errors"].append(f"{file_path.name}: {str(e)}")
            return CardInfo(type="Error", file_size=0)

    def get_target_directory(self, card_info: CardInfo, base_dir: Path) -> Path:
        """Determina el directorio destino basado en la información del archivo."""
        # Si es un mod (.zipmod)
        if card_info.type.startswith("Mod_"):
            return base_dir / "Mods" / card_info.type.replace("Mod_", "")
        
        # Si es un error
        if card_info.type == "Error":
            return base_dir / "Errores"
        
        # Para todos los demás tipos (incluyendo KStudio), usar directamente el tipo
        return base_dir / card_info.type

    def create_backup(self) -> Path:
        """Crea un backup de los archivos originales."""
        backup_dir = self.input_folder / "backup"
        backup_dir.mkdir(exist_ok=True)
        
        valid_files = self.get_valid_files()
        for file_path in valid_files:
            relative_path = file_path.relative_to(self.input_folder)
            backup_path = backup_dir / relative_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, backup_path)
        
        return backup_dir

    def classify_files(self, update_progress: Callable = None, update_status: Callable = None) -> bool:
        """Clasifica los archivos en diferentes categorías."""
        try:
            if not self.input_folder.exists():
                raise FileNotFoundError(f"Input folder does not exist: {self.input_folder}")
            
            # Crear backup si está habilitado
            if self.settings.create_backup and not self.settings.dry_run:
                backup_dir = self.create_backup()
                logging.info(f"Backup created at: {backup_dir}")
            
            # Crear carpeta de salida si no es simulación
            if not self.settings.dry_run:
                self.output_folder.mkdir(exist_ok=True)
            
            # Obtener archivos válidos
            valid_files = self.get_valid_files()
            
            if not valid_files:
                if update_status:
                    update_status("No se encontraron archivos válidos")
                return False
            
            total_files = len(valid_files)
            processed_files = 0
            
            # Procesar archivos
            for file_path in valid_files:
                if self.cancelled:
                    if update_status:
                        update_status("Operación cancelada")
                    return False
                
                if update_status:
                    update_status(f"Procesando: {file_path.name}")
                
                # Analizar archivo según su extensión
                if file_path.suffix.lower() == '.zipmod':
                    card_info = self.check_zipmod_type(file_path)
                else:  # .png
                    card_info = self.check_card_type(file_path)
                
                # Actualizar estadísticas
                self.stats["by_type"][card_info.type] = self.stats["by_type"].get(card_info.type, 0) + 1
                
                if not self.settings.dry_run:
                    # Determinar directorio destino
                    target_dir = self.get_target_directory(card_info, self.output_folder)
                    target_dir.mkdir(parents=True, exist_ok=True)
                    
                    target_file = target_dir / file_path.name
                    
                    # Manejar archivos duplicados
                    counter = 1
                    while target_file.exists():
                        name_parts = file_path.stem, counter, file_path.suffix
                        target_file = target_dir / f"{name_parts[0]}_{name_parts[1]}{name_parts[2]}"
                        counter += 1
                    
                    # Mover o copiar archivo
                    if self.settings.copy_mode:
                        shutil.copy2(file_path, target_file)
                    else:
                        shutil.move(str(file_path), str(target_file))
                
                processed_files += 1
                self.stats["processed"] = processed_files
                
                if update_progress:
                    progress = int((processed_files / total_files) * 100)
                    update_progress(progress)
            
            # Crear resumen si está habilitado
            if self.settings.create_summary and not self.settings.dry_run:
                self.create_summary()
            
            if update_status:
                status = "Simulación completada" if self.settings.dry_run else "Clasificación completada"
                update_status(status)
            
            return True
            
        except Exception as e:
            logging.error(f"Error during classification: {str(e)}")
            if update_status:
                update_status(f"Error: {str(e)}")
            return False

    def create_summary(self):
        """Crea un archivo de resumen con estadísticas de la clasificación."""
        summary_data = {
            "total_processed": self.stats["processed"],
            "by_type": self.stats["by_type"],
            "errors": self.stats["errors"],
            "settings": self.settings.to_dict()
        }
        
        summary_file = self.output_folder / "resumen_clasificacion.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.input_folder = ""
        self.settings = ClassificationSettings()
        self.classifier = None
        self.classification_thread = None
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        self.title(TRADUCCIONES[self.settings.language]["title"])
        self.geometry("600x450")
        self.resizable(True, True)

        # Configuración de estilo
        style = ttk.Style()
        style.theme_use('clam')

        # Frame principal con scroll
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Notebook para pestañas
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True)

        # Pestaña principal
        main_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text="Clasificación")

        # Pestaña de configuración
        config_tab = ttk.Frame(notebook)
        notebook.add(config_tab, text=TRADUCCIONES[self.settings.language]["settings"])

        self.setup_main_tab(main_tab)
        self.setup_config_tab(config_tab)

    def setup_main_tab(self, parent):
        # Selección de carpeta
        folder_frame = ttk.LabelFrame(parent, text="Carpeta de entrada", padding=10)
        folder_frame.pack(fill="x", pady=(0, 10))

        self.folder_label = ttk.Label(folder_frame, text=TRADUCCIONES[self.settings.language]["select_input"])
        self.folder_label.pack(fill="x", pady=(0, 5))
        
        folder_button_frame = ttk.Frame(folder_frame)
        folder_button_frame.pack(fill="x")
        
        ttk.Button(folder_button_frame, text=TRADUCCIONES[self.settings.language]["select_folder"], 
                  command=self.select_folder).pack(side="left")
        
        ttk.Button(folder_button_frame, text=TRADUCCIONES[self.settings.language]["open_output"], 
                  command=self.open_output_folder).pack(side="left", padx=(10, 0))

        # Información de archivos soportados
        info_frame = ttk.LabelFrame(parent, text="Archivos soportados", padding=10)
        info_frame.pack(fill="x", pady=(0, 10))
        
        info_text = "Este clasificador procesa:\n• Tarjetas (.png): KStudio, KoiKatu, AIS, etc.\n• Mods (.zipmod): Automáticamente categorizados por contenido"
        ttk.Label(info_frame, text=info_text, justify="left").pack(anchor="w")

        # Opciones rápidas
        options_frame = ttk.LabelFrame(parent, text="Opciones", padding=10)
        options_frame.pack(fill="x", pady=(0, 10))

        self.copy_mode_var = tk.BooleanVar(value=self.settings.copy_mode)
        ttk.Checkbutton(options_frame, text=TRADUCCIONES[self.settings.language]["copy_mode"], 
                       variable=self.copy_mode_var).pack(anchor="w")

        self.dry_run_var = tk.BooleanVar(value=self.settings.dry_run)
        ttk.Checkbutton(options_frame, text=TRADUCCIONES[self.settings.language]["dry_run"], 
                       variable=self.dry_run_var).pack(anchor="w")

        self.create_summary_var = tk.BooleanVar(value=self.settings.create_summary)
        ttk.Checkbutton(options_frame, text=TRADUCCIONES[self.settings.language]["create_summary"], 
                       variable=self.create_summary_var).pack(anchor="w")

        # Progreso
        progress_frame = ttk.LabelFrame(parent, text="Progreso", padding=10)
        progress_frame.pack(fill="x", pady=(0, 10))

        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress.pack(fill="x", pady=(0, 5))
        
        self.status_label = ttk.Label(progress_frame, text="")
        self.status_label.pack(fill="x")

        # Botones de control
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill="x", pady=(0, 10))

        self.start_button = ttk.Button(button_frame, text=TRADUCCIONES[self.settings.language]["start"], 
                                     command=self.start_classification)
        self.start_button.pack(side="left")

        self.cancel_button = ttk.Button(button_frame, text=TRADUCCIONES[self.settings.language]["cancel"], 
                                      command=self.cancel_classification, state="disabled")
        self.cancel_button.pack(side="left", padx=(10, 0))

        # Área de estadísticas
        stats_frame = ttk.LabelFrame(parent, text="Estadísticas", padding=10)
        stats_frame.pack(fill="both", expand=True)

        self.stats_text = tk.Text(stats_frame, height=8, state="disabled")
        scrollbar = ttk.Scrollbar(stats_frame, orient="vertical", command=self.stats_text.yview)
        self.stats_text.configure(yscrollcommand=scrollbar.set)
        
        self.stats_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def setup_config_tab(self, parent):
        # Configuración de idioma
        lang_frame = ttk.LabelFrame(parent, text="Idioma", padding=10)
        lang_frame.pack(fill="x", pady=(0, 10))

        self.language_var = tk.StringVar(value=self.settings.language)
        ttk.Radiobutton(lang_frame, text="Español", variable=self.language_var, 
                       value="es", command=self.change_language).pack(anchor="w")
        ttk.Radiobutton(lang_frame, text="English", variable=self.language_var, 
                       value="en", command=self.change_language).pack(anchor="w")

        # Configuración avanzada
        advanced_frame = ttk.LabelFrame(parent, text="Configuración avanzada", padding=10)
        advanced_frame.pack(fill="x", pady=(0, 10))

        self.create_backup_var = tk.BooleanVar(value=self.settings.create_backup)
        ttk.Checkbutton(advanced_frame, text="Crear backup antes de clasificar", 
                       variable=self.create_backup_var).pack(anchor="w")

        # Botones de configuración
        config_button_frame = ttk.Frame(parent)
        config_button_frame.pack(fill="x")

        ttk.Button(config_button_frame, text=TRADUCCIONES[self.settings.language]["save_settings"], 
                  command=self.save_settings).pack(side="left")
        
        ttk.Button(config_button_frame, text=TRADUCCIONES[self.settings.language]["load_settings"], 
                  command=self.load_settings).pack(side="left", padx=(10, 0))

    def change_language(self):
        """Cambia el idioma de la interfaz."""
        self.settings.language = self.language_var.get()
        self.title(TRADUCCIONES[self.settings.language]["title"])

    def select_folder(self):
        folder = filedialog.askdirectory(title=TRADUCCIONES[self.settings.language]["select_folder"])
        if folder:
            self.input_folder = folder
            self.folder_label.config(text=TRADUCCIONES[self.settings.language]["selected_folder"].format(folder))

    def open_output_folder(self):
        """Abre la carpeta de salida en el explorador de archivos."""
        if self.input_folder:
            output_path = Path(self.input_folder) / "clasificadas"
            if output_path.exists():
                import subprocess
                import platform
                
                if platform.system() == "Windows":
                    subprocess.run(["explorer", str(output_path)])
                elif platform.system() == "Darwin":  # macOS
                    subprocess.run(["open", str(output_path)])
                else:  # Linux
                    subprocess.run(["xdg-open", str(output_path)])

    def update_progress(self, value):
        self.progress_var.set(value)
        self.update_idletasks()

    def update_status(self, text):
        self.status_label.config(text=text)
        self.update_idletasks()

    def update_stats(self, stats):
        """Actualiza el área de estadísticas."""
        self.stats_text.config(state="normal")
        self.stats_text.delete(1.0, tk.END)
        
        stats_text = f"Archivos procesados: {stats['processed']}\n\n"
        stats_text += "Archivos por tipo:\n"
        for card_type, count in stats['by_type'].items():
            stats_text += f"  {card_type}: {count}\n"
        
        if stats['errors']:
            stats_text += f"\nErrores ({len(stats['errors'])}):\n"
            for error in stats['errors'][:10]:  # Mostrar solo los primeros 10 errores
                stats_text += f"  {error}\n"
            if len(stats['errors']) > 10:
                stats_text += f"  ... y {len(stats['errors']) - 10} más\n"
        
        self.stats_text.insert(1.0, stats_text)
        self.stats_text.config(state="disabled")

    def start_classification(self):
        if not self.input_folder:
            messagebox.showerror(TRADUCCIONES[self.settings.language]["error"], 
                               TRADUCCIONES[self.settings.language]["no_folder"])
            return

        # Actualizar configuración
        self.settings.copy_mode = self.copy_mode_var.get()
        self.settings.dry_run = self.dry_run_var.get()
        self.settings.create_summary = self.create_summary_var.get()
        self.settings.create_backup = self.create_backup_var.get()

        self.start_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self.progress_var.set(0)
        self.status_label.config(text=TRADUCCIONES[self.settings.language]["processing"])

        self.classifier = CardClassifier(self.input_folder, self.settings)
        
        def classify_thread():
            try:
                success = self.classifier.classify_files(
                    update_progress=self.update_progress,
                    update_status=self.update_status
                )
                
                # Actualizar estadísticas finales
                self.update_stats(self.classifier.stats)
                
                if success and not self.classifier.cancelled:
                    message = TRADUCCIONES[self.settings.language]["done"]
                    self.status_label.config(text=message)
                    messagebox.showinfo(TRADUCCIONES[self.settings.language]["complete"], message)
                elif self.classifier.cancelled:
                    message = TRADUCCIONES[self.settings.language]["cancelled"]
                    self.status_label.config(text=message)
                else:
                    message = TRADUCCIONES[self.settings.language]["no_files"]
                    self.status_label.config(text=message)
                    messagebox.showinfo(TRADUCCIONES[self.settings.language]["complete"], message)
                    
            except Exception as e:
                error_msg = f"Error: {str(e)}"
                self.status_label.config(text=error_msg)
                messagebox.showerror(TRADUCCIONES[self.settings.language]["error"], error_msg)
            finally:
                self.start_button.config(state="normal")
                self.cancel_button.config(state="disabled")

        self.classification_thread = threading.Thread(target=classify_thread)
        self.classification_thread.daemon = True
        self.classification_thread.start()

    def cancel_classification(self):
        """Cancela la clasificación en curso."""
        if self.classifier:
            self.classifier.cancel()
        self.cancel_button.config(state="disabled")

    def save_settings(self):
        """Guarda la configuración actual."""
        # Actualizar configuración
        self.settings.copy_mode = self.copy_mode_var.get()
        self.settings.dry_run = self.dry_run_var.get()
        self.settings.create_summary = self.create_summary_var.get()
        self.settings.create_backup = self.create_backup_var.get()
        self.settings.language = self.language_var.get()

        settings_file = Path("card_classifier_settings.json")
        try:
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings.to_dict(), f, indent=2)
            messagebox.showinfo("Configuración", "Configuración guardada correctamente")
        except Exception as e:
            messagebox.showerror("Error", f"Error guardando configuración: {str(e)}")

    def load_settings(self):
        """Carga la configuración guardada."""
        settings_file = Path("card_classifier_settings.json")
        try:
            if settings_file.exists():
                with open(settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.settings = ClassificationSettings.from_dict(data)
                
                # Actualizar interfaz
                self.copy_mode_var.set(self.settings.copy_mode)
                self.dry_run_var.set(self.settings.dry_run)
                self.create_summary_var.set(self.settings.create_summary)
                self.create_backup_var.set(self.settings.create_backup)
                self.language_var.set(self.settings.language)
                
                self.change_language()
        except Exception as e:
            logging.error(f"Error loading settings: {str(e)}")

def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()