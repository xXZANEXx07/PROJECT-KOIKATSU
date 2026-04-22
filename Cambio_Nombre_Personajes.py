import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageEnhance
from kkloader import KoikatuCharaData
import os
import re
import threading
import time
import json
from deep_translator import GoogleTranslator
import pyperclip
from functools import lru_cache
import hashlib
from datetime import datetime
import sqlite3
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ConfigManager:
    """Maneja la configuración persistente de la aplicación"""
    def __init__(self, config_file="koikatsu_config.json"):
        self.config_file = config_file
        self.default_config = {
            "window_geometry": "500x850",
            "last_folder": "",
            "translation_language": "en",
            "auto_translate": True,
            "image_quality": "medium",
            "theme": "dark",
            "backup_enabled": True,
            "recent_folders": []
        }
        self.config = self.load_config()

    def load_config(self):
        """Carga la configuración desde archivo"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Combinar con defaults para nuevas opciones
                    return {**self.default_config, **config}
            return self.default_config.copy()
        except Exception as e:
            logger.error(f"Error cargando configuración: {e}")
            return self.default_config.copy()

    def save_config(self):
        """Guarda la configuración actual"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error guardando configuración: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value

    def add_recent_folder(self, folder_path):
        """Añade una carpeta a la lista de recientes"""
        recent = self.config.get("recent_folders", [])
        if folder_path in recent:
            recent.remove(folder_path)
        recent.insert(0, folder_path)
        self.config["recent_folders"] = recent[:10]  # Máximo 10 carpetas

class DatabaseManager:
    """Maneja la base de datos local para cache y estadísticas"""
    def __init__(self, db_file="koikatsu_data.db"):
        self.db_file = db_file
        self.init_database()

    def init_database(self):
        """Inicializa la base de datos"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Tabla para cache de traducciones
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS translation_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text_hash TEXT UNIQUE,
                    original_text TEXT,
                    target_lang TEXT,
                    translation TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabla para estadísticas de uso
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usage_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error inicializando base de datos: {e}")

    def get_translation(self, text_hash):
        """Obtiene traducción del cache"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT translation FROM translation_cache WHERE text_hash = ?",
                (text_hash,)
            )
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Error obteniendo traducción: {e}")
            return None

    def save_translation(self, text_hash, original_text, target_lang, translation):
        """Guarda traducción en cache"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO translation_cache (text_hash, original_text, target_lang, translation) VALUES (?, ?, ?, ?)",
                (text_hash, original_text, target_lang, translation)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error guardando traducción: {e}")

    def log_usage(self, action, details=""):
        """Registra estadísticas de uso"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO usage_stats (action, details) VALUES (?, ?)",
                (action, details)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error registrando estadística: {e}")

class BackupManager:
    """Maneja respaldos automáticos de las cartas"""
    def __init__(self, backup_dir="backups"):
        self.backup_dir = backup_dir
        self.ensure_backup_dir()

    def ensure_backup_dir(self):
        """Asegura que el directorio de respaldos existe"""
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

    def create_backup(self, card_path):
        """Crea respaldo de una carta antes de modificarla"""
        try:
            filename = os.path.basename(card_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"{timestamp}_{filename}"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # Copiar archivo
            with open(card_path, 'rb') as src, open(backup_path, 'wb') as dst:
                dst.write(src.read())
            
            logger.info(f"Respaldo creado: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Error creando respaldo: {e}")
            return None

    def get_recent_backups(self, limit=20):
        """Obtiene lista de respaldos recientes"""
        try:
            backups = []
            for file in os.listdir(self.backup_dir):
                if file.endswith('.png'):
                    path = os.path.join(self.backup_dir, file)
                    backups.append({
                        'file': file,
                        'path': path,
                        'date': os.path.getmtime(path)
                    })
            return sorted(backups, key=lambda x: x['date'], reverse=True)[:limit]
        except Exception as e:
            logger.error(f"Error obteniendo respaldos: {e}")
            return []

class ImageProcessor:
    """Maneja el procesamiento avanzado de imágenes"""
    
    @staticmethod
    def enhance_image(image, brightness=1.0, contrast=1.0, saturation=1.0):
        """Mejora la imagen aplicando filtros"""
        try:
            if brightness != 1.0:
                enhancer = ImageEnhance.Brightness(image)
                image = enhancer.enhance(brightness)
            
            if contrast != 1.0:
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(contrast)
                
            if saturation != 1.0:
                enhancer = ImageEnhance.Color(image)
                image = enhancer.enhance(saturation)
                
            return image
        except Exception as e:
            logger.error(f"Error procesando imagen: {e}")
            return image

    @staticmethod
    def get_image_info(image_path):
        """Obtiene información detallada de la imagen"""
        try:
            with Image.open(image_path) as img:
                return {
                    'size': img.size,
                    'mode': img.mode,
                    'format': img.format,
                    'file_size': os.path.getsize(image_path)
                }
        except Exception as e:
            logger.error(f"Error obteniendo info de imagen: {e}")
            return {}

class KoikatsuCardViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        
        # Inicializar managers
        self.config_manager = ConfigManager()
        self.db_manager = DatabaseManager()
        self.backup_manager = BackupManager()
        self.image_processor = ImageProcessor()
        
        # Configurar ventana
        self.title("Koikatsu Card Viewer Pro")
        self.geometry(self.config_manager.get("window_geometry", "500x850"))
        self.configure(bg="#1a1a1a")
        
        # Variables de estado
        self.card_paths = []
        self.current_index = -1
        self.kc = None
        self.card_path = None
        self.current_image = None
        self.is_loading = False
        self.filter_text = tk.StringVar()
        self.filtered_paths = []
        
        # Variables de imagen
        self.image_brightness = tk.DoubleVar(value=1.0)
        self.image_contrast = tk.DoubleVar(value=1.0)
        self.image_saturation = tk.DoubleVar(value=1.0)
        
        self.setup_ui()
        self.setup_bindings()
        self.setup_menu()
        self.restore_session()

    def setup_menu(self):
        """Configura el menú principal"""
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # Menú Archivo
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Archivo", menu=file_menu)
        file_menu.add_command(label="Abrir Carpeta", command=self.abrir_carpeta, accelerator="Ctrl+O")
        file_menu.add_separator()
        
        # Carpetas recientes
        recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Carpetas Recientes", menu=recent_menu)
        self.update_recent_menu(recent_menu)
        
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=self.on_closing, accelerator="Ctrl+Q")

        # Menú Edición
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edición", menu=edit_menu)
        edit_menu.add_command(label="Guardar", command=self.guardar_cambios, accelerator="Ctrl+S")
        edit_menu.add_command(label="Limpiar Campos", command=self.limpiar_campos, accelerator="Esc")
        edit_menu.add_separator()
        edit_menu.add_command(label="Configuración", command=self.mostrar_configuracion)

        # Menú Herramientas
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Herramientas", menu=tools_menu)
        tools_menu.add_command(label="Limpiar Cache", command=self.limpiar_cache)
        tools_menu.add_command(label="Ver Respaldos", command=self.mostrar_respaldos)
        tools_menu.add_command(label="Estadísticas", command=self.mostrar_estadisticas)

        # Menú Ayuda
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Ayuda", menu=help_menu)
        help_menu.add_command(label="Atajos de Teclado", command=self.mostrar_ayuda, accelerator="F1")
        help_menu.add_command(label="Acerca de", command=self.mostrar_acerca_de)

    def setup_ui(self):
        """Configura toda la interfaz de usuario"""
        # Crear notebook para pestañas
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Pestaña principal
        self.main_frame = tk.Frame(self.notebook, bg="#1a1a1a")
        self.notebook.add(self.main_frame, text="Editor Principal")

        # Pestaña de filtros de imagen
        self.image_frame = tk.Frame(self.notebook, bg="#1a1a1a")
        self.notebook.add(self.image_frame, text="Filtros de Imagen")

        # Configurar pestaña principal
        self.setup_main_tab()
        
        # Configurar pestaña de filtros
        self.setup_image_filters_tab()

    def setup_main_tab(self):
        """Configura la pestaña principal"""
        # Barra de herramientas superior
        toolbar = tk.Frame(self.main_frame, bg="#1a1a1a")
        toolbar.pack(fill="x", pady=5)

        # Filtro de búsqueda
        tk.Label(toolbar, text="🔍 Filtro:", bg="#1a1a1a", fg="white").pack(side="left")
        self.filter_entry = tk.Entry(toolbar, textvariable=self.filter_text, width=20)
        self.filter_entry.pack(side="left", padx=5)
        self.filter_text.trace('w', self.on_filter_change)

        # Información de archivo
        self.info_label = tk.Label(toolbar, text="", bg="#1a1a1a", fg="#888", font=("Arial", 8))
        self.info_label.pack(side="right")

        # Imagen de preview con scroll
        self.setup_image_preview()

        # Indicador de progreso
        self.progress_var = tk.StringVar()
        self.progress_label = tk.Label(self.main_frame, textvariable=self.progress_var, 
                                     bg="#1a1a1a", fg="yellow", font=("Arial", 10))
        self.progress_label.pack()

        # Información actual
        self.text_actual = tk.Text(self.main_frame, height=4, width=50, wrap="word", 
                                 bg="#111", fg="white", font=("Arial", 10))
        self.text_actual.configure(state='disabled')
        self.text_actual.pack(pady=5)

        # Campos de edición mejorados
        self.setup_edit_fields()

        # Botones principales
        self.setup_buttons()

        # Configuración de traducción
        self.setup_translation_ui()

    def setup_image_preview(self):
        """Configura el área de preview de imagen con scroll"""
        # Frame contenedor con scroll
        canvas_frame = tk.Frame(self.main_frame, bg="#1a1a1a")
        canvas_frame.pack(pady=10)

        # Canvas para la imagen
        self.image_canvas = tk.Canvas(canvas_frame, width=400, height=400, bg="#333")
        self.image_canvas.pack()

        # Label para la imagen
        self.preview_label = tk.Label(self.image_canvas, bg="#333")
        self.image_canvas.create_window(200, 200, window=self.preview_label)

    def setup_image_filters_tab(self):
        """Configura la pestaña de filtros de imagen"""
        # Controles de brillo
        tk.Label(self.image_frame, text="☀️ Brillo:", bg="#1a1a1a", fg="white").pack(pady=5)
        brightness_scale = tk.Scale(self.image_frame, from_=0.1, to=2.0, resolution=0.1,
                                   orient="horizontal", variable=self.image_brightness,
                                   bg="#1a1a1a", fg="white", highlightthickness=0)
        brightness_scale.pack(pady=5)
        brightness_scale.bind("<ButtonRelease-1>", self.update_image_filters)

        # Controles de contraste
        tk.Label(self.image_frame, text="🎨 Contraste:", bg="#1a1a1a", fg="white").pack(pady=5)
        contrast_scale = tk.Scale(self.image_frame, from_=0.1, to=2.0, resolution=0.1,
                                 orient="horizontal", variable=self.image_contrast,
                                 bg="#1a1a1a", fg="white", highlightthickness=0)
        contrast_scale.pack(pady=5)
        contrast_scale.bind("<ButtonRelease-1>", self.update_image_filters)

        # Controles de saturación
        tk.Label(self.image_frame, text="🌈 Saturación:", bg="#1a1a1a", fg="white").pack(pady=5)
        saturation_scale = tk.Scale(self.image_frame, from_=0.0, to=2.0, resolution=0.1,
                                   orient="horizontal", variable=self.image_saturation,
                                   bg="#1a1a1a", fg="white", highlightthickness=0)
        saturation_scale.pack(pady=5)
        saturation_scale.bind("<ButtonRelease-1>", self.update_image_filters)

        # Botones de filtros
        filter_buttons = tk.Frame(self.image_frame, bg="#1a1a1a")
        filter_buttons.pack(pady=20)

        tk.Button(filter_buttons, text="↺ Resetear", command=self.reset_image_filters).pack(side="left", padx=5)
        tk.Button(filter_buttons, text="💾 Guardar Filtros", command=self.save_image_filters).pack(side="left", padx=5)

    def setup_edit_fields(self):
        """Configura los campos de edición mejorados"""
        # Frame para campos
        fields_frame = tk.Frame(self.main_frame, bg="#1a1a1a")
        fields_frame.pack(pady=10)

        # Variables
        self.lastname_var = tk.StringVar()
        self.firstname_var = tk.StringVar()
        self.nickname_var = tk.StringVar()

        # Trazas para validación
        self.lastname_var.trace('w', self.validate_names)
        self.firstname_var.trace('w', self.validate_names)
        self.nickname_var.trace('w', self.validate_names)

        # Campos con contadores de caracteres
        self.create_field_with_counter(fields_frame, "Apellido:", self.lastname_var, 0)
        self.create_field_with_counter(fields_frame, "Nombre:", self.firstname_var, 1)
        self.create_field_with_counter(fields_frame, "Apodo:", self.nickname_var, 2)

        # Label para errores
        self.validation_var = tk.StringVar()
        self.validation_label = tk.Label(fields_frame, textvariable=self.validation_var, 
                                       bg="#1a1a1a", fg="red", font=("Arial", 9))
        self.validation_label.grid(row=3, column=0, columnspan=3, pady=5)

    def create_field_with_counter(self, parent, label_text, var, row):
        """Crea un campo con contador de caracteres"""
        tk.Label(parent, text=label_text, bg="#1a1a1a", fg="white").grid(row=row, column=0, sticky="w", padx=5)
        
        entry = tk.Entry(parent, textvariable=var, width=30, font=("Arial", 10))
        entry.grid(row=row, column=1, padx=5, pady=2)
        
        # Contador de caracteres
        counter_var = tk.StringVar()
        counter_label = tk.Label(parent, textvariable=counter_var, bg="#1a1a1a", fg="#888", font=("Arial", 8))
        counter_label.grid(row=row, column=2, padx=5)
        
        # Función para actualizar contador
        def update_counter(*args):
            text = var.get()
            counter_var.set(f"{len(text)}/50")
            if len(text) > 50:
                counter_label.config(fg="red")
            else:
                counter_label.config(fg="#888")
        
        var.trace('w', update_counter)
        update_counter()

    def setup_buttons(self):
        """Configura los botones principales mejorados"""
        # Frame principal de botones
        main_btn_frame = tk.Frame(self.main_frame, bg="#1a1a1a")
        main_btn_frame.pack(pady=10)

        # Botones de archivo
        file_frame = tk.Frame(main_btn_frame, bg="#1a1a1a")
        file_frame.pack(pady=5)

        tk.Button(file_frame, text="📁 Abrir Carpeta", command=self.abrir_carpeta, 
                 font=("Arial", 10), bg="#4a4a4a", fg="white").pack(side="left", padx=5)
        tk.Button(file_frame, text="💾 Guardar", command=self.guardar_cambios, 
                 font=("Arial", 10), bg="#2a5a2a", fg="white").pack(side="left", padx=5)
        tk.Button(file_frame, text="🗑️ Limpiar", command=self.limpiar_campos, 
                 font=("Arial", 10), bg="#5a2a2a", fg="white").pack(side="left", padx=5)

        # Navegación mejorada
        nav_frame = tk.Frame(main_btn_frame, bg="#1a1a1a")
        nav_frame.pack(pady=5)

        tk.Button(nav_frame, text="⏮️ Primero", command=self.primera_carta, 
                 font=("Arial", 10)).pack(side="left", padx=2)
        tk.Button(nav_frame, text="⬅️ Anterior", command=self.carta_anterior, 
                 font=("Arial", 10)).pack(side="left", padx=2)
        
        # Indicador de posición
        self.position_var = tk.StringVar()
        position_label = tk.Label(nav_frame, textvariable=self.position_var, 
                                 bg="#1a1a1a", fg="white", font=("Arial", 10))
        position_label.pack(side="left", padx=10)

        tk.Button(nav_frame, text="➡️ Siguiente", command=self.carta_siguiente, 
                 font=("Arial", 10)).pack(side="left", padx=2)
        tk.Button(nav_frame, text="⏭️ Último", command=self.ultima_carta, 
                 font=("Arial", 10)).pack(side="left", padx=2)

    def setup_translation_ui(self):
        """Configura la interfaz de traducción mejorada"""
        # Frame de traducción
        trans_frame = tk.Frame(self.main_frame, bg="#1a1a1a")
        trans_frame.pack(pady=10)

        # Selector de idioma mejorado
        tk.Label(trans_frame, text="🌐 Idioma:", bg="#1a1a1a", fg="white").pack()
        
        self.idioma_destino = tk.StringVar(value=self.config_manager.get("translation_language", "en"))
        self.idioma_destino.trace('w', self.on_language_change)

        idiomas = {
            "en": "🇺🇸 English", "es": "🇪🇸 Español", "fr": "🇫🇷 Français", 
            "de": "🇩🇪 Deutsch", "it": "🇮🇹 Italiano", "ru": "🇷🇺 Русский",
            "ko": "🇰🇷 한국어", "zh-CN": "🇨🇳 中文", "ja": "🇯🇵 日本語", 
            "pt": "🇵🇹 Português"
        }
        
        self.combo_idioma = ttk.Combobox(trans_frame, textvariable=self.idioma_destino, 
                                        values=list(idiomas.keys()), state="readonly")
        self.combo_idioma.pack(pady=5)

        # Área de traducción
        tk.Label(trans_frame, text="🔄 Traducción:", bg="#1a1a1a", fg="white").pack()
        self.text_traducido = tk.Text(trans_frame, height=4, width=50, wrap="word", 
                                    bg="#001a00", fg="#00ff00", font=("Arial", 10))
        self.text_traducido.configure(state='disabled')
        self.text_traducido.pack(pady=5)

        # Botones de traducción
        trans_btn_frame = tk.Frame(trans_frame, bg="#1a1a1a")
        trans_btn_frame.pack(pady=5)
        
        tk.Button(trans_btn_frame, text="🔄 Traducir", command=self.traducir_manual, 
                 font=("Arial", 10)).pack(side="left", padx=5)
        tk.Button(trans_btn_frame, text="📋 Copiar", command=self.copiar_traduccion, 
                 font=("Arial", 10)).pack(side="left", padx=5)
        tk.Button(trans_btn_frame, text="✨ Aplicar", command=self.usar_traduccion, 
                 font=("Arial", 10)).pack(side="left", padx=5)

        # Auto-traducción
        self.auto_translate_var = tk.BooleanVar(value=self.config_manager.get("auto_translate", True))
        tk.Checkbutton(trans_frame, text="Traducción automática", 
                      variable=self.auto_translate_var, bg="#1a1a1a", fg="white",
                      selectcolor="#333").pack(pady=5)

    def setup_bindings(self):
        """Configura todos los atajos de teclado"""
        # Navegación
        self.bind("<KeyPress-z>", self.carta_anterior)
        self.bind("<KeyPress-x>", self.carta_siguiente)
        self.bind("<Home>", self.primera_carta)
        self.bind("<End>", self.ultima_carta)
        
        # Acciones
        self.bind("<Control-s>", self.guardar_cambios)
        self.bind("<Control-o>", self.abrir_carpeta)
        self.bind("<Control-q>", self.on_closing)
        self.bind("<F1>", self.mostrar_ayuda)
        self.bind("<Escape>", self.limpiar_campos)
        
        # Traducción
        self.bind("<Control-t>", self.traducir_manual)
        self.bind("<Control-c>", self.copiar_traduccion)
        
        # Filtros
        self.bind("<Control-f>", lambda e: self.filter_entry.focus())
        
        self.focus_set()

    def restore_session(self):
        """Restaura la sesión anterior"""
        last_folder = self.config_manager.get("last_folder")
        if last_folder and os.path.exists(last_folder):
            self.load_folder(last_folder)

    def update_recent_menu(self, menu):
        """Actualiza el menú de carpetas recientes"""
        menu.delete(0, tk.END)
        recent_folders = self.config_manager.get("recent_folders", [])
        
        for folder in recent_folders:
            if os.path.exists(folder):
                menu.add_command(label=folder, command=lambda f=folder: self.load_folder(f))

    def on_filter_change(self, *args):
        """Maneja el cambio en el filtro de búsqueda"""
        if not self.card_paths:
            return
            
        filter_text = self.filter_text.get().lower()
        if not filter_text:
            self.filtered_paths = self.card_paths[:]
        else:
            self.filtered_paths = [path for path in self.card_paths 
                                  if filter_text in os.path.basename(path).lower()]
        
        # Ajustar índice actual
        if self.filtered_paths:
            if self.card_path in self.filtered_paths:
                self.current_index = self.filtered_paths.index(self.card_path)
            else:
                self.current_index = 0
                self.cargar_carta(self.filtered_paths[0])
        
        self.update_position_indicator()

    def update_position_indicator(self):
        """Actualiza el indicador de posición"""
        if self.filtered_paths:
            total = len(self.filtered_paths)
            current = self.current_index + 1
            self.position_var.set(f"{current}/{total}")
        else:
            self.position_var.set("0/0")

    def update_image_filters(self, event=None):
        """Actualiza los filtros de imagen"""
        if self.card_path:
            self.load_optimized_image(self.card_path)

    def reset_image_filters(self):
        """Resetea los filtros de imagen"""
        self.image_brightness.set(1.0)
        self.image_contrast.set(1.0)
        self.image_saturation.set(1.0)
        self.update_image_filters()

    def save_image_filters(self):
        """Guarda los filtros de imagen actuales"""
        self.config_manager.set("image_brightness", self.image_brightness.get())
        self.config_manager.set("image_contrast", self.image_contrast.get())
        self.config_manager.set("image_saturation", self.image_saturation.get())
        self.config_manager.save_config()
        messagebox.showinfo("✅ Guardado", "Filtros de imagen guardados como predeterminados")

    def load_folder(self, folder_path):
        """Carga una carpeta específica"""
        if os.path.exists(folder_path):
            self.show_progress("🔍 Cargando carpeta...")
            
            archivos = [os.path.join(folder_path, f) for f in os.listdir(folder_path) 
                       if f.lower().endswith(".png")]
            
            if archivos:
                self.card_paths = sorted(archivos)
                self.filtered_paths = self.card_paths[:]
                self.current_index = 0
                self.cargar_carta(self.card_paths[0])
                
                # Actualizar configuración
                self.config_manager.set("last_folder", folder_path)
                self.config_manager.add_recent_folder(folder_path)
                self.config_manager.save_config()
                
                # Registrar estadística
                self.db_manager.log_usage("folder_opened", folder_path)
                
                self.show_progress(f"📁 Cargados {len(archivos)} archivos")
                self.after(2000, self.hide_progress)
            else:
                self.hide_progress()
                messagebox.showwarning("⚠️ Advertencia", "No se encontraron archivos PNG en la carpeta.")

    def abrir_carpeta(self, event=None):
        """Abre una carpeta y carga las cartas PNG"""
        carpeta = filedialog.askdirectory(title="Seleccionar carpeta con cartas")
        if carpeta:
            self.load_folder(carpeta)

    def primera_carta(self, event=None):
        """Va a la primera carta"""
        if self.filtered_paths and not self.is_loading:
            self.current_index = 0
            self.cargar_carta(self.filtered_paths[0])

    def ultima_carta(self, event=None):
        """Va a la última carta"""
        if self.filtered_paths and not self.is_loading:
            self.current_index = len(self.filtered_paths) - 1
            self.cargar_carta(self.filtered_paths[-1])

    def carta_anterior(self, event=None):
        """Navega a la carta anterior"""
        if self.filtered_paths and self.current_index > 0 and not self.is_loading:
            self.current_index -= 1
            self.cargar_carta(self.filtered_paths[self.current_index])

    def carta_siguiente(self, event=None):
        """Navega a la carta siguiente"""
        if self.filtered_paths and self.current_index < len(self.filtered_paths) - 1 and not self.is_loading:
            self.current_index += 1
            self.cargar_carta(self.filtered_paths[self.current_index])

    def show_progress(self, message):
        """Muestra un mensaje de progreso"""
        self.progress_var.set(message)
        self.update_idletasks()

    def hide_progress(self):
        """Oculta el mensaje de progreso"""
        self.progress_var.set("")

    def cleanup_image(self):
        """Libera la memoria de la imagen actual"""
        if self.current_image:
            try:
                del self.current_image
                self.current_image = None
            except:
                pass

    def validate_names(self, *args):
        """Valida los nombres en tiempo real"""
        lastname = self.lastname_var.get()
        firstname = self.firstname_var.get()
        nickname = self.nickname_var.get()
        
        forbidden_chars = r'[<>:"/\\|?*]'
        errors = []
        
        # Validar cada campo
        for name, field in [(lastname, "Apellido"), (firstname, "Nombre"), (nickname, "Apodo")]:
            if re.search(forbidden_chars, name):
                errors.append(f"{field} contiene caracteres inválidos")
            if len(name) > 50:
                errors.append(f"{field} demasiado largo (máx. 50 caracteres)")
        
        # Mostrar errores
        if errors:
            self.validation_var.set(" | ".join(errors))
        else:
            self.validation_var.set("")

    def get_translation_key(self, text, target_lang):
        """Genera una clave única para el cache de traducción"""
        content = f"{text}_{target_lang}"
        return hashlib.md5(content.encode()).hexdigest()

    def translate_text_cached(self, text, target_lang):
        """Traduce texto usando cache de base de datos"""
        if not text.strip():
            return ""
            
        cache_key = self.get_translation_key(text, target_lang)
        
        # Intentar obtener del cache
        cached_translation = self.db_manager.get_translation(cache_key)
        if cached_translation:
            return cached_translation
        
        # Traducir si no está en cache
        try:
            translator = GoogleTranslator(source="auto", target=target_lang)
            translation = translator.translate(text)
            
            # Guardar en cache
            self.db_manager.save_translation(cache_key, text, target_lang, translation)
            
            return translation
        except Exception as e:
            logger.error(f"Error en traducción: {e}")
            return text

    def cargar_carta(self, path):
        """Carga una carta con optimizaciones mejoradas"""
        if self.is_loading:
            return
            
        self.is_loading = True
        self.show_progress("⏳ Cargando carta...")
        
        try:
            # Limpiar imagen anterior
            self.cleanup_image()
            
            # Cargar datos de la carta
            self.kc = KoikatuCharaData.load(path)
            self.card_path = path

            # Cargar imagen optimizada
            self.load_optimized_image(path)

            # Mostrar información
            self.display_card_info()

            # Mostrar información del archivo
            self.show_file_info(path)

            # Traducir automáticamente si está habilitado
            if self.auto_translate_var.get():
                threading.Thread(target=self.translate_in_background, daemon=True).start()

            # Actualizar indicadores
            self.update_position_indicator()
            
            # Actualizar título
            filename = os.path.basename(path)
            self.title(f"Koikatsu Card Viewer Pro - {filename}")

            # Registrar estadística
            self.db_manager.log_usage("card_loaded", filename)

        except Exception as e:
            logger.error(f"Error cargando carta: {e}")
            messagebox.showerror("❌ Error", f"No se pudo cargar la carta:\n{e}")
        finally:
            self.is_loading = False
            self.hide_progress()

    def show_file_info(self, path):
        """Muestra información del archivo"""
        try:
            file_size = os.path.getsize(path)
            file_size_mb = file_size / (1024 * 1024)
            
            image_info = self.image_processor.get_image_info(path)
            size_text = f"{image_info.get('size', ('?', '?'))[0]}x{image_info.get('size', ('?', '?'))[1]}"
            
            info_text = f"📄 {file_size_mb:.1f}MB | 🖼️ {size_text} | 📅 {datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M')}"
            self.info_label.config(text=info_text)
        except Exception as e:
            logger.error(f"Error mostrando info de archivo: {e}")

    def load_optimized_image(self, path):
        """Carga la imagen con optimizaciones y filtros"""
        try:
            with Image.open(path) as img:
                # Aplicar filtros
                img = self.image_processor.enhance_image(
                    img,
                    brightness=self.image_brightness.get(),
                    contrast=self.image_contrast.get(),
                    saturation=self.image_saturation.get()
                )
                
                # Redimensionar según calidad configurada
                quality = self.config_manager.get("image_quality", "medium")
                if quality == "high":
                    max_size = (600, 600)
                elif quality == "low":
                    max_size = (200, 200)
                else:  # medium
                    max_size = (400, 400)
                
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                self.current_image = ImageTk.PhotoImage(img)
                self.preview_label.config(image=self.current_image, text="")
                
        except Exception as e:
            logger.error(f"Error cargando imagen: {e}")
            self.preview_label.config(image="", text="❌ Error cargando imagen")

    def display_card_info(self):
        """Muestra la información de la carta"""
        try:
            data = self.kc["Parameter"].data
            lastname = data.get("lastname", "")
            firstname = data.get("firstname", "")
            nickname = data.get("nickname", "")
            
            # Información adicional
            personality = data.get("personality", "Desconocido")
            club = data.get("club", "Sin club")
            
            texto = f"📝 Apellido: {lastname or '(Vacío)'}\n📝 Nombre: {firstname or '(Vacío)'}\n📝 Apodo: {nickname or '(Vacío)'}\n👤 Personalidad: {personality}\n🎯 Club: {club}"
            
            self.text_actual.configure(state='normal')
            self.text_actual.delete("1.0", tk.END)
            self.text_actual.insert(tk.END, texto)
            self.text_actual.configure(state='disabled')

            # Cargar en campos editables
            self.lastname_var.set(lastname)
            self.firstname_var.set(firstname)
            self.nickname_var.set(nickname)
            
        except Exception as e:
            logger.error(f"Error mostrando info de carta: {e}")

    def translate_in_background(self):
        """Traduce los textos en un hilo separado"""
        if not self.kc:
            return
            
        try:
            data = self.kc["Parameter"].data
            lastname = data.get("lastname", "")
            firstname = data.get("firstname", "")
            nickname = data.get("nickname", "")
            
            idioma = self.idioma_destino.get()
            
            # Traducir con cache de BD
            trad_apellido = self.translate_text_cached(lastname, idioma) if lastname else ""
            trad_nombre = self.translate_text_cached(firstname, idioma) if firstname else ""
            trad_apodo = self.translate_text_cached(nickname, idioma) if nickname else ""

            # Actualizar UI en el hilo principal
            self.after(0, self.update_translation_ui, trad_apellido, trad_nombre, trad_apodo)
            
        except Exception as e:
            logger.error(f"Error en traducción en background: {e}")
            self.after(0, self.show_translation_error, str(e))

    def update_translation_ui(self, trad_apellido, trad_nombre, trad_apodo):
        """Actualiza la UI con las traducciones"""
        try:
            resultado = f"📝 Apellido: {trad_apellido}\n📝 Nombre: {trad_nombre}\n📝 Apodo: {trad_apodo}"

            self.text_traducido.configure(state='normal')
            self.text_traducido.delete("1.0", tk.END)
            self.text_traducido.insert(tk.END, resultado)
            self.text_traducido.configure(state='disabled')

            # Guardar traducciones para uso posterior
            self.trad_apellido = trad_apellido
            self.trad_nombre = trad_nombre
            self.trad_apodo = trad_apodo
            
        except Exception as e:
            logger.error(f"Error actualizando UI de traducción: {e}")

    def show_translation_error(self, error_msg):
        """Muestra error de traducción"""
        self.text_traducido.configure(state='normal')
        self.text_traducido.delete("1.0", tk.END)
        self.text_traducido.insert(tk.END, f"❌ Error en traducción:\n{error_msg}")
        self.text_traducido.configure(state='disabled')

    def on_language_change(self, *args):
        """Maneja el cambio de idioma"""
        # Guardar en configuración
        self.config_manager.set("translation_language", self.idioma_destino.get())
        
        if self.kc and self.auto_translate_var.get():
            threading.Thread(target=self.translate_in_background, daemon=True).start()

    def traducir_manual(self, event=None):
        """Traduce manualmente"""
        if self.kc:
            threading.Thread(target=self.translate_in_background, daemon=True).start()

    def usar_traduccion(self):
        """Usa la traducción automática en los campos de edición"""
        if hasattr(self, 'trad_apellido') and hasattr(self, 'trad_nombre'):
            self.lastname_var.set(self.trad_apellido)
            self.firstname_var.set(self.trad_nombre)
            if hasattr(self, 'trad_apodo'):
                self.nickname_var.set(self.trad_apodo)
            messagebox.showinfo("✅ Aplicado", "Traducción aplicada a los campos de edición")

    def copiar_traduccion(self, event=None):
        """Copia la traducción al portapapeles"""
        try:
            texto = self.text_traducido.get("1.0", tk.END).strip()
            if texto and not texto.startswith("❌"):
                pyperclip.copy(texto)
                messagebox.showinfo("📋 Copiado", "Traducción copiada al portapapeles")
            else:
                messagebox.showwarning("⚠️ Advertencia", "No hay traducción válida para copiar")
        except Exception as e:
            logger.error(f"Error copiando traducción: {e}")
            messagebox.showerror("❌ Error", f"No se pudo copiar:\n{e}")

    def guardar_cambios(self, event=None):
        """Guarda los cambios en la carta con respaldo automático"""
        if not self.kc or not self.card_path:
            messagebox.showwarning("⚠️ Advertencia", "Primero carga una carta para editar")
            return
            
        # Validar antes de guardar
        if self.validation_var.get():
            messagebox.showerror("❌ Error", f"Corrige los errores antes de guardar:\n{self.validation_var.get()}")
            return

        self.show_progress("💾 Guardando cambios...")
        
        try:
            nuevo_apellido = self.lastname_var.get().strip()
            nuevo_nombre = self.firstname_var.get().strip()
            nuevo_apodo = self.nickname_var.get().strip()

            if not nuevo_apellido and not nuevo_nombre:
                messagebox.showwarning("⚠️ Advertencia", "Ingresa al menos un nombre o apellido")
                return

            # Crear respaldo si está habilitado
            if self.config_manager.get("backup_enabled", True):
                backup_path = self.backup_manager.create_backup(self.card_path)
                if backup_path:
                    self.show_progress("🔄 Respaldo creado, guardando...")

            # Actualizar datos
            self.kc["Parameter"]["lastname"] = nuevo_apellido
            self.kc["Parameter"]["firstname"] = nuevo_nombre
            self.kc["Parameter"]["nickname"] = nuevo_apodo or f"{nuevo_nombre} {nuevo_apellido}".strip() or "SinNombre"

            # Generar nombre de archivo seguro
            base_nombre = f"{nuevo_nombre} {nuevo_apellido}".strip().replace("  ", " ")
            base_nombre = re.sub(r'[<>:"/\\|?*]', '', base_nombre)
            
            if not base_nombre:
                base_nombre = "SinNombre"
                
            nombre_archivo = base_nombre + ".png"
            dir_actual = os.path.dirname(self.card_path)
            nuevo_path = os.path.join(dir_actual, nombre_archivo)

            # Evitar sobreescritura
            contador = 1
            while os.path.exists(nuevo_path) and nuevo_path != self.card_path:
                nombre_archivo = f"{base_nombre} ({contador}).png"
                nuevo_path = os.path.join(dir_actual, nombre_archivo)
                contador += 1

            # Guardar
            self.kc.save(nuevo_path)

            # Actualizar referencias si cambió el nombre
            if nuevo_path != self.card_path:
                # Eliminar archivo original
                os.remove(self.card_path)
                
                # Actualizar listas
                old_index = self.card_paths.index(self.card_path)
                self.card_paths[old_index] = nuevo_path
                
                if self.card_path in self.filtered_paths:
                    filter_index = self.filtered_paths.index(self.card_path)
                    self.filtered_paths[filter_index] = nuevo_path
                
                self.card_path = nuevo_path

            # Registrar estadística
            self.db_manager.log_usage("card_saved", os.path.basename(nuevo_path))

            self.hide_progress()
            messagebox.showinfo(
                "✅ Guardado Exitoso",
                f"Carta guardada como:\n{os.path.basename(nuevo_path)}\n\n"
                "✅ Cambios aplicados correctamente\n"
                "💡 Tip: Recuerda importar la carta en Koikatsu"
            )

        except Exception as e:
            logger.error(f"Error guardando cambios: {e}")
            self.hide_progress()
            messagebox.showerror("❌ Error", f"No se pudo guardar:\n{e}")

    def limpiar_campos(self, event=None):
        """Limpia los campos de edición"""
        self.lastname_var.set("")
        self.firstname_var.set("")
        self.nickname_var.set("")

    def mostrar_configuracion(self):
        """Muestra la ventana de configuración"""
        config_window = tk.Toplevel(self)
        config_window.title("⚙️ Configuración")
        config_window.geometry("400x500")
        config_window.configure(bg="#1a1a1a")
        config_window.transient(self)
        config_window.grab_set()

        # Configuración de imagen
        img_frame = tk.LabelFrame(config_window, text="🖼️ Imagen", bg="#1a1a1a", fg="white")
        img_frame.pack(fill="x", padx=10, pady=5)

        quality_var = tk.StringVar(value=self.config_manager.get("image_quality", "medium"))
        tk.Label(img_frame, text="Calidad de imagen:", bg="#1a1a1a", fg="white").pack(anchor="w")
        for quality in ["low", "medium", "high"]:
            tk.Radiobutton(img_frame, text=quality.capitalize(), variable=quality_var, 
                          value=quality, bg="#1a1a1a", fg="white", selectcolor="#333").pack(anchor="w")

        # Configuración de respaldos
        backup_frame = tk.LabelFrame(config_window, text="💾 Respaldos", bg="#1a1a1a", fg="white")
        backup_frame.pack(fill="x", padx=10, pady=5)

        backup_var = tk.BooleanVar(value=self.config_manager.get("backup_enabled", True))
        tk.Checkbutton(backup_frame, text="Crear respaldos automáticamente", 
                      variable=backup_var, bg="#1a1a1a", fg="white", selectcolor="#333").pack(anchor="w")

        # Configuración de traducción
        trans_frame = tk.LabelFrame(config_window, text="🌐 Traducción", bg="#1a1a1a", fg="white")
        trans_frame.pack(fill="x", padx=10, pady=5)

        auto_trans_var = tk.BooleanVar(value=self.config_manager.get("auto_translate", True))
        tk.Checkbutton(trans_frame, text="Traducción automática", 
                      variable=auto_trans_var, bg="#1a1a1a", fg="white", selectcolor="#333").pack(anchor="w")

        # Botones
        btn_frame = tk.Frame(config_window, bg="#1a1a1a")
        btn_frame.pack(fill="x", padx=10, pady=10)

        def save_config():
            self.config_manager.set("image_quality", quality_var.get())
            self.config_manager.set("backup_enabled", backup_var.get())
            self.config_manager.set("auto_translate", auto_trans_var.get())
            self.auto_translate_var.set(auto_trans_var.get())
            self.config_manager.save_config()
            messagebox.showinfo("✅ Configuración", "Configuración guardada correctamente")
            config_window.destroy()

        tk.Button(btn_frame, text="💾 Guardar", command=save_config).pack(side="left", padx=5)
        tk.Button(btn_frame, text="❌ Cancelar", command=config_window.destroy).pack(side="left", padx=5)

    def limpiar_cache(self):
        """Limpia el cache de traducciones"""
        try:
            conn = sqlite3.connect(self.db_manager.db_file)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM translation_cache")
            conn.commit()
            conn.close()
            messagebox.showinfo("✅ Cache", "Cache de traducciones limpiado correctamente")
        except Exception as e:
            logger.error(f"Error limpiando cache: {e}")
            messagebox.showerror("❌ Error", f"No se pudo limpiar el cache:\n{e}")

    def mostrar_respaldos(self):
        """Muestra la ventana de respaldos"""
        backup_window = tk.Toplevel(self)
        backup_window.title("🗂️ Respaldos")
        backup_window.geometry("600x400")
        backup_window.configure(bg="#1a1a1a")
        backup_window.transient(self)

        # Lista de respaldos
        listbox_frame = tk.Frame(backup_window, bg="#1a1a1a")
        listbox_frame.pack(fill="both", expand=True, padx=10, pady=10)

        scrollbar = tk.Scrollbar(listbox_frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set, 
                            bg="#333", fg="white", font=("Arial", 10))
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

        # Cargar respaldos
        backups = self.backup_manager.get_recent_backups()
        for backup in backups:
            date_str = datetime.fromtimestamp(backup['date']).strftime('%Y-%m-%d %H:%M:%S')
            listbox.insert(tk.END, f"{date_str} - {backup['file']}")

        # Botones
        btn_frame = tk.Frame(backup_window, bg="#1a1a1a")
        btn_frame.pack(fill="x", padx=10, pady=5)

        def restore_backup():
            selection = listbox.curselection()
            if selection:
                backup = backups[selection[0]]
                # Aquí implementarías la lógica de restauración
                messagebox.showinfo("🔄 Restaurar", f"Función de restauración: {backup['file']}")

        tk.Button(btn_frame, text="🔄 Restaurar", command=restore_backup).pack(side="left", padx=5)
        tk.Button(btn_frame, text="❌ Cerrar", command=backup_window.destroy).pack(side="left", padx=5)

    def mostrar_estadisticas(self):
        """Muestra estadísticas de uso"""
        try:
            conn = sqlite3.connect(self.db_manager.db_file)
            cursor = conn.cursor()
            
            # Obtener estadísticas
            cursor.execute("SELECT action, COUNT(*) as count FROM usage_stats GROUP BY action ORDER BY count DESC")
            stats = cursor.fetchall()
            
            cursor.execute("SELECT COUNT(*) FROM translation_cache")
            cache_count = cursor.fetchone()[0]
            
            conn.close()
            
            stats_text = "📊 ESTADÍSTICAS DE USO\n\n"
            stats_text += f"🗂️ Traducciones en cache: {cache_count}\n\n"
            stats_text += "📈 Acciones realizadas:\n"
            
            for action, count in stats:
                stats_text += f"• {action}: {count} veces\n"
            
            messagebox.showinfo("📊 Estadísticas", stats_text)
            
        except Exception as e:
            logger.error(f"Error mostrando estadísticas: {e}")
            messagebox.showerror("❌ Error", f"No se pudieron obtener las estadísticas:\n{e}")

    def mostrar_ayuda(self, event=None):
        """Muestra la ayuda completa"""
        ayuda = """🎮 KOIKATSU CARD VIEWER PRO - AYUDA

⌨️ ATAJOS DE TECLADO:
• Z / ← = Carta anterior
• X / → = Carta siguiente  
• Home = Primera carta
• End = Última carta
• Ctrl+O = Abrir carpeta
• Ctrl+S = Guardar cambios
• Ctrl+T = Traducir manualmente
• Ctrl+C = Copiar traducción
• Ctrl+F = Buscar/Filtrar
• Ctrl+Q = Salir
• Esc = Limpiar campos
• F1 = Esta ayuda

🔧 CARACTERÍSTICAS:
• 🌐 Traducción automática con cache
• 💾 Respaldos automáticos
• 🖼️ Filtros de imagen ajustables
• 🔍 Filtrado y búsqueda
• 📊 Estadísticas de uso
• ⚙️ Configuración personalizable
• 🗂️ Carpetas recientes
• 📋 Validación en tiempo real

💡 CONSEJOS:
• Las traducciones se guardan automáticamente
• Los respaldos se crean antes de cada modificación
• Usa filtros para encontrar cartas específicas
• Ajusta la calidad de imagen según tu preferencia
• Revisa las estadísticas para ver tu actividad"""
        
        messagebox.showinfo("🎮 Ayuda Completa", ayuda)

    def mostrar_acerca_de(self):
        """Muestra información sobre la aplicación"""
        about_text = """🎮 KOIKATSU CARD VIEWER PRO
        
Versión: 2.0.0
Desarrollado con Python y Tkinter

📋 CARACTERÍSTICAS:
• Editor avanzado de cartas Koikatsu
• Traducción automática multiidioma
• Sistema de respaldos integrado
• Filtros de imagen en tiempo real
• Base de datos local para cache
• Interfaz moderna y personalizable

🛠️ TECNOLOGÍAS:
• Python 3.8+
• Tkinter para GUI
• PIL/Pillow para imágenes
• SQLite para almacenamiento
• deep-translator para traducciones
• kkloader para datos de cartas

❤️ ¡Gracias por usar Koikatsu Card Viewer Pro!"""
        
        messagebox.showinfo("ℹ️ Acerca de", about_text)

    def on_closing(self, event=None):
        """Maneja el cierre de la aplicación"""
        # Guardar configuración de ventana
        self.config_manager.set("window_geometry", self.geometry())
        self.config_manager.save_config()
        
        # Registrar cierre
        self.db_manager.log_usage("app_closed")
        
        # Limpiar recursos
        self.cleanup_image()
        
        # Cerrar aplicación
        self.destroy()

if __name__ == "__main__":
    try:
        app = KoikatsuCardViewer()
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        app.mainloop()
    except Exception as e:
        logger.error(f"Error crítico en la aplicación: {e}")
        messagebox.showerror("❌ Error Crítico", f"Error al iniciar la aplicación:\n{e}")
        raise