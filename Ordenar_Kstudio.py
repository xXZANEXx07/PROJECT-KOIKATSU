"""
Koikatsu Card Sampler v5
────────────────────────────────────────────────────────────────
• Grid de miniaturas de la carpeta "-"
• Polling cada 1s detecta cambios externos
• Clic              → seleccionar
• Doble clic        → preview ampliado
• R / BackSpace     → regresar carta a subcarpeta origen
• Supr / botón 🗑   → borrar carta + carpeta origen desde el programa
• Botón ⟳ Extraer  → sample_and_move
• Checkbox Top      → ventana siempre visible
• Orden de cartas   → configurable con selector
────────────────────────────────────────────────────────────────
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import shutil, random, json, threading, math
from pathlib import Path
from PIL import Image, ImageTk

# ── Paleta ──────────────────────────────────────────────────────
BG       = "#0b0c10"
BG2      = "#13141a"
BG3      = "#1c1e2a"
FG       = "#e8eaf0"
FG_DIM   = "#555e7a"
ACCENT   = "#e94560"
OK       = "#4caf50"
WARN     = "#ff9800"
SEL_BOR  = "#e94560"
CARD_BG  = "#161825"
FONT_M   = ("Consolas", 9)
FONT_B   = ("Consolas", 9, "bold")
FONT_L   = ("Consolas", 12, "bold")
FONT_S   = ("Consolas", 8)

# ── Constantes ──────────────────────────────────────────────────
DEST_FOLDER   = "-"
REGISTRY_FILE = ".kk_sampler_registry.json"
CARD_EXT      = (".png",)
THUMB_W, THUMB_H = 160, 220
THUMB_PAD        = 8
MIN_COLS         = 2
POLL_MS          = 1000

SORT_OPTIONS = [
    "Carpeta origen A→Z",
    "Carpeta origen Z→A",
    "Nombre A→Z",
    "Nombre Z→A",
    "Tamaño mayor primero",
    "Tamaño menor primero",
    "Fecha modificación nueva",
    "Fecha modificación antigua",
    "Fecha creación nueva",
    "Fecha creación antigua",
    "Columnas (original)",
]

# ── Lógica ──────────────────────────────────────────────────────

def load_registry(base: Path) -> dict:
    p = base / REGISTRY_FILE
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_registry(base: Path, reg: dict):
    (base / REGISTRY_FILE).write_text(
        json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")

def get_subfolders(base: Path) -> list:
    return [p for p in base.iterdir() if p.is_dir() and p.name != DEST_FOLDER]

def get_cards_in(folder: Path) -> list:
    return [f for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in CARD_EXT]

def sort_cards(cards: list, mode: str, registry: dict = None) -> list:
    reg = registry or {}
    if mode == "Carpeta origen A→Z":
        return sorted(cards, key=lambda p: reg.get(p.name, "").lower())
    elif mode == "Carpeta origen Z→A":
        return sorted(cards, key=lambda p: reg.get(p.name, "").lower(), reverse=True)
    elif mode == "Nombre A→Z":
        return sorted(cards, key=lambda p: p.name.lower())
    elif mode == "Nombre Z→A":
        return sorted(cards, key=lambda p: p.name.lower(), reverse=True)
    elif mode == "Tamaño mayor primero":
        return sorted(cards, key=lambda p: p.stat().st_size, reverse=True)
    elif mode == "Tamaño menor primero":
        return sorted(cards, key=lambda p: p.stat().st_size)
    elif mode == "Fecha modificación nueva":
        return sorted(cards, key=lambda p: p.stat().st_mtime, reverse=True)
    elif mode == "Fecha modificación antigua":
        return sorted(cards, key=lambda p: p.stat().st_mtime)
    elif mode == "Fecha creación nueva":
        return sorted(cards, key=lambda p: p.stat().st_ctime, reverse=True)
    elif mode == "Fecha creación antigua":
        return sorted(cards, key=lambda p: p.stat().st_ctime)
    else:  # "Columnas (original)"
        return sorted(cards, key=lambda p: p.name.lower())

def sample_and_move(base: Path):
    dest = base / DEST_FOLDER
    dest.mkdir(exist_ok=True)
    reg = load_registry(base)
    results, warnings = [], []
    for folder in sorted(get_subfolders(base)):
        cards = get_cards_in(folder)
        if not cards:
            warnings.append(f"Sin cartas: {folder.name}")
            continue
        chosen = random.choice(cards)
        dst = dest / chosen.name
        if dst.exists():
            warnings.append(f"Ya existe, omitida: {chosen.name}")
            continue
        shutil.move(str(chosen), str(dst))
        reg[dst.name] = chosen.parent.name
        results.append((chosen, dst))
    save_registry(base, reg)
    return results, warnings

def revert_card(base: Path, card_name: str) -> tuple:
    reg = load_registry(base)
    if card_name not in reg:
        return False, f'"{card_name}" no está en el registro.'
    origin_name = reg[card_name]
    origin_dir  = base / origin_name
    src = base / DEST_FOLDER / card_name
    if not src.exists():
        return False, f'"{card_name}" no está en "-".'
    if not origin_dir.exists():
        return False, f'Carpeta origen "{origin_name}" no existe.'
    shutil.move(str(src), str(origin_dir / card_name))
    del reg[card_name]
    save_registry(base, reg)
    return True, f'✓ Regresada → "{origin_name}"'

def delete_card_and_origin(base: Path, card_name: str) -> tuple:
    reg = load_registry(base)
    if card_name not in reg:
        return False, f'"{card_name}" no está en el registro.'
    origin_name = reg[card_name]
    src = base / DEST_FOLDER / card_name
    if src.exists():
        src.unlink()
    origin_dir = base / origin_name
    if origin_dir.exists():
        shutil.rmtree(str(origin_dir))
    del reg[card_name]
    save_registry(base, reg)
    return True, f'🗑 "{card_name}" + carpeta "{origin_name}" eliminadas.'

def delete_origin_only(base: Path, card_name: str) -> tuple:
    reg = load_registry(base)
    if card_name not in reg:
        return False, f'"{card_name}" no está en el registro (nada que limpiar).'
    origin_name = reg[card_name]
    origin_dir  = base / origin_name
    if origin_dir.exists():
        shutil.rmtree(str(origin_dir))
    del reg[card_name]
    save_registry(base, reg)
    return True, f'🗑 Carpeta "{origin_name}" eliminada (carta borrada externamente).'

# ── Miniatura ────────────────────────────────────────────────────

class CardThumb(tk.Frame):
    def __init__(self, master, card_path: Path, on_select, on_preview, **kw):
        super().__init__(master, bg=CARD_BG, cursor="hand2",
                         highlightthickness=2, highlightbackground=CARD_BG, **kw)
        self.card_path = card_path
        self.on_select = on_select
        self._build(on_preview)

    def _build(self, on_preview):
        try:
            img = Image.open(self.card_path)
            img.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
            bg = Image.new("RGB", (THUMB_W, THUMB_H), (22, 24, 37))
            bg.paste(img, ((THUMB_W - img.width) // 2,
                           (THUMB_H - img.height) // 2))
            self._photo = ImageTk.PhotoImage(bg)
        except Exception:
            self._photo = None

        img_lbl = tk.Label(self, image=self._photo, bg=CARD_BG, bd=0,
                           highlightthickness=0)
        img_lbl.pack()

        short = (self.card_path.name if len(self.card_path.name) <= 22
                 else self.card_path.name[:19] + "…")

        # Tamaño del archivo en KB
        try:
            kb = self.card_path.stat().st_size / 1024
            size_str = f"{kb:.0f} KB"
        except Exception:
            size_str = ""

        tk.Label(self, text=short, bg=CARD_BG, fg=FG_DIM,
                 font=("Consolas", 7), wraplength=THUMB_W).pack(pady=(2, 0))
        tk.Label(self, text=size_str, bg=CARD_BG, fg="#3a4a6a",
                 font=("Consolas", 7)).pack(pady=(0, 4))

        for w in (self, img_lbl):
            w.bind("<Button-1>",        lambda e: self.on_select(self))
            w.bind("<Double-Button-1>", lambda e: on_preview(self.card_path))

    def set_selected(self, val: bool):
        self.configure(highlightbackground=SEL_BOR if val else CARD_BG)

# ── Preview ──────────────────────────────────────────────────────

class PreviewWindow(tk.Toplevel):
    def __init__(self, master, path: Path):
        super().__init__(master)
        self.title(path.name)
        self.configure(bg=BG)
        try:
            img = Image.open(path)
            img.thumbnail((600, 800), Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            tk.Label(self, image=self._photo, bg=BG, bd=0).pack(padx=10, pady=10)
        except Exception:
            tk.Label(self, text="No se pudo cargar.",
                     bg=BG, fg=FG, font=FONT_M).pack(padx=20, pady=20)
        self.bind("<Escape>", lambda _: self.destroy())

# ── App ──────────────────────────────────────────────────────────

class KKSampler(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("KK Card Sampler  v5")
        self.configure(bg=BG)
        self.minsize(400, 480)
        self.geometry("960x700")

        self.base_path: Path | None      = None
        self._selected: CardThumb | None = None
        self._thumbs:   list             = []
        self._known:    set              = set()
        self._poll_job                   = None
        self._resize_job                 = None

        self.var_sort = tk.StringVar(value=SORT_OPTIONS[0])
        self.var_sort.trace_add("write", self._on_sort_change)

        self._build_ui()
        self._bind_keys()

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Dark.TCombobox",
                        fieldbackground=BG3, background=BG3, foreground=FG,
                        selectbackground=BG3, selectforeground=ACCENT,
                        arrowcolor=FG_DIM, bordercolor=BG3,
                        lightcolor=BG3, darkcolor=BG3)
        style.map("Dark.TCombobox",
                  fieldbackground=[("readonly", BG3)],
                  background=[("readonly", BG3)],
                  foreground=[("readonly", FG)])

        hdr = tk.Frame(self, bg=BG2, pady=7)
        hdr.pack(fill="x")
        tk.Label(hdr, text="✦ KK CARD SAMPLER", bg=BG2, fg=ACCENT,
                 font=FONT_L).pack(side="left", padx=12)
        self.var_top = tk.BooleanVar(value=False)
        tk.Checkbutton(hdr, text="Siempre visible", variable=self.var_top,
                       bg=BG2, fg=FG_DIM, selectcolor=BG3,
                       activebackground=BG2, activeforeground=FG,
                       font=FONT_S, bd=0, cursor="hand2",
                       command=lambda: self.wm_attributes(
                           "-topmost", self.var_top.get())
                       ).pack(side="right", padx=10)

        fbar = tk.Frame(self, bg=BG3, pady=5)
        fbar.pack(fill="x")
        self._mkbtn(fbar, "📁 Carpeta…", self._pick_folder
                    ).pack(side="left", padx=8)
        self._mkbtn(fbar, "⟳ Extraer", self._on_sample
                    ).pack(side="left", padx=4)
        self.lbl_path = tk.Label(fbar, text="(ninguna)", bg=BG3, fg=FG_DIM,
                                 font=FONT_S, anchor="w")
        self.lbl_path.pack(side="left", padx=10, fill="x", expand=True)

        abar = tk.Frame(self, bg=BG2, pady=5)
        abar.pack(fill="x")
        for text, cmd, bg, abg in [
            ("↩ Regresar  [R]",  self._act_revert, "#0f3460", "#1a4f8a"),
            ("🗑 Borrar  [Del]", self._act_delete, "#3b0a1a", "#6b1030"),
        ]:
            self._mkbtn(abar, text, cmd, bg=bg, active=abg
                        ).pack(side="left", padx=(8, 4))

        sort_frame = tk.Frame(abar, bg=BG2)
        sort_frame.pack(side="left", padx=(12, 4))
        tk.Label(sort_frame, text="Orden:", bg=BG2, fg=FG_DIM,
                 font=FONT_S).pack(side="left", padx=(0, 4))
        self.cmb_sort = ttk.Combobox(
            sort_frame, textvariable=self.var_sort,
            values=SORT_OPTIONS, state="readonly",
            width=22, style="Dark.TCombobox", font=FONT_S,
        )
        self.cmb_sort.pack(side="left")

        self.lbl_sel = tk.Label(abar, text="", bg=BG2, fg=ACCENT,
                                font=FONT_B, anchor="e")
        self.lbl_sel.pack(side="right", padx=10, fill="x", expand=True)

        sf = tk.Frame(self, bg=BG, pady=2)
        sf.pack(fill="x")
        self.lbl_stats = tk.Label(sf, text="", bg=BG, fg=FG_DIM, font=FONT_S)
        self.lbl_stats.pack(side="right", padx=10)

        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(container, bg=BG, bd=0, highlightthickness=0)
        vbar = tk.Scrollbar(container, orient="vertical",
                            command=self.canvas.yview,
                            bg=BG2, troughcolor=BG)
        self.canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.grid_frame = tk.Frame(self.canvas, bg=BG)
        self._cw = self.canvas.create_window(
            (0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>", lambda _: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
            lambda e: self.canvas.itemconfig(self._cw, width=e.width))
        self.canvas.bind("<MouseWheel>",
            lambda e: self.canvas.yview_scroll(-1*(e.delta//120), "units"))

        tk.Frame(self, bg="#1a1d2a", height=1).pack(fill="x")
        lf = tk.Frame(self, bg=BG)
        lf.pack(fill="x", padx=8, pady=4)
        self.log = tk.Text(lf, height=3, bg=BG2, fg=FG, font=FONT_S,
                           relief="flat", state="disabled", wrap="word",
                           highlightthickness=1, highlightbackground="#1e2a3a")
        self.log.pack(fill="x")
        for tag, color in [("ok", OK), ("warn", WARN),
                           ("err", ACCENT), ("info", "#90caf9"), ("dim", FG_DIM)]:
            self.log.tag_configure(tag, foreground=color)

    def _mkbtn(self, parent, text, cmd, bg=ACCENT, active="#c73652"):
        return tk.Button(parent, text=text, command=cmd,
                         bg=bg, fg="white", font=FONT_B,
                         relief="flat", bd=0, padx=9, pady=4,
                         cursor="hand2", activebackground=active,
                         activeforeground="white")

    def _bind_keys(self):
        self.bind("<Delete>",    lambda _: self._act_delete())
        self.bind("<r>",         lambda _: self._act_revert())
        self.bind("<R>",         lambda _: self._act_revert())
        self.bind("<BackSpace>", lambda _: self._act_revert())
        self.bind("<Configure>", self._on_resize)

    def _log(self, msg: str, tag: str = "info"):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _calc_cols(self) -> int:
        w = self.canvas.winfo_width()
        return max(MIN_COLS, w // (THUMB_W + THUMB_PAD * 2))

    def _layout(self):
        mode = self.var_sort.get()
        cols = self._calc_cols()
        n    = len(self._thumbs)
        if mode == "Columnas (original)":
            rows = math.ceil(n / cols) if n else 1
            for i, t in enumerate(self._thumbs):
                t.grid(row=i % rows, column=i // rows,
                       padx=THUMB_PAD, pady=THUMB_PAD)
        else:
            for i, t in enumerate(self._thumbs):
                t.grid(row=i // cols, column=i % cols,
                       padx=THUMB_PAD, pady=THUMB_PAD)

    def _full_rebuild(self):
        for t in self._thumbs:
            t.destroy()
        self._thumbs.clear()
        self._selected = None
        self.lbl_sel.configure(text="")

        if not self.base_path:
            return
        dest = self.base_path / DEST_FOLDER
        if not dest.exists():
            self._known = set()
            self._update_stats()
            return

        cards_raw = get_cards_in(dest)
        self._known = {c.name for c in cards_raw}

        mode     = self.var_sort.get()
        registry = load_registry(self.base_path)
        cards    = sort_cards(cards_raw, mode, registry)

        cols = self._calc_cols()
        n    = len(cards)

        if mode == "Columnas (original)":
            rows = math.ceil(n / cols) if n else 1
            positions = [(i % rows, i // rows) for i in range(n)]
        else:
            positions = [(i // cols, i % cols) for i in range(n)]

        for i, card in enumerate(cards):
            t = CardThumb(self.grid_frame, card,
                          on_select=self._select,
                          on_preview=self._open_preview)
            t.grid(row=positions[i][0], column=positions[i][1],
                   padx=THUMB_PAD, pady=THUMB_PAD)
            self._thumbs.append(t)

        self._update_stats()

    def _on_sort_change(self, *_):
        if not self.base_path:
            return
        self._log(f"Orden: {self.var_sort.get()}", "dim")
        self._full_rebuild()

    def _select(self, thumb: CardThumb):
        if self._selected and self._selected is not thumb:
            self._selected.set_selected(False)
        self._selected = thumb
        thumb.set_selected(True)
        self.lbl_sel.configure(text=f"● {thumb.card_path.name}")
        self.focus_set()

    def _deselect(self):
        if self._selected:
            self._selected.set_selected(False)
        self._selected = None
        self.lbl_sel.configure(text="")

    def _open_preview(self, path: Path):
        PreviewWindow(self, path)

    def _remove_thumb_by_name(self, name: str):
        for t in list(self._thumbs):
            if t.card_path.name == name:
                if self._selected is t:
                    self._deselect()
                t.destroy()
                self._thumbs.remove(t)
                break
        self._layout()
        self._update_stats()

    def _update_stats(self):
        if not self.base_path:
            return
        dest    = self.base_path / DEST_FOLDER
        in_dest = len(get_cards_in(dest)) if dest.exists() else 0
        subs    = len(get_subfolders(self.base_path))
        reg     = len(load_registry(self.base_path))
        self.lbl_stats.configure(
            text=f'subcarpetas: {subs}  |  en "-": {in_dest}  |  reg: {reg}')

    def _on_resize(self, event):
        if event.widget is not self:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(150, self._layout)

    def _start_polling(self):
        if self._poll_job:
            self.after_cancel(self._poll_job)
        self._poll()

    def _poll(self):
        if self.base_path:
            dest = self.base_path / DEST_FOLDER
            current = set()
            if dest.exists():
                current = {f.name for f in dest.iterdir()
                           if f.is_file() and f.suffix.lower() in CARD_EXT}
            added   = current - self._known
            removed = self._known - current
            if added:
                self._known = current
                self._full_rebuild()
                self._log(f"+ {len(added)} carta(s) detectada(s).", "info")
            if removed:
                self._known = current
                for name in sorted(removed):
                    ok, msg = delete_origin_only(self.base_path, name)
                    self._log(msg, "ok" if ok else "warn")
                    self._remove_thumb_by_name(name)
        self._poll_job = self.after(POLL_MS, self._poll)

    def _pick_folder(self):
        folder = filedialog.askdirectory(title="Selecciona la carpeta general")
        if not folder:
            return
        self.base_path = Path(folder)
        self.lbl_path.configure(text=self.base_path.name, fg=FG)
        self._log(f"Carpeta: {self.base_path}", "info")
        self._known = set()
        self._full_rebuild()
        self._start_polling()

    def _on_sample(self):
        if not self.base_path:
            messagebox.showwarning("Sin carpeta",
                                   "Primero selecciona la carpeta general.")
            return
        self._log("Extrayendo cartas…", "dim")
        def worker():
            pairs, warnings = sample_and_move(self.base_path)
            def finish():
                for w in warnings:
                    self._log(f"⚠ {w}", "warn")
                self._log(
                    f"✓ {len(pairs)} carta(s) movidas a \"-\"" if pairs
                    else "No hay cartas nuevas.", "ok" if pairs else "warn")
                self._known = set()
                self._full_rebuild()
            self.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()

    def _act_revert(self):
        if not self._selected:
            self._log("Ninguna carta seleccionada.", "warn")
            return
        name = self._selected.card_path.name
        ok, msg = revert_card(self.base_path, name)
        self._log(msg, "ok" if ok else "err")
        if ok:
            self._known.discard(name)
            self._remove_thumb_by_name(name)

    def _act_delete(self):
        if not self._selected:
            self._log("Ninguna carta seleccionada.", "warn")
            return
        name   = self._selected.card_path.name
        origin = load_registry(self.base_path).get(name, "???")
        if not messagebox.askyesno(
            "Confirmar borrado",
            f'¿Borrar "{name}" y TODA la carpeta\n"{origin}"?\n\nNo se puede deshacer.',
            icon="warning"
        ):
            return
        ok, msg = delete_card_and_origin(self.base_path, name)
        self._log(msg, "ok" if ok else "err")
        if ok:
            self._known.discard(name)
            self._remove_thumb_by_name(name)


if __name__ == "__main__":
    app = KKSampler()
    app.mainloop()