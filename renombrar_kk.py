import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import logging
import logging.handlers
from threading import Thread
import threading
import queue
from dataclasses import dataclass
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from kkloader import KoikatuCharaData
except ImportError:
    KoikatuCharaData = None


# ─────────────────────────────────────────────
#  Paleta de colores y estilos
# ─────────────────────────────────────────────
COLORS = {
    "bg_dark":       "#0d0f14",
    "bg_panel":      "#13161e",
    "bg_card":       "#1a1e2a",
    "bg_input":      "#1f2435",
    "accent":        "#7c6af7",
    "accent_hover":  "#9585ff",
    "accent_dim":    "#3d3580",
    "success":       "#3dd68c",
    "error":         "#f05e5e",
    "warning":       "#f0b25e",
    "info":          "#5ea8f0",
    "text_primary":  "#e8eaf2",
    "text_secondary":"#7a7f96",
    "text_muted":    "#474d66",
    "border":        "#252a3a",
    "border_active": "#7c6af7",
    "progress_bg":   "#1f2435",
    "progress_fill": "#7c6af7",
}

FONTS = {
    "title":    ("Segoe UI", 18, "bold"),
    "subtitle": ("Segoe UI", 10),
    "label":    ("Segoe UI", 9, "bold"),
    "body":     ("Segoe UI", 9),
    "mono":     ("Cascadia Code", 9),
    "mono_alt": ("Consolas", 9),
    "counter":  ("Segoe UI", 22, "bold"),
    "counter_sm":("Segoe UI", 11),
    "btn":      ("Segoe UI", 9, "bold"),
    "badge":    ("Segoe UI", 8, "bold"),
}


# ─────────────────────────────────────────────
#  Lógica de negocio
# ─────────────────────────────────────────────

class Gender(Enum):
    MALE = 0
    FEMALE = 1


@dataclass
class ProcessingResult:
    success: bool
    original_file: str
    new_path: str = None
    error: str = None


@dataclass
class CharacterData:
    firstname: str
    lastname: str
    sex: int

    @property
    def full_name(self) -> str:
        parts = [self.firstname, self.lastname]
        return " ".join(p for p in parts if p).strip() or "Sin_nombre"


class KoikatsuRenamer:
    VALID_EXTENSIONS = {'.png'}
    FORBIDDEN_CHARS = '<>:"/\\|?*'
    GENDER_FOLDERS = {Gender.MALE.value: "Masculino", Gender.FEMALE.value: "Femenino"}

    def __init__(self):
        self.logger = self._setup_logger()
        self._cache: dict = {}
        self._created_dirs: set = set()
        self._path_lock = threading.Lock()
        self.stats = {"processed": 0, "errors": 0}

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            handler = logging.FileHandler("koikatsu_renamer.log", encoding="utf-8")
            handler.setFormatter(
                logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            )
            mem_handler = logging.handlers.MemoryHandler(
                capacity=50, flushLevel=logging.ERROR, target=handler
            )
            logger.addHandler(mem_handler)
        return logger

    def reset(self):
        self.stats = {"processed": 0, "errors": 0}
        self._cache.clear()
        self._created_dirs.clear()

    def clean_filename(self, name: str) -> str:
        if not name:
            return "Sin_nombre"
        clean = "".join(c for c in name if c not in self.FORBIDDEN_CHARS)
        clean = " ".join(clean.split()).strip()
        return clean[:200] if clean else "Sin_nombre"

    def _ensure_dir(self, path: Path):
        if path not in self._created_dirs:
            path.mkdir(parents=True, exist_ok=True)
            self._created_dirs.add(path)

    def generate_unique_path(self, folder: Path, base_name: str, extension: str) -> Path:
        with self._path_lock:
            candidate = folder / f"{base_name}{extension}"
            if not candidate.exists():
                return candidate
            counter = 1
            while (folder / f"{base_name} ({counter}){extension}").exists():
                counter += 1
            return folder / f"{base_name} ({counter}){extension}"

    def extract_character_data(self, file_path: Path) -> CharacterData:
        cache_key = str(file_path)
        if cache_key in self._cache:
            return self._cache[cache_key]
        try:
            if KoikatuCharaData is None:
                raise ImportError("kkloader no instalado")
            kc = KoikatuCharaData.load(str(file_path))
            param = kc["Parameter"].data
            character = CharacterData(
                param.get("firstname", "").strip(),
                param.get("lastname", "").strip(),
                param.get("sex"),
            )
            self._cache[cache_key] = character
            return character
        except Exception as e:
            self.logger.error(f"Error al leer {file_path}: {e}")
            raise

    def process_file(
        self, file_path: Path, base_folder: Path, use_subfolders: bool
    ) -> ProcessingResult:
        try:
            character = self.extract_character_data(file_path)
            gender_folder = base_folder / self.GENDER_FOLDERS.get(
                character.sex, "Sin_Genero"
            )
            if use_subfolders:
                destination = gender_folder / self.clean_filename(character.full_name)
            else:
                destination = gender_folder

            self._ensure_dir(destination)
            base_name = self.clean_filename(character.full_name)
            new_path = self.generate_unique_path(
                destination, base_name, file_path.suffix
            )
            os.rename(file_path, new_path)
            self.logger.info(f"Procesado: {file_path.name} → {new_path}")
            self.stats["processed"] += 1
            return ProcessingResult(True, file_path.name, str(new_path))

        except Exception as e:
            self.logger.error(f"Error procesando {file_path}: {e}")
            self.stats["errors"] += 1
            return ProcessingResult(False, file_path.name, error=str(e))

    def process_folder(
        self,
        base_folder: Path,
        use_subfolders: bool,
        progress_callback=None,
        workers: int = 2,
    ):
        self.reset()
        valid_files = [
            f
            for f in base_folder.iterdir()
            if f.is_file() and f.suffix.lower() in self.VALID_EXTENSIONS
        ]
        if not valid_files:
            self.logger.warning("No se encontraron archivos válidos")
            return 0, 0

        total = len(valid_files)
        self.logger.info(f"Encontrados {total} archivos válidos")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    self.process_file, f, base_folder, use_subfolders
                ): f
                for f in valid_files
            }
            completed = 0
            for future in as_completed(futures):
                completed += 1
                try:
                    result = future.result()
                except Exception as e:
                    fname = futures[future].name
                    result = ProcessingResult(False, fname, error=str(e))
                if progress_callback:
                    progress_callback(result, completed, total)

        return self.stats["processed"], self.stats["errors"]


# ─────────────────────────────────────────────
#  Hilo de procesamiento
# ─────────────────────────────────────────────

class ProcessingThread(Thread):
    def __init__(
        self,
        renamer: KoikatsuRenamer,
        folder_path: Path,
        use_subfolders: bool,
        workers: int,
        result_queue: queue.Queue,
    ):
        super().__init__(daemon=True)
        self.renamer = renamer
        self.folder_path = folder_path
        self.use_subfolders = use_subfolders
        self.workers = workers
        self.result_queue = result_queue
        self._stop_requested = False

    def run(self):
        try:
            def progress_callback(result, current, total):
                if not self._stop_requested:
                    self.result_queue.put(("progress", (result, current, total)))

            successful, errors = self.renamer.process_folder(
                self.folder_path, self.use_subfolders, progress_callback, self.workers
            )
            if not self._stop_requested:
                self.result_queue.put(("completed", (successful, errors)))
        except Exception as e:
            if not self._stop_requested:
                self.result_queue.put(("error", str(e)))

    def stop(self):
        self._stop_requested = True


# ─────────────────────────────────────────────
#  Widgets personalizados
# ─────────────────────────────────────────────

class DarkEntry(tk.Frame):
    """Entry con borde de color que cambia al enfocar."""

    def __init__(self, parent, textvariable=None, placeholder="", **kwargs):
        super().__init__(parent, bg=COLORS["border"], padx=1, pady=1)
        self.placeholder = placeholder
        self._has_focus = False
        self._textvariable = textvariable or tk.StringVar()

        self.entry = tk.Entry(
            self,
            textvariable=self._textvariable,
            bg=COLORS["bg_input"],
            fg=COLORS["text_primary"],
            insertbackground=COLORS["accent"],
            relief="flat",
            font=FONTS["body"],
            **kwargs,
        )
        self.entry.pack(fill="both", expand=True, padx=6, pady=6)
        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)

    def _on_focus_in(self, _):
        self.config(bg=COLORS["border_active"])

    def _on_focus_out(self, _):
        self.config(bg=COLORS["border"])

    def get(self):
        return self._textvariable.get()

    def set(self, value):
        self._textvariable.set(value)


class ModernButton(tk.Canvas):
    """Botón con fondo sólido, esquinas redondeadas y hover suave."""

    def __init__(self, parent, text="", command=None, style="primary", width=160, height=38, **kwargs):
        bg_color = kwargs.pop(
            "bg",
            parent.cget("bg") if hasattr(parent, "cget") else COLORS["bg_panel"]
        )
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=bg_color,
            highlightthickness=0,
            **kwargs,
        )
        self.command = command
        self.style = style
        self._text = text
        self._width = width
        self._height = height
        self._enabled = True

        self._colors = {
            "primary": {
                "normal": COLORS["accent"],
                "hover":  COLORS["accent_hover"],
                "text":   "#ffffff",
            },
            "secondary": {
                "normal": COLORS["bg_card"],
                "hover":  COLORS["bg_input"],
                "text":   COLORS["text_primary"],
            },
            "danger": {
                "normal": "#5e2a2a",
                "hover":  "#7a3535",
                "text":   COLORS["error"],
            },
        }
        self._draw("normal")
        self.bind("<Enter>",    lambda _: self._on_hover(True))
        self.bind("<Leave>",    lambda _: self._on_hover(False))
        self.bind("<Button-1>", self._on_click)

    def _draw(self, state: str):
        self.delete("all")
        c = self._colors.get(self.style, self._colors["primary"])
        fill = c["hover"] if state == "hover" else c["normal"]
        text_color = c["text"]

        if not self._enabled:
            fill = COLORS["bg_input"]
            text_color = COLORS["text_muted"]

        r = 8
        w, h = self._width, self._height
        self.create_arc( 0,  0, 2*r, 2*r, start=90, extent=90, fill=fill, outline=fill)
        self.create_arc(w-2*r, 0, w, 2*r, start=0, extent=90, fill=fill, outline=fill)
        self.create_arc( 0, h-2*r, 2*r, h, start=180, extent=90, fill=fill, outline=fill)
        self.create_arc(w-2*r, h-2*r, w, h, start=270, extent=90, fill=fill, outline=fill)
        self.create_rectangle(r, 0, w-r, h, fill=fill, outline=fill)
        self.create_rectangle(0, r, w, h-r, fill=fill, outline=fill)
        self.create_text(
            w // 2, h // 2,
            text=self._text,
            fill=text_color,
            font=FONTS["btn"],
        )

    def _on_hover(self, entered: bool):
        if self._enabled:
            self._draw("hover" if entered else "normal")

    def _on_click(self, _):
        if self._enabled and self.command:
            self.command()

    def config_state(self, enabled: bool):
        self._enabled = enabled
        self._draw("normal")

    def config_text(self, text: str):
        self._text = text
        self._draw("normal")


class StatCard(tk.Frame):
    """Tarjeta con número grande y etiqueta."""

    def __init__(self, parent, label="", color=COLORS["accent"], **kwargs):
        super().__init__(parent, bg=COLORS["bg_card"], **kwargs)
        self.config(relief="flat", bd=0)

        # Borde superior de color
        tk.Frame(self, bg=color, height=3).pack(fill="x")

        inner = tk.Frame(self, bg=COLORS["bg_card"])
        inner.pack(fill="both", expand=True, padx=16, pady=12)

        self._value_var = tk.StringVar(value="0")
        tk.Label(
            inner,
            textvariable=self._value_var,
            font=FONTS["counter"],
            bg=COLORS["bg_card"],
            fg=color,
        ).pack(anchor="w")
        tk.Label(
            inner,
            text=label,
            font=FONTS["counter_sm"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
        ).pack(anchor="w")

    def set_value(self, v):
        self._value_var.set(str(v))


class SmoothProgressBar(tk.Canvas):
    """Barra de progreso con gradiente animado."""

    def __init__(self, parent, height=10, **kwargs):
        super().__init__(
            parent,
            height=height,
            bg=COLORS["progress_bg"],
            highlightthickness=0,
            **kwargs,
        )
        self._pct = 0.0
        self._height = height
        self.bind("<Configure>", self._redraw)

    def set_percent(self, pct: float):
        self._pct = max(0.0, min(100.0, pct))
        self._redraw()

    def _redraw(self, _=None):
        self.delete("all")
        w = self.winfo_width()
        if w <= 1:
            return
        h = self._height
        r = h // 2

        # Fondo
        self.create_rectangle(0, 0, w, h, fill=COLORS["progress_bg"], outline="")

        fill_w = int(w * self._pct / 100)
        if fill_w < 1:
            return

        # Relleno redondeado
        if fill_w >= 2 * r:
            self.create_oval(0, 0, 2*r, h, fill=COLORS["progress_fill"], outline="")
            self.create_rectangle(r, 0, fill_w - r, h, fill=COLORS["progress_fill"], outline="")
            self.create_oval(fill_w - 2*r, 0, fill_w, h, fill=COLORS["progress_fill"], outline="")
        else:
            self.create_oval(0, 0, fill_w, h, fill=COLORS["progress_fill"], outline="")


# ─────────────────────────────────────────────
#  Aplicación principal
# ─────────────────────────────────────────────

class ModernGUI:
    LOG_FLUSH_MS = 120
    MAX_LOG_LINES = 1500

    def __init__(self):
        self.renamer = KoikatsuRenamer()
        self.root = tk.Tk()
        self.processing_thread: ProcessingThread = None
        self.result_queue = queue.Queue()
        self._log_buffer: list = []
        self._start_time: datetime = None

        self.folder_var    = tk.StringVar()
        self.subfolder_var = tk.BooleanVar(value=False)
        self.workers_var   = tk.IntVar(value=2)
        self.status_var    = tk.StringVar(value="Listo para procesar")
        self.pct_var       = tk.StringVar(value="0%")
        self.eta_var       = tk.StringVar(value="")

        self._setup_window()
        self._setup_styles()
        self._build_ui()

    # ── ventana ──────────────────────────────

    def _setup_window(self):
        self.root.title("Koikatsu Character Renamer  ·  v5.0")
        w, h = 980, 720
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(860, 600)
        sx = (self.root.winfo_screenwidth()  - w) // 2
        sy = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{sx}+{sy}")
        self.root.configure(bg=COLORS["bg_dark"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

    def _setup_styles(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")

        s.configure(
            "Dark.TCheckbutton",
            background=COLORS["bg_panel"],
            foreground=COLORS["text_primary"],
            font=FONTS["body"],
            focuscolor=COLORS["accent"],
        )
        s.map("Dark.TCheckbutton",
              background=[("active", COLORS["bg_panel"])],
              foreground=[("active", COLORS["accent"])],
              indicatorcolor=[("selected", COLORS["accent"]), ("!selected", COLORS["bg_input"])],
        )

    # ── UI ───────────────────────────────────

    def _build_ui(self):
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        main = tk.Frame(root, bg=COLORS["bg_dark"])
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(2, weight=1)

        self._build_header(main)
        self._build_controls(main)
        self._build_body(main)
        self._build_statusbar(main)

    # ── Cabecera ─────────────────────────────

    def _build_header(self, parent):
        hdr = tk.Frame(parent, bg=COLORS["bg_panel"])
        hdr.grid(row=0, column=0, sticky="ew")

        tk.Frame(hdr, bg=COLORS["accent"], height=3).pack(fill="x")

        inner = tk.Frame(hdr, bg=COLORS["bg_panel"])
        inner.pack(fill="x", padx=28, pady=18)

        left = tk.Frame(inner, bg=COLORS["bg_panel"])
        left.pack(side="left")

        tk.Label(
            left,
            text="Koikatsu Renamer",
            font=FONTS["title"],
            bg=COLORS["bg_panel"],
            fg=COLORS["text_primary"],
        ).pack(anchor="w")
        tk.Label(
            left,
            text="Organiza y renombra tus cartas de personaje automáticamente",
            font=FONTS["subtitle"],
            bg=COLORS["bg_panel"],
            fg=COLORS["text_secondary"],
        ).pack(anchor="w")

        badge = tk.Label(
            inner,
            text=" v5.0 ",
            font=FONTS["badge"],
            bg=COLORS["accent_dim"],
            fg=COLORS["accent_hover"],
            padx=6,
            pady=2,
        )
        badge.pack(side="right", anchor="n")

    # ── Panel de controles ───────────────────

    def _build_controls(self, parent):
        panel = tk.Frame(parent, bg=COLORS["bg_panel"])
        panel.grid(row=1, column=0, sticky="ew", padx=0, pady=0)

        tk.Frame(panel, bg=COLORS["border"], height=1).pack(fill="x")

        inner = tk.Frame(panel, bg=COLORS["bg_panel"])
        inner.pack(fill="x", padx=28, pady=18)
        inner.columnconfigure(1, weight=1)

        # ── Fila 1: Carpeta ──
        tk.Label(
            inner, text="CARPETA DE CARTAS",
            font=FONTS["label"],
            bg=COLORS["bg_panel"],
            fg=COLORS["text_secondary"],
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        self._folder_entry = DarkEntry(inner, textvariable=self.folder_var)
        self._folder_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0, 10))

        self._browse_btn = ModernButton(
            inner, text="📂  Examinar",
            command=self._select_folder,
            style="secondary",
            width=130, height=36,
            bg=COLORS["bg_panel"],
        )
        self._browse_btn.grid(row=1, column=2)

        # ── Fila 2: Opciones ──
        opts = tk.Frame(inner, bg=COLORS["bg_panel"])
        opts.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(16, 0))

        self._subfolder_chk = ttk.Checkbutton(
            opts,
            text="Crear subcarpeta individual por personaje",
            variable=self.subfolder_var,
            style="Dark.TCheckbutton",
            command=self._on_subfolder_toggle,
        )
        self._subfolder_chk.pack(side="left")

        wk_frame = tk.Frame(opts, bg=COLORS["bg_panel"])
        wk_frame.pack(side="right", padx=(20, 0))

        tk.Label(
            wk_frame, text="Hilos paralelos:",
            font=FONTS["body"],
            bg=COLORS["bg_panel"],
            fg=COLORS["text_secondary"],
        ).pack(side="left")

        self._wk_label = tk.Label(
            wk_frame,
            textvariable=self.workers_var,
            font=FONTS["label"],
            bg=COLORS["bg_panel"],
            fg=COLORS["accent"],
            width=2,
        )
        self._wk_label.pack(side="left", padx=(6, 4))

        self._wk_scale = ttk.Scale(
            wk_frame,
            from_=1, to=6,
            variable=self.workers_var,
            orient="horizontal",
            length=100,
            style="Horizontal.TScale",
            command=lambda _: self.workers_var.set(int(float(self.workers_var.get()))),
        )
        self._wk_scale.pack(side="left")

        tk.Label(
            wk_frame,
            text="⚠ HDD: usa 2",
            font=FONTS["badge"],
            bg=COLORS["bg_panel"],
            fg=COLORS["warning"],
        ).pack(side="left", padx=(8, 0))

        # ── Fila 3: Botones ──
        btn_row = tk.Frame(inner, bg=COLORS["bg_panel"])
        btn_row.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(16, 0))

        self._process_btn = ModernButton(
            btn_row, text="▶  Procesar Cartas",
            command=self._start_processing,
            style="primary",
            width=180, height=40,
            bg=COLORS["bg_panel"],
        )
        self._process_btn.pack(side="left", padx=(0, 12))

        self._stop_btn = ModernButton(
            btn_row, text="■  Detener",
            command=self._stop_processing,
            style="danger",
            width=120, height=40,
            bg=COLORS["bg_panel"],
        )
        self._stop_btn.pack(side="left")
        self._stop_btn.config_state(False)

        self._clear_btn = ModernButton(
            btn_row, text="🗑  Limpiar Log",
            command=self._clear_log,
            style="secondary",
            width=130, height=40,
            bg=COLORS["bg_panel"],
        )
        self._clear_btn.pack(side="right")

        # Progreso
        prog_row = tk.Frame(inner, bg=COLORS["bg_panel"])
        prog_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        prog_row.columnconfigure(0, weight=1)

        self._progress = SmoothProgressBar(prog_row, height=10)
        self._progress.grid(row=0, column=0, sticky="ew", padx=(0, 12))

        tk.Label(
            prog_row,
            textvariable=self.pct_var,
            font=FONTS["label"],
            bg=COLORS["bg_panel"],
            fg=COLORS["accent"],
            width=7,
        ).grid(row=0, column=1)

        tk.Label(
            prog_row,
            textvariable=self.eta_var,
            font=FONTS["body"],
            bg=COLORS["bg_panel"],
            fg=COLORS["text_secondary"],
        ).grid(row=0, column=2)

    # ── Cuerpo: stats + log ──────────────────

    def _build_body(self, parent):
        body = tk.Frame(parent, bg=COLORS["bg_dark"])
        body.grid(row=2, column=0, sticky="nsew", padx=20, pady=(16, 8))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        cards_row = tk.Frame(body, bg=COLORS["bg_dark"])
        cards_row.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        for i in range(4):
            cards_row.columnconfigure(i, weight=1)

        specs = [
            ("Encontrados",  COLORS["info"],    "total"),
            ("Procesados",   COLORS["success"], "ok"),
            ("Errores",      COLORS["error"],   "err"),
            ("Tiempo",       COLORS["warning"], "time"),
        ]
        self._cards: dict[str, StatCard] = {}
        for i, (label, color, key) in enumerate(specs):
            card = StatCard(cards_row, label=label, color=color)
            card.grid(row=0, column=i, sticky="nsew", padx=(0, 10) if i < 3 else (0, 0), ipady=4)
            self._cards[key] = card

        log_container = tk.Frame(body, bg=COLORS["bg_card"])
        log_container.grid(row=1, column=0, sticky="nsew")
        log_container.columnconfigure(0, weight=1)
        log_container.rowconfigure(1, weight=1)

        log_hdr = tk.Frame(log_container, bg=COLORS["bg_card"])
        log_hdr.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(10, 6))

        tk.Label(
            log_hdr,
            text="REGISTRO DE ACTIVIDAD",
            font=FONTS["label"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
        ).pack(side="left")

        self._log_count_lbl = tk.Label(
            log_hdr,
            text="0 entradas",
            font=FONTS["badge"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"],
        )
        self._log_count_lbl.pack(side="right")

        try:
            mono = FONTS["mono"]
            tk.font.Font(family=mono[0])
            mono_font = mono
        except Exception:
            mono_font = FONTS["mono_alt"]

        self._log_text = tk.Text(
            log_container,
            bg=COLORS["bg_card"],
            fg=COLORS["text_primary"],
            insertbackground=COLORS["accent"],
            selectbackground=COLORS["accent_dim"],
            relief="flat",
            bd=0,
            font=mono_font,
            wrap="word",
            state="normal",
        )
        scrollbar = tk.Scrollbar(
            log_container,
            orient="vertical",
            command=self._log_text.yview,
            bg=COLORS["bg_card"],
            troughcolor=COLORS["bg_input"],
            activebackground=COLORS["accent"],
            width=12,
        )
        self._log_text.configure(yscrollcommand=scrollbar.set)
        self._log_text.grid(row=1, column=0, sticky="nsew", padx=(14, 0), pady=(0, 10))
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 10), padx=(0, 6))

        self._log_text.tag_configure("success", foreground=COLORS["success"])
        self._log_text.tag_configure("error",   foreground=COLORS["error"])
        self._log_text.tag_configure("info",    foreground=COLORS["info"])
        self._log_text.tag_configure("warning", foreground=COLORS["warning"])
        self._log_text.tag_configure("ts",      foreground=COLORS["text_muted"])
        self._log_text.tag_configure("sep",     foreground=COLORS["text_muted"])

        self._log_count = 0
        self._log("Sistema listo. Selecciona una carpeta para comenzar.", "info")
        self._log("Directorio de log: koikatsu_renamer.log", "info")

    # ── Barra de estado ──────────────────────

    def _build_statusbar(self, parent):
        bar = tk.Frame(parent, bg=COLORS["bg_panel"], height=28)
        bar.grid(row=3, column=0, sticky="ew")
        tk.Frame(bar, bg=COLORS["border"], height=1).pack(fill="x", side="top")

        inner = tk.Frame(bar, bg=COLORS["bg_panel"])
        inner.pack(fill="x", padx=16, pady=4)

        self._status_dot = tk.Label(
            inner, text="●",
            font=FONTS["badge"],
            bg=COLORS["bg_panel"],
            fg=COLORS["success"],
        )
        self._status_dot.pack(side="left", padx=(0, 6))

        tk.Label(
            inner,
            textvariable=self.status_var,
            font=FONTS["body"],
            bg=COLORS["bg_panel"],
            fg=COLORS["text_secondary"],
        ).pack(side="left")

        tk.Label(
            inner,
            text="Koikatsu Character Renamer — HDD Optimizado",
            font=FONTS["badge"],
            bg=COLORS["bg_panel"],
            fg=COLORS["text_muted"],
        ).pack(side="right")

    # ── Helpers de log ───────────────────────

    def _log(self, msg: str, tag: str = ""):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_buffer.append((ts, msg, tag))

    def _flush_log(self):
        if self._log_buffer:
            self._log_text.config(state="normal")

            current_lines = int(self._log_text.index("end-1c").split(".")[0])
            if current_lines > self.MAX_LOG_LINES:
                self._log_text.delete("1.0", f"{current_lines - self.MAX_LOG_LINES}.0")

            for ts, msg, tag in self._log_buffer:
                self._log_text.insert("end", f"[{ts}] ", "ts")
                self._log_text.insert("end", msg + "\n", tag)
                self._log_count += 1

            self._log_buffer.clear()
            self._log_text.see("end")
            self._log_count_lbl.config(text=f"{self._log_count} entradas")

        if self.processing_thread and self.processing_thread.is_alive():
            self.root.after(self.LOG_FLUSH_MS, self._flush_log)

    # ── Acciones ─────────────────────────────

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Selecciona la carpeta de cartas PNG")
        if folder:
            self.folder_var.set(folder)
            self._log(f"Carpeta: {folder}", "info")
            self._flush_log()

    def _on_subfolder_toggle(self):
        if self.subfolder_var.get():
            self._log("Subcarpetas individuales: ACTIVADO", "info")
        else:
            self._log("Subcarpetas individuales: DESACTIVADO", "info")
        self._flush_log()

    def _clear_log(self):
        self._log_text.config(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_count = 0
        self._log_count_lbl.config(text="0 entradas")

    def _start_processing(self):
        folder_path = self.folder_var.get().strip()
        if not folder_path:
            messagebox.showerror("Error", "Por favor selecciona una carpeta.")
            return
        path = Path(folder_path)
        if not path.exists() or not path.is_dir():
            messagebox.showerror("Error", "La carpeta seleccionada no existe.")
            return

        workers = int(self.workers_var.get())
        self._process_btn.config_state(False)
        self._stop_btn.config_state(True)
        self._status_dot.config(fg=COLORS["warning"])

        self._progress.set_percent(0)
        self.pct_var.set("0%")
        self.eta_var.set("")
        self._start_time = datetime.now()

        for key in ("total", "ok", "err"):
            self._cards[key].set_value(0)
        self._cards["time"].set_value("0s")

        mode = "con subcarpetas" if self.subfolder_var.get() else "por género"
        self.status_var.set(f"Procesando {mode} · {workers} hilo(s)...")
        self._log(f"{'─'*55}", "sep")
        self._log(f"Iniciando · {workers} hilo(s) · modo {mode}", "info")

        self.processing_thread = ProcessingThread(
            self.renamer, path, self.subfolder_var.get(), workers, self.result_queue
        )
        self.processing_thread.start()
        self.root.after(self.LOG_FLUSH_MS, self._flush_log)
        self._check_results()

    def _stop_processing(self):
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.stop()
            self._log("Procesamiento detenido por el usuario.", "warning")
            self._flush_log()
        self._reset_ui()

    def _check_results(self):
        try:
            while not self.result_queue.empty():
                msg_type, data = self.result_queue.get_nowait()
                if msg_type == "progress":
                    self._handle_progress(data)
                elif msg_type == "completed":
                    self._handle_completion(data)
                elif msg_type == "error":
                    self._handle_error(data)
        except queue.Empty:
            pass

        if self.processing_thread and self.processing_thread.is_alive():
            self.root.after(80, self._check_results)

    def _handle_progress(self, data):
        result, current, total = data
        pct = (current / total * 100) if total else 0
        self._progress.set_percent(pct)
        self.pct_var.set(f"{pct:.1f}%")
        self._cards["total"].set_value(total)
        self._cards["ok"].set_value(self.renamer.stats["processed"])
        self._cards["err"].set_value(self.renamer.stats["errors"])

        if self._start_time and current > 0:
            elapsed = (datetime.now() - self._start_time).total_seconds()
            eta_s = elapsed / current * (total - current)
            self.eta_var.set(f"ETA {eta_s:.0f}s")
            self._cards["time"].set_value(f"{elapsed:.0f}s")

        self.status_var.set(f"Procesando {current}/{total}…")

        if result.success:
            rel = "/".join(Path(result.new_path).parts[-2:])
            self._log(f"✓  {result.original_file}  →  {rel}", "success")
        else:
            self._log(f"✗  {result.original_file}  —  {result.error}", "error")

    def _handle_completion(self, data):
        successful, errors = data
        elapsed = ""
        if self._start_time:
            s = (datetime.now() - self._start_time).total_seconds()
            elapsed = f"{s:.1f}s"
            self._cards["time"].set_value(elapsed)

        self._progress.set_percent(100)
        self.pct_var.set("100%")
        self.eta_var.set("")
        self._cards["ok"].set_value(successful)
        self._cards["err"].set_value(errors)
        self._status_dot.config(fg=COLORS["success"] if errors == 0 else COLORS["warning"])

        self._log(f"{'─'*55}", "sep")
        self._log(f"COMPLETADO  ·  ✓ {successful} procesados  ·  ✗ {errors} errores  ·  {elapsed}", "info")
        self._log(f"{'─'*55}", "sep")
        self._flush_log()

        self.status_var.set(f"Completado: {successful} ok, {errors} errores · {elapsed}")

        if successful > 0:
            messagebox.showinfo(
                "¡Listo!",
                f"✓  Procesados correctamente: {successful}\n"
                f"✗  Errores: {errors}\n"
                f"⏱  Tiempo total: {elapsed}",
            )
        else:
            messagebox.showwarning("Sin resultados", "No se procesó ningún archivo.")
        self._reset_ui()

    def _handle_error(self, error: str):
        self._log(f"Error crítico: {error}", "error")
        self._flush_log()
        self._status_dot.config(fg=COLORS["error"])
        messagebox.showerror("Error", f"Error durante el procesamiento:\n{error}")
        self._reset_ui()

    def _reset_ui(self):
        self._process_btn.config_state(True)
        self._stop_btn.config_state(False)
        if self.status_var.get().startswith("Procesando"):
            self.status_var.set("Listo para procesar")
            self._status_dot.config(fg=COLORS["success"])

    def _on_closing(self):
        if self.processing_thread and self.processing_thread.is_alive():
            if messagebox.askokcancel("Cerrar", "¿Detener el procesamiento y salir?"):
                self.processing_thread.stop()
                self.processing_thread.join(timeout=1)
                self.root.destroy()
        else:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


# ─────────────────────────────────────────────
#  Entrada
# ─────────────────────────────────────────────

def main():
    try:
        app = ModernGUI()
        app.run()
    except Exception as e:
        logging.error(f"Error crítico: {e}")
        messagebox.showerror("Error crítico", f"No se pudo iniciar la aplicación:\n{e}")


if __name__ == "__main__":
    main()