import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import os
import shutil
import platform
import re
import json
import subprocess
from pathlib import Path

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_SUPPORT = True
except ImportError:
    HEIF_SUPPORT = False

try:
    import send2trash
    USE_SEND2TRASH = True
except ImportError:
    USE_SEND2TRASH = False

# Archivo donde se guardan las carpetas configuradas (mismo directorio que el script)
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clasificador_config.json")


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        widget.bind("<Enter>", self.show_tooltip)
        widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tooltip, text=self.text, background="#ffffe0",
                 relief=tk.SOLID, borderwidth=1, font=("Arial", 9)).pack()

    def hide_tooltip(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None


class ImageSorter:
    SUPPORTED_FORMATS = (
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif',
        '.cr2', '.cr3', '.nef', '.arw', '.dng', '.orf', '.rw2', '.pef', '.srw', '.raf',
        '.heic', '.heif', '.heics', '.heifs', '.avif', '.ico', '.svg', '.psd', '.xcf',
        '.exr', '.hdr', '.jp2', '.j2k', '.jpx', '.jfif', '.jpe', '.dib', '.pcx',
        '.ppm', '.pgm', '.pbm', '.pnm'
    )
    LETTERS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    def __init__(self, root):
        self.root = root
        root.title("Clasificador de Imagenes - Version Mejorada")
        root.geometry("980x920")

        self.source_folder = self.left_folder = self.right_folder = ""
        self.custom_folders = {}
        self.letter_folders = {}
        home = str(Path.home())
        self.last_source_dir = self.last_left_dir = self.last_right_dir = self.last_custom_dir = home

        self.image_files = []
        self.current_index = 0
        self.current_image = None
        self.rotation_angle = 0
        self.history = []
        self.stats = {'left': 0, 'right': 0, 'custom': 0, 'deleted': 0, 'skipped': 0}
        self.sort_method = tk.StringVar(value="natural")

        self.create_widgets()
        self.load_config()

        if not HEIF_SUPPORT:
            messagebox.showwarning(
                "Soporte HEIC/HEIF no disponible",
                "Para soportar archivos HEIC/HEIF, instala:\n\npip install pillow-heif\n\n"
                "Los demas formatos funcionaran normalmente."
            )

    # ── Config persistence ─────────────────────────────────────────────────────

    def save_config(self):
        config = {
            "source_folder": self.source_folder,
            "left_folder": self.left_folder,
            "right_folder": self.right_folder,
            "custom_folders": {str(k): v for k, v in self.custom_folders.items()},
            "letter_folders": self.letter_folders,
            "sort_method": self.sort_method.get(),
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[autoguardado] No se pudo guardar config: {e}")

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            return

        self.sort_method.set(config.get("sort_method", "natural"))

        src = config.get("source_folder", "")
        if src and os.path.isdir(src):
            self.source_folder = src
            self.last_source_dir = src
            display_text = self.truncate_path(os.path.basename(src), 40)
            self.source_label.config(text=f"Origen: {display_text}")
            ToolTip(self.source_label, src)

        for attr, label_widget, key in [
            ("left_folder",  self.left_label,  "left_folder"),
            ("right_folder", self.right_label, "right_folder"),
        ]:
            path = config.get(key, "")
            if path and os.path.isdir(path):
                setattr(self, attr, path)
                label_widget.config(text=self.truncate_path(os.path.basename(path), 20))
                ToolTip(label_widget, path)

        for k_str, path in config.get("custom_folders", {}).items():
            if path and os.path.isdir(path):
                k = int(k_str)
                self.custom_folders[k] = path
                folder_name = os.path.basename(path)
                if len(folder_name) > 12:
                    folder_name = folder_name[:9] + "..."
                self.custom_folder_labels[k].config(text=folder_name, fg="black")
                ToolTip(self.custom_folder_labels[k], path)

        for letter, path in config.get("letter_folders", {}).items():
            if path and os.path.isdir(path) and letter in self.letter_folder_labels:
                self.letter_folders[letter] = path
                folder_name = os.path.basename(path)
                if len(folder_name) > 12:
                    folder_name = folder_name[:9] + "..."
                self.letter_folder_labels[letter].config(text=folder_name, fg="black")
                ToolTip(self.letter_folder_labels[letter], path)

        if self.source_folder:
            self.load_images(silent=True)

    # ── Static helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def ordenamiento_natural_key(texto):
        partes = re.split(r'(\d+)', texto)
        resultado = []
        for parte in partes:
            if parte:
                if parte.isdigit():
                    resultado.append((0, int(parte)))
                else:
                    resultado.append((1, parte.lower()))
        return resultado

    @staticmethod
    def truncate_path(path, max_length=30):
        if len(path) <= max_length:
            return path
        parts = path.split(os.sep)
        if len(parts) <= 2:
            return path[:max_length - 3] + "..."
        start, end = parts[0], parts[-1]
        if len(start) + len(end) + 5 > max_length:
            return f"{start}{os.sep}...{os.sep}{end[:max_length - len(start) - 5]}"
        return f"{start}{os.sep}...{os.sep}{end}"

    # ── Widget creation ────────────────────────────────────────────────────────

    def create_widgets(self):
        top_frame = tk.Frame(self.root, bg="#f0f0f0", pady=8)
        top_frame.pack(fill=tk.X)

        source_btn = tk.Button(top_frame, text="Seleccionar Carpeta de Imagenes",
                               command=self.select_source_folder, font=("Arial", 10, "bold"),
                               bg="#4CAF50", fg="white", padx=10, pady=5, cursor="hand2")
        source_btn.pack(pady=4)
        ToolTip(source_btn, "Carpeta donde estan las imagenes a clasificar")

        self.source_label = tk.Label(top_frame, text="No hay carpeta seleccionada",
                                     bg="#f0f0f0", font=("Arial", 9))
        self.source_label.pack()

        sort_frame = tk.LabelFrame(top_frame, text="Metodo de Ordenamiento",
                                   bg="#f0f0f0", font=("Arial", 9, "bold"))
        sort_frame.pack(pady=6, padx=20, fill=tk.X)

        sort_options = tk.Frame(sort_frame, bg="#f0f0f0")
        sort_options.pack(pady=4)

        sorts = [
            ("Natural (1, 2, 10, 100)", "natural",    "Orden logico: 1, 2, 10, 20, 100"),
            ("Alfabetico (1, 10, 2, 20)", "alphabetic", "Orden alfabetico tradicional"),
            ("Fecha de creacion",         "date",       "Del archivo mas antiguo al mas nuevo"),
            ("Sin ordenar",               "none",       "Orden del sistema de archivos"),
        ]
        for text, value, tip in sorts:
            rb = tk.Radiobutton(sort_options, text=text, variable=self.sort_method,
                                value=value, bg="#f0f0f0", font=("Arial", 9))
            rb.pack(side=tk.LEFT, padx=10)
            ToolTip(rb, tip)

        tk.Label(sort_frame, text="Orden natural recomendado para archivos numerados",
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="blue").pack()

        dest_frame = tk.Frame(top_frame, bg="#f0f0f0")
        dest_frame.pack(pady=8)

        left_frame = tk.Frame(dest_frame, bg="#f0f0f0")
        left_frame.pack(side=tk.LEFT, padx=20)
        left_btn = tk.Button(left_frame, text="<- Carpeta Izquierda",
                             command=self.select_left_folder, bg="#2196F3",
                             fg="white", padx=10, pady=5, cursor="hand2")
        left_btn.pack()
        ToolTip(left_btn, "Presiona <- (flecha izquierda) para mover aqui")
        self.left_label = tk.Label(left_frame, text="No configurada",
                                   bg="#f0f0f0", font=("Arial", 8))
        self.left_label.pack()

        right_frame = tk.Frame(dest_frame, bg="#f0f0f0")
        right_frame.pack(side=tk.LEFT, padx=20)
        right_btn = tk.Button(right_frame, text="Carpeta Derecha ->",
                              command=self.select_right_folder, bg="#FF9800",
                              fg="white", padx=10, pady=5, cursor="hand2")
        right_btn.pack()
        ToolTip(right_btn, "Presiona -> (flecha derecha) para mover aqui")
        self.right_label = tk.Label(right_frame, text="No configurada",
                                    bg="#f0f0f0", font=("Arial", 8))
        self.right_label.pack()

        notebook_frame = tk.Frame(self.root, bg="#f0f0f0")
        notebook_frame.pack(fill=tk.X, padx=20, pady=4)

        self.notebook = ttk.Notebook(notebook_frame)
        self.notebook.pack(fill=tk.X)

        # Tab 1 - numeric
        tab_num = tk.Frame(self.notebook, bg="#f0f0f0", pady=6)
        self.notebook.add(tab_num, text="  Carpetas Numericas (1-9)  ")

        tk.Label(tab_num,
                 text="Haz clic en un numero para asignarle una carpeta. Presiona la tecla correspondiente para mover la imagen.",
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#555").pack(pady=(2, 4))

        self.custom_folder_labels = {}
        for row_range in [range(1, 6), range(6, 10)]:
            row = tk.Frame(tab_num, bg="#f0f0f0")
            row.pack(pady=3)
            for i in row_range:
                self._create_numeric_button(row, i)

        # Tab 2 - letters
        tab_letter = tk.Frame(self.notebook, bg="#f0f0f0", pady=6)
        self.notebook.add(tab_letter, text="  Carpetas Alfabeticas (A-Z)  ")

        tk.Label(tab_letter,
                 text="Haz clic en una letra para asignarle una carpeta. Presiona la tecla correspondiente para mover la imagen.",
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#555").pack(pady=(2, 4))

        self.letter_folder_labels = {}
        for row_letters in [self.LETTERS[i:i + 9] for i in range(0, 26, 9)]:
            row = tk.Frame(tab_letter, bg="#f0f0f0")
            row.pack(pady=3)
            for letter in row_letters:
                self._create_letter_button(row, letter)

        extra_row = tk.Frame(tab_letter, bg="#f0f0f0")
        extra_row.pack(pady=3)
        self._create_letter_button(
            extra_row, '#', color="#546E7A",
            tooltip="Presiona # (Shift+3) para mover aqui.\nUsalo para carpetas especiales o que inicien con numero."
        )

        # Image area
        self.filename_label = tk.Label(self.root, text="", font=("Arial", 10, "italic"), fg="#555")
        self.filename_label.pack(pady=2)

        self.counter_label = tk.Label(self.root, text="0 / 0", font=("Arial", 14, "bold"))
        self.counter_label.pack(pady=3)

        self.progress = ttk.Progressbar(self.root, length=800, mode='determinate')
        self.progress.pack(pady=3)

        self.canvas = tk.Canvas(self.root, bg="gray", width=800, height=400)
        self.canvas.pack(pady=6, padx=10)

        # Image action buttons
        img_actions = tk.Frame(self.root, bg="#f0f0f0")
        img_actions.pack(pady=4)

        rotate_btn = tk.Button(
            img_actions, text="Rotar 90 grados",
            command=self.rotate_image,
            bg="#00796B", fg="white", font=("Arial", 9, "bold"),
            padx=12, pady=4, cursor="hand2"
        )
        rotate_btn.pack(side=tk.LEFT, padx=10)
        ToolTip(rotate_btn, "Rota la vista 90 grados en sentido horario (solo vista, no modifica el archivo).\nAtajo: tecla R")

        open_btn = tk.Button(
            img_actions, text="Abrir en Explorador",
            command=self.open_in_explorer,
            bg="#5C6BC0", fg="white", font=("Arial", 9, "bold"),
            padx=12, pady=4, cursor="hand2"
        )
        open_btn.pack(side=tk.LEFT, padx=10)
        ToolTip(open_btn, "Abre la carpeta de la imagen en el explorador de archivos del sistema,\ncon el archivo seleccionado.\nAtajo: tecla E")

        stats_frame = tk.Frame(self.root, bg="#e0e0e0", pady=4)
        stats_frame.pack(fill=tk.X, padx=10)
        self.stats_label = tk.Label(
            stats_frame,
            text="Izq: 0 | Der: 0 | Personal: 0 | Eliminadas: 0 | Saltadas: 0",
            bg="#e0e0e0", font=("Arial", 9)
        )
        self.stats_label.pack()

        bottom_frame = tk.Frame(self.root, bg="#f0f0f0", pady=6)
        bottom_frame.pack(fill=tk.X)
        tk.Label(
            bottom_frame,
            text="CONTROLES:\n<- Izquierda | -> Derecha | abajo/ESPACIO Saltar | arriba Anterior | "
                 "SUPR Eliminar | 1-9 Numericas | A-Z Alfabeticas | # Especiales | "
                 "R Rotar | E Explorador | Ctrl+Z Deshacer",
            bg="#f0f0f0", font=("Arial", 9, "bold"), fg="#d32f2f"
        ).pack()

        bindings = [
            ('<Left>',      lambda e: self.move_image('left')),
            ('<Right>',     lambda e: self.move_image('right')),
            ('<Down>',      lambda e: self.skip_image()),
            ('<space>',     lambda e: self.skip_image()),
            ('<Up>',        lambda e: self.previous_image()),
            ('<Delete>',    lambda e: self.delete_image()),
            ('<Control-z>', lambda e: self.undo_action()),
            ('r',           lambda e: self.rotate_image()),
            ('R',           lambda e: self.rotate_image()),
            ('e',           lambda e: self.open_in_explorer()),
            ('E',           lambda e: self.open_in_explorer()),
        ]
        for key, func in bindings:
            self.root.bind(key, func)

        for i in range(1, 10):
            self.root.bind(str(i), lambda e, num=i: self.move_to_custom_folder(num))

        for letter in self.LETTERS:
            self.root.bind(letter.lower(), lambda e, l=letter: self.move_to_letter_folder(l))
            self.root.bind(letter.upper(), lambda e, l=letter: self.move_to_letter_folder(l))

        self.root.bind('#', lambda e: self.move_to_letter_folder('#'))

    # ── Button factories ───────────────────────────────────────────────────────

    def _create_numeric_button(self, parent, num):
        frame = tk.Frame(parent, bg="#f0f0f0")
        frame.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(frame, text=f"{num}",
                        command=lambda: self.select_custom_folder(num),
                        bg="#9C27B0", fg="white", font=("Arial", 10, "bold"),
                        width=3, height=1, cursor="hand2")
        btn.pack()
        ToolTip(btn, f"Presiona {num} en el teclado para mover aqui")
        label = tk.Label(frame, text="Sin config.", bg="#f0f0f0",
                         font=("Arial", 7), fg="gray", width=12, anchor="w")
        label.pack()
        self.custom_folder_labels[num] = label

    def _create_letter_button(self, parent, letter, color="#1565C0", tooltip=None):
        frame = tk.Frame(parent, bg="#f0f0f0")
        frame.pack(side=tk.LEFT, padx=4)
        btn = tk.Button(frame, text=letter,
                        command=lambda l=letter: self.select_letter_folder(l),
                        bg=color, fg="white", font=("Arial", 10, "bold"),
                        width=3, height=1, cursor="hand2")
        btn.pack()
        ToolTip(btn, tooltip if tooltip else f"Presiona {letter} en el teclado para mover aqui")
        label = tk.Label(frame, text="Sin config.", bg="#f0f0f0",
                         font=("Arial", 7), fg="gray", width=12, anchor="w")
        label.pack()
        self.letter_folder_labels[letter] = label

    # ── Folder selection ───────────────────────────────────────────────────────

    def select_source_folder(self):
        folder = filedialog.askdirectory(title="Selecciona la carpeta con imagenes",
                                         initialdir=self.last_source_dir)
        if folder:
            self.source_folder = folder
            self.last_source_dir = folder
            display_text = self.truncate_path(os.path.basename(folder), 40)
            self.source_label.config(text=f"Origen: {display_text}")
            ToolTip(self.source_label, folder)
            self.save_config()
            self.load_images()

    def select_left_folder(self):
        folder = filedialog.askdirectory(title="Selecciona la carpeta IZQUIERDA",
                                         initialdir=self.last_left_dir)
        if folder:
            self.left_folder = folder
            self.last_left_dir = folder
            self.left_label.config(text=self.truncate_path(os.path.basename(folder), 20))
            ToolTip(self.left_label, folder)
            self.save_config()

    def select_right_folder(self):
        folder = filedialog.askdirectory(title="Selecciona la carpeta DERECHA",
                                         initialdir=self.last_right_dir)
        if folder:
            self.right_folder = folder
            self.last_right_dir = folder
            self.right_label.config(text=self.truncate_path(os.path.basename(folder), 20))
            ToolTip(self.right_label, folder)
            self.save_config()

    def select_custom_folder(self, num):
        folder = filedialog.askdirectory(title=f"Selecciona carpeta para tecla {num}",
                                         initialdir=self.last_custom_dir)
        if folder:
            self.custom_folders[num] = folder
            self.last_custom_dir = folder
            folder_name = os.path.basename(folder)
            if len(folder_name) > 12:
                folder_name = folder_name[:9] + "..."
            self.custom_folder_labels[num].config(text=folder_name, fg="black")
            ToolTip(self.custom_folder_labels[num], folder)
            self.save_config()

    def select_letter_folder(self, letter):
        folder = filedialog.askdirectory(title=f"Selecciona carpeta para tecla '{letter}'",
                                         initialdir=self.last_custom_dir)
        if folder:
            self.letter_folders[letter] = folder
            self.last_custom_dir = folder
            folder_name = os.path.basename(folder)
            if len(folder_name) > 12:
                folder_name = folder_name[:9] + "..."
            self.letter_folder_labels[letter].config(text=folder_name, fg="black")
            ToolTip(self.letter_folder_labels[letter], folder)
            self.save_config()

    # ── Image loading ──────────────────────────────────────────────────────────

    def load_images(self, silent=False):
        self.image_files = []
        skipped_formats = []

        if not self.source_folder:
            return

        files_with_info = []
        try:
            for file in os.listdir(self.source_folder):
                file_lower = file.lower()
                if file_lower.endswith(self.SUPPORTED_FORMATS):
                    if file_lower.endswith(('.heic', '.heif', '.heics', '.heifs')) and not HEIF_SUPPORT:
                        skipped_formats.append(file)
                    else:
                        file_path = os.path.join(self.source_folder, file)
                        try:
                            creation_time = os.path.getctime(file_path)
                        except Exception:
                            creation_time = 0
                        files_with_info.append((file, creation_time))
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer la carpeta:\n{e}")
            return

        sort_method = self.sort_method.get()
        if sort_method == "natural":
            files_with_info.sort(key=lambda x: self.ordenamiento_natural_key(x[0]))
        elif sort_method == "alphabetic":
            files_with_info.sort(key=lambda x: x[0].lower())
        elif sort_method == "date":
            files_with_info.sort(key=lambda x: x[1])

        self.image_files = [f[0] for f in files_with_info]
        self.current_index = 0
        self.rotation_angle = 0
        self.stats = {k: 0 for k in self.stats}
        self.update_stats_display()

        if self.image_files:
            self.show_current_image()
            if not silent:
                preview_count = min(5, len(self.image_files))
                msg = (f"Se encontraron {len(self.image_files)} imagenes\n"
                       f"Ordenamiento: {sort_method}")
                if skipped_formats:
                    msg += f"\n\n{len(skipped_formats)} archivos HEIC/HEIF omitidos"
                msg += (f"\n\nPrimeras {preview_count} imagenes:\n" +
                        "\n".join(self.image_files[:preview_count]))
                messagebox.showinfo("Listo", msg)
        elif not silent:
            messagebox.showwarning("Sin imagenes",
                                   "No se encontraron imagenes compatibles en la carpeta seleccionada")

    def update_stats_display(self):
        self.stats_label.config(
            text=f"Izq: {self.stats['left']} | Der: {self.stats['right']} | "
                 f"Personal: {self.stats['custom']} | Eliminadas: {self.stats['deleted']} | "
                 f"Saltadas: {self.stats['skipped']}"
        )

    def show_current_image(self):
        if not self.image_files:
            return
        if self.current_index >= len(self.image_files):
            self.show_completion_message()
            return

        self.counter_label.config(text=f"{self.current_index + 1} / {len(self.image_files)}")
        self.progress['value'] = (self.current_index / len(self.image_files)) * 100

        current_file = self.image_files[self.current_index]
        file_ext = os.path.splitext(current_file)[1].upper()
        display_name = self.truncate_path(current_file, 60)
        self.filename_label.config(text=f"{display_name} ({file_ext})")

        image_path = os.path.join(self.source_folder, current_file)
        try:
            image = Image.open(image_path)
            if image.mode not in ('RGB', 'RGBA'):
                image = image.convert('RGB')
            if self.rotation_angle:
                image = image.rotate(-self.rotation_angle, expand=True)
            image.thumbnail((800, 400), Image.Resampling.LANCZOS)
            self.current_image = ImageTk.PhotoImage(image)
            self.canvas.delete("all")
            self.canvas.create_image(400, 200, image=self.current_image)
        except Exception as e:
            error_msg = f"No se pudo cargar:\n{current_file}\n\nError: {str(e)}"
            if current_file.lower().endswith(
                    ('.cr2', '.cr3', '.nef', '.arw', '.dng', '.orf', '.rw2', '.pef', '.srw', '.raf')):
                error_msg += "\n\nPara RAW: pip install rawpy imageio"
            messagebox.showerror("Error al cargar imagen", error_msg)
            self.stats['skipped'] += 1
            self.update_stats_display()
            self.current_index += 1
            self.show_current_image()

    def show_completion_message(self):
        messagebox.showinfo(
            "Completado!",
            f"Has clasificado todas las imagenes!\n\nResumen Final:\n"
            f"Izquierda: {self.stats['left']}\nDerecha: {self.stats['right']}\n"
            f"Personalizadas: {self.stats['custom']}\nEliminadas: {self.stats['deleted']}\n"
            f"Saltadas: {self.stats['skipped']}\nTotal procesado: {sum(self.stats.values())}"
        )
        self.canvas.delete("all")
        self.counter_label.config(text="Completado")
        self.filename_label.config(text="Todas las imagenes han sido clasificadas")

    # ── Image actions ──────────────────────────────────────────────────────────

    def rotate_image(self):
        """Rota la imagen 90 grados en sentido horario (solo en pantalla, no modifica el archivo)."""
        if not self.image_files or self.current_index >= len(self.image_files):
            return
        self.rotation_angle = (self.rotation_angle + 90) % 360
        self.show_current_image()

    def open_in_explorer(self):
        """Abre el explorador de archivos del sistema con la imagen actual seleccionada."""
        if not self.image_files or self.current_index >= len(self.image_files):
            return
        image_path = os.path.join(self.source_folder, self.image_files[self.current_index])
        if not os.path.exists(image_path):
            messagebox.showwarning("Archivo no encontrado",
                                   f"No se encontro el archivo:\n{image_path}")
            return
        try:
            system = platform.system()
            if system == "Windows":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(image_path)])
            elif system == "Darwin":
                subprocess.Popen(["open", "-R", image_path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(image_path)])
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el explorador:\n{e}")

    # ── Move helpers ───────────────────────────────────────────────────────────

    def _do_move(self, source_path, dest_path, history_entry, stat_key):
        if os.path.exists(dest_path):
            if not messagebox.askyesno("Archivo existente",
                                       "Ya existe un archivo con este nombre en el destino.\n\nSobrescribir?"):
                return
        try:
            shutil.move(source_path, dest_path)
            self.history.append(history_entry)
            self.stats[stat_key] += 1
            self.update_stats_display()
            self.rotation_angle = 0
            self.current_index += 1
            self.show_current_image()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo mover la imagen:\n{e}")

    def move_image(self, direction):
        if not self.image_files or self.current_index >= len(self.image_files):
            return
        target_folder = self.left_folder if direction == 'left' else self.right_folder
        if not target_folder:
            messagebox.showwarning("Carpeta no configurada",
                                   f"Configura primero la carpeta "
                                   f"{'IZQUIERDA' if direction == 'left' else 'DERECHA'}")
            return
        fname = self.image_files[self.current_index]
        src = os.path.join(self.source_folder, fname)
        dst = os.path.join(target_folder, fname)
        self._do_move(src, dst, {
            'action': 'move', 'direction': direction, 'file': fname,
            'from': src, 'to': dst, 'index': self.current_index
        }, 'left' if direction == 'left' else 'right')

    def move_to_custom_folder(self, folder_num):
        if not self.image_files or self.current_index >= len(self.image_files):
            return
        if folder_num not in self.custom_folders:
            messagebox.showwarning("Carpeta no configurada",
                                   f"Configura primero la carpeta {folder_num}\n\n"
                                   f"Haz clic en el boton {folder_num}")
            return
        fname = self.image_files[self.current_index]
        src = os.path.join(self.source_folder, fname)
        dst = os.path.join(self.custom_folders[folder_num], fname)
        self._do_move(src, dst, {
            'action': 'move_custom', 'folder_num': folder_num, 'file': fname,
            'from': src, 'to': dst, 'index': self.current_index
        }, 'custom')

    def move_to_letter_folder(self, letter):
        if not self.image_files or self.current_index >= len(self.image_files):
            return
        if letter not in self.letter_folders:
            messagebox.showwarning("Carpeta no configurada",
                                   f"Configura primero la carpeta para '{letter}'\n\n"
                                   f"Ve a la pestana Carpetas Alfabeticas y haz clic en el boton {letter}")
            return
        fname = self.image_files[self.current_index]
        src = os.path.join(self.source_folder, fname)
        dst = os.path.join(self.letter_folders[letter], fname)
        self._do_move(src, dst, {
            'action': 'move_letter', 'letter': letter, 'file': fname,
            'from': src, 'to': dst, 'index': self.current_index
        }, 'custom')

    # ── Delete ─────────────────────────────────────────────────────────────────

    def delete_image(self):
        if not self.image_files or self.current_index >= len(self.image_files):
            return
        current_file = self.image_files[self.current_index]
        if not messagebox.askyesno("Confirmar eliminacion",
                                   f"Seguro que quieres eliminar?\n\n{current_file}\n\n"
                                   "Se movera a la papelera del sistema."):
            return
        source_path = os.path.join(self.source_folder, current_file)
        try:
            if platform.system() == 'Windows':
                self.windows_recycle(source_path)
            elif USE_SEND2TRASH:
                send2trash.send2trash(source_path)
            else:
                import tempfile
                trash_folder = os.path.join(tempfile.gettempdir(), "image_sorter_trash")
                os.makedirs(trash_folder, exist_ok=True)
                shutil.move(source_path, os.path.join(trash_folder, current_file))
            self.history.append({'action': 'delete', 'file': current_file,
                                  'path': source_path, 'index': self.current_index})
            self.stats['deleted'] += 1
            self.update_stats_display()
            self.rotation_angle = 0
            self.current_index += 1
            self.show_current_image()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo eliminar:\n{e}")

    def windows_recycle(self, filepath):
        from ctypes import windll, c_wchar_p, c_uint, Structure, byref
        from ctypes.wintypes import HWND, UINT, BOOL

        class SHFILEOPSTRUCTW(Structure):
            _fields_ = [("hwnd", HWND), ("wFunc", UINT), ("pFrom", c_wchar_p), ("pTo", c_wchar_p),
                        ("fFlags", c_uint), ("fAnyOperationsAborted", BOOL),
                        ("hNameMappings", c_uint), ("lpszProgressTitle", c_wchar_p)]

        fileop = SHFILEOPSTRUCTW()
        fileop.hwnd = 0
        fileop.wFunc = 0x0003
        fileop.pFrom = filepath + '\0'
        fileop.pTo = None
        fileop.fFlags = 0x0050
        fileop.fAnyOperationsAborted = False
        fileop.hNameMappings = 0
        fileop.lpszProgressTitle = None
        result = windll.shell32.SHFileOperationW(byref(fileop))
        if result != 0:
            raise Exception(f"Error al mover a papelera (codigo: {result})")

    # ── Navigation ─────────────────────────────────────────────────────────────

    def skip_image(self):
        if not self.image_files or self.current_index >= len(self.image_files):
            return
        self.stats['skipped'] += 1
        self.update_stats_display()
        self.rotation_angle = 0
        self.current_index += 1
        self.show_current_image()

    def previous_image(self):
        if not self.image_files:
            return
        if self.current_index > 0:
            self.rotation_angle = 0
            self.current_index -= 1
            self.show_current_image()
        else:
            messagebox.showinfo("Inicio", "Ya estas en la primera imagen")

    def undo_action(self):
        if not self.history:
            messagebox.showinfo("Sin historial", "No hay acciones para deshacer")
            return
        last_action = self.history.pop()
        try:
            if last_action['action'] in ('move', 'move_custom', 'move_letter'):
                if not os.path.exists(last_action['to']):
                    messagebox.showerror("Error",
                                         "No se puede deshacer: el archivo ya no existe en el destino")
                    return
                shutil.move(last_action['to'], last_action['from'])
                if last_action['action'] == 'move':
                    self.stats['left' if last_action['direction'] == 'left' else 'right'] -= 1
                else:
                    self.stats['custom'] -= 1
                self.rotation_angle = 0
                self.current_index = last_action['index']
                self.show_current_image()
                messagebox.showinfo("Deshecho", "Accion deshecha correctamente")
            elif last_action['action'] == 'delete':
                messagebox.showinfo("Eliminacion",
                                    "Las imagenes eliminadas no se pueden recuperar automaticamente.\n\n"
                                    "Revisa la papelera de reciclaje de tu sistema.")
                self.stats['deleted'] -= 1
            self.update_stats_display()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo deshacer:\n{e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = ImageSorter(root)
    root.mainloop()