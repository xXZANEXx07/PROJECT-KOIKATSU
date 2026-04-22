import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import os
import ctypes
import ctypes.wintypes
from datetime import datetime

# ─────────────────────────────────────────────
#  WIN32 — mouse de bajo nivel
#  Necesario para que Koikatsu (Unity) reciba el drag correctamente
#  y para evitar que Windows Explorer abra el archivo al hacer mouseDown.
# ─────────────────────────────────────────────
_u32 = ctypes.windll.user32

MOUSEEVENTF_LEFTDOWN  = 0x0002
MOUSEEVENTF_LEFTUP    = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP   = 0x0010

def _move(x, y):
    _u32.SetCursorPos(int(x), int(y))

def _left_down(x, y):
    _move(x, y)
    _u32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)

def _left_up(x, y):
    _move(x, y)
    _u32.mouse_event(MOUSEEVENTF_LEFTUP,   0, 0, 0, 0)

def _left_click(x, y):
    _move(x, y);  time.sleep(0.05)
    _u32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0);  time.sleep(0.05)
    _u32.mouse_event(MOUSEEVENTF_LEFTUP,   0, 0, 0, 0)

def _right_click(x, y):
    _move(x, y);  time.sleep(0.05)
    _u32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0);  time.sleep(0.05)
    _u32.mouse_event(MOUSEEVENTF_RIGHTUP,   0, 0, 0, 0)

def _get_pos():
    pt = ctypes.wintypes.POINT()
    _u32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def _key(vk):
    """Presionar y soltar una tecla por virtual-key code."""
    _u32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    _u32.keybd_event(vk, 0, 0x0002, 0)   # KEYEVENTF_KEYUP

VK_DELETE = 0x2E
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B

def _win32_drag(sx, sy, dx, dy, steps=40, step_ms=0.018):
    """
    Drag real en bajo nivel.
    - Mueve el cursor al origen.
    - Presiona botón izquierdo.
    - Mueve en 'steps' pasos graduales hasta el destino.
    - Suelta el botón.
    Funciona con Unity/Koikatsu y con Windows Explorer sin abrir el archivo.
    """
    _move(sx, sy)
    time.sleep(0.12)                              # dejar que Explorer enfoque
    _u32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)                              # esperar registro del down

    for step in range(1, steps + 1):
        t   = step / steps
        cx  = int(sx + (dx - sx) * t)
        cy  = int(sy + (dy - sy) * t)
        _move(cx, cy)
        time.sleep(step_ms)

    _move(dx, dy)
    time.sleep(0.1)
    _u32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
DEFAULT_CONFIG = {
    "explorer_card":      {"x": 200, "y": 300},   # carta actual en explorador
    "explorer_next":      {"x": 200, "y": 330},   # siguiente carta (un renglón abajo)
    "game_drop":          {"x": 640, "y": 360},   # zona de drop en el juego
    "btn_camera1":        {"x": 100, "y": 100},
    "btn_create_new":     {"x": 100, "y": 200},
    "btn_select_front":   {"x": 100, "y": 300},
    "btn_take_picture":   {"x": 100, "y": 350},
    "btn_select_id":      {"x": 100, "y": 400},
    "btn_save":           {"x": 100, "y": 500},

    "wait_load":          3.0,
    "wait_camera":        1.5,
    "wait_between_photo": 0.8,
    "wait_take_picture":  1.2,
    "wait_save":          2.0,
    "wait_delete":        0.8,

    "total_cards":        0,
    "processed":          0,
}

CONFIG_FILE = "kk_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
        return cfg
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


# ─────────────────────────────────────────────
#  MOTOR
# ─────────────────────────────────────────────
class AutomationEngine:
    def __init__(self, cfg, log_cb, progress_cb, status_cb):
        self.cfg = cfg
        self.log = log_cb
        self.set_progress = progress_cb
        self.set_status   = status_cb
        self._pause = threading.Event(); self._pause.set()
        self._stop  = threading.Event()

    def pause(self):   self._pause.clear()
    def resume(self):  self._pause.set()
    def stop(self):    self._stop.set(); self._pause.set()

    def _wait(self, key):
        secs     = self.cfg.get(key, 1.0)
        deadline = time.time() + secs
        while time.time() < deadline:
            if self._stop.is_set(): return False
            self._pause.wait()
            time.sleep(0.05)
        return True

    def _c(self, key):
        """Click en coordenada guardada."""
        p = self.cfg[key]
        _left_click(p["x"], p["y"])

    # ── Bucle principal ───────────────────────
    def run(self, total, start=0):
        self.log(f"▶ Inicio — {total} cartas, desde #{start + 1}")
        for i in range(start, total):
            if self._stop.is_set(): self.log("⏹ Detenido."); break
            self._pause.wait()
            self.log(f"── Carta {i+1}/{total} ──")
            self.set_status(f"Carta {i+1}/{total}")
            self.set_progress(i, total)
            try:
                if not self._process(i, total): break
                self.cfg["processed"] = i + 1
                save_config(self.cfg)
                self.log("  ✔ OK")
            except Exception as e:
                self.log(f"  ✘ Error: {e}")
        self.set_progress(total, total)
        self.set_status("Finalizado")
        self.log(f"✅ Listo. Procesadas: {self.cfg['processed']}")

    def _process(self, i, total):
        src  = self.cfg["explorer_card"]
        nxt  = self.cfg["explorer_next"]
        drop = self.cfg["game_drop"]

        # ── 1. Seleccionar carta en Explorer ──────────────────────────────
        # Usamos clic DERECHO para seleccionar el archivo sin abrirlo,
        # luego ESC para cerrar el menú contextual.
        # Así queda seleccionado y el siguiente mouseDown irá a drag, no a abrir.
        self.log("   1. Seleccionar carta (clic derecho + ESC)")
        _right_click(src["x"], src["y"])
        time.sleep(0.3)
        _key(VK_ESCAPE)
        time.sleep(0.2)
        if self._stop.is_set(): return False

        # ── 2. Drag de Explorer → Juego ───────────────────────────────────
        self.log("   2. Drag al juego")
        _win32_drag(src["x"], src["y"], drop["x"], drop["y"])
        if not self._wait("wait_load"): return False

        # ── 3-4. Camera 1 + Create New ────────────────────────────────────
        self.log("   3. Camera 1")
        self._c("btn_camera1")
        if not self._wait("wait_camera"): return False

        self.log("   4. Create New")
        self._c("btn_create_new")
        if not self._wait("wait_camera"): return False

        # ── 5-6. Foto frontal ─────────────────────────────────────────────
        self.log("   5. Seleccionar foto frontal")
        self._c("btn_select_front")
        if not self._wait("wait_between_photo"): return False

        self.log("   6. Take Picture [frontal]")
        self._c("btn_take_picture")
        if not self._wait("wait_take_picture"): return False

        # ── 7-8. Foto credencial ──────────────────────────────────────────
        self.log("   7. Seleccionar foto credencial")
        self._c("btn_select_id")
        if not self._wait("wait_between_photo"): return False

        self.log("   8. Take Picture [credencial]")
        self._c("btn_take_picture")
        if not self._wait("wait_take_picture"): return False

        # ── 9. Save ───────────────────────────────────────────────────────
        self.log("   9. Save")
        self._c("btn_save")
        if not self._wait("wait_save"): return False

        # ── 10. Borrar carta del Explorer ─────────────────────────────────
        self.log("   10. Borrar carta (clic + Delete)")
        _left_click(src["x"], src["y"])
        time.sleep(0.2)
        _key(VK_DELETE)
        time.sleep(0.2)
        _key(VK_RETURN)          # confirmar diálogo si aparece
        if not self._wait("wait_delete"): return False

        # ── 11. Clic en siguiente carta ───────────────────────────────────
        if i < total - 1:
            self.log("   11. Seleccionar siguiente carta")
            _left_click(nxt["x"], nxt["y"])
            time.sleep(0.1)

        return True


# ─────────────────────────────────────────────
#  COLORES
# ─────────────────────────────────────────────
DARK_BG  = "#0f0f14"
PANEL_BG = "#16161f"
ACCENT   = "#7f5af0"
ACCENT2  = "#2cb67d"
TEXT     = "#fffffe"
SUBTEXT  = "#94a1b2"
BTN_BG   = "#242435"
BTN_HOV  = "#2f2f4a"
DANGER   = "#e53170"
WARNING  = "#f9c846"
CAPTURE  = "#d4500a"


# ─────────────────────────────────────────────
#  GUI
# ─────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg     = load_config()
        self.engine  = None
        self.worker  = None
        self._capture_target = None

        self.title("Koikatsu Card Automator")
        self.geometry("960x720")
        self.resizable(False, False)
        self.configure(bg=DARK_BG)
        self._style()
        self._build_ui()

    # ── Estilos ───────────────────────────────
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TNotebook",     background=DARK_BG,  borderwidth=0)
        s.configure("TNotebook.Tab", background=BTN_BG,   foreground=SUBTEXT,
                    padding=[14, 6], font=("Consolas", 10))
        s.map("TNotebook.Tab",
              background=[("selected", PANEL_BG)],
              foreground=[("selected", TEXT)])
        s.configure("TFrame",   background=DARK_BG)
        s.configure("TLabel",   background=DARK_BG, foreground=TEXT, font=("Consolas", 10))
        s.configure("TEntry",   fieldbackground=BTN_BG, foreground=TEXT,
                    insertcolor=TEXT, borderwidth=0)
        s.configure("TSpinbox", fieldbackground=BTN_BG, foreground=TEXT,
                    arrowcolor=ACCENT, borderwidth=0)
        s.configure("Prog.Horizontal.TProgressbar",
                    troughcolor=BTN_BG, background=ACCENT, thickness=8, borderwidth=0)

    # ── Estructura ───────────────────────────
    def _build_ui(self):
        hdr = tk.Frame(self, bg=DARK_BG)
        hdr.pack(fill="x", padx=20, pady=(16, 4))
        tk.Label(hdr, text="⬡ KOIKATSU", bg=DARK_BG, fg=ACCENT,
                 font=("Consolas", 20, "bold")).pack(side="left")
        tk.Label(hdr, text=" CARD AUTOMATOR", bg=DARK_BG, fg=TEXT,
                 font=("Consolas", 20)).pack(side="left")
        tk.Label(hdr, text="v1.3", bg=DARK_BG, fg=SUBTEXT,
                 font=("Consolas", 9)).pack(side="right", pady=6)
        tk.Frame(self, bg=ACCENT, height=1).pack(fill="x", padx=20, pady=(0, 8))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=20)
        t1 = ttk.Frame(nb); t2 = ttk.Frame(nb); t3 = ttk.Frame(nb)
        nb.add(t1, text="  🏠 Principal  ")
        nb.add(t2, text="  🎯 Coordenadas  ")
        nb.add(t3, text="  ⏱ Tiempos  ")
        self._build_main(t1)
        self._build_coords(t2)
        self._build_timing(t3)

        foot = tk.Frame(self, bg=PANEL_BG, height=36)
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)
        self.lbl_status = tk.Label(foot, text="Listo.", bg=PANEL_BG, fg=SUBTEXT,
                                   font=("Consolas", 9), anchor="w")
        self.lbl_status.pack(side="left", padx=14, pady=8)

    # ── Pestaña Principal ─────────────────────
    def _build_main(self, parent):
        tc = tk.Frame(parent, bg=PANEL_BG)
        tc.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(tc, text="Total de cartas en el explorador:", bg=PANEL_BG,
                 fg=SUBTEXT, font=("Consolas", 9)).pack(side="left", padx=10, pady=7)
        self.var_total = tk.IntVar(value=self.cfg.get("total_cards", 0))
        ttk.Spinbox(tc, from_=1, to=99999, width=8,
                    textvariable=self.var_total,
                    font=("Consolas", 11, "bold")).pack(side="left", padx=6)
        tk.Label(tc, text="← número de cartas en el explorador",
                 bg=PANEL_BG, fg=SUBTEXT, font=("Consolas", 8)).pack(side="left", padx=4)

        rf = tk.Frame(parent, bg=DARK_BG)
        rf.pack(fill="x", padx=16, pady=4)
        tk.Label(rf, text="Reanudar desde carta #:", bg=DARK_BG,
                 fg=SUBTEXT, font=("Consolas", 9)).pack(side="left")
        self.var_start = tk.IntVar(value=self.cfg.get("processed", 0))
        ttk.Spinbox(rf, from_=0, to=99999, width=8,
                    textvariable=self.var_start,
                    font=("Consolas", 10)).pack(side="left", padx=6)
        tk.Label(rf, text="(0 = desde el inicio)", bg=DARK_BG,
                 fg=SUBTEXT, font=("Consolas", 8)).pack(side="left", padx=4)

        pf = tk.Frame(parent, bg=DARK_BG)
        pf.pack(fill="x", padx=16, pady=(10, 2))
        self.var_prog = tk.DoubleVar(value=0)
        ttk.Progressbar(pf, variable=self.var_prog, maximum=100, length=900,
                        style="Prog.Horizontal.TProgressbar").pack(fill="x")
        self.lbl_prog = tk.Label(pf, text="0 / 0", bg=DARK_BG, fg=SUBTEXT,
                                 font=("Consolas", 9), anchor="e")
        self.lbl_prog.pack(fill="x")

        ctrl = tk.Frame(parent, bg=DARK_BG)
        ctrl.pack(pady=6)
        self.btn_start = self._btn(ctrl, "▶  INICIAR",  self._start,        color=ACCENT2, width=16)
        self.btn_pause = self._btn(ctrl, "⏸  PAUSAR",   self._toggle_pause, color=WARNING,  width=14)
        self.btn_stop  = self._btn(ctrl, "⏹  DETENER",  self._stop,         color=DANGER,   width=14)
        self.btn_start.pack(side="left", padx=6)
        self.btn_pause.pack(side="left", padx=6)
        self.btn_stop.pack(side="left",  padx=6)
        self.btn_pause.config(state="disabled")
        self.btn_stop.config(state="disabled")

        flow = tk.Frame(parent, bg=PANEL_BG)
        flow.pack(fill="x", padx=16, pady=(4, 6))
        steps = [
            ("R-clic+ESC", SUBTEXT), ("Drag→juego", SUBTEXT),
            ("Camera 1",   ACCENT),  ("Create New", ACCENT),
            ("Sel.Front",  ACCENT2), ("Take Pic",   ACCENT2),
            ("Sel.ID",     WARNING), ("Take Pic",   WARNING),
            ("Save",       DANGER),  ("Delete",     CAPTURE),
            ("→ sig.",     SUBTEXT),
        ]
        for j, (txt, col) in enumerate(steps):
            tk.Label(flow, text=txt, bg=PANEL_BG, fg=col,
                     font=("Consolas", 8, "bold")).pack(side="left", padx=4, pady=5)
            if j < len(steps) - 1:
                tk.Label(flow, text="›", bg=PANEL_BG, fg=SUBTEXT,
                         font=("Consolas", 9)).pack(side="left")

        lf = tk.Frame(parent, bg=DARK_BG)
        lf.pack(fill="both", expand=True, padx=16, pady=(2, 10))
        tk.Label(lf, text="Log:", bg=DARK_BG, fg=SUBTEXT,
                 font=("Consolas", 9), anchor="w").pack(fill="x")
        self.log_text = tk.Text(lf, height=11, bg="#0a0a10", fg=ACCENT2,
                                font=("Consolas", 9), bd=0, wrap="word",
                                insertbackground=TEXT)
        sc = ttk.Scrollbar(lf, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sc.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")

    # ── Pestaña Coordenadas ───────────────────
    def _build_coords(self, parent):
        self.capture_banner = tk.Frame(parent, bg=CAPTURE)
        self.lbl_capture_msg = tk.Label(self.capture_banner, text="",
                                        bg=CAPTURE, fg=TEXT,
                                        font=("Consolas", 10, "bold"))
        self.lbl_capture_msg.pack(padx=14, pady=7)

        instr = tk.Frame(parent, bg=PANEL_BG)
        instr.pack(fill="x", padx=16, pady=(10, 4))
        tk.Label(instr,
                 text="🎯 Pulsa [ Capturar ] → minimiza → haz clic en el punto exacto",
                 bg=PANEL_BG, fg=WARNING,
                 font=("Consolas", 9)).pack(side="left", padx=10, pady=5)
        self.lbl_mouse = tk.Label(instr, text="Cursor: (0, 0)",
                                  bg=PANEL_BG, fg=ACCENT2,
                                  font=("Consolas", 9, "bold"))
        self.lbl_mouse.pack(side="right", padx=10)
        self._track_mouse()

        fields = [
            ("explorer_card",    "🗂  Carta actual  (explorador)",          CAPTURE),
            ("explorer_next",    "🗂  Siguiente carta  (un renglón abajo)", CAPTURE),
            ("game_drop",        "🎮  Drop en el juego",                    ACCENT),
            ("btn_camera1",      "🎥  Camera 1",                            ACCENT),
            ("btn_create_new",   "➕  Create New",                          ACCENT),
            ("btn_select_front", "🖼  Seleccionar foto frontal",            ACCENT2),
            ("btn_take_picture", "📷  Take Picture  (se usa 2 veces)",      ACCENT2),
            ("btn_select_id",    "🪪  Seleccionar foto credencial",         WARNING),
            ("btn_save",         "💾  Save",                                DANGER),
        ]

        self.coord_vars = {}
        canvas = tk.Canvas(parent, bg=DARK_BG, highlightthickness=0)
        sb     = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        sf     = tk.Frame(canvas, bg=DARK_BG)
        sf.bind("<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=sf, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(16, 0), pady=4)
        sb.pack(side="right", fill="y", pady=4)

        for col, (txt, w, anc) in enumerate([
            ("Botón / Punto", 36, "w"), ("X", 7, "c"), ("Y", 7, "c"),
            ("", 13, "c"), ("", 10, "c")
        ]):
            tk.Label(sf, text=txt, bg=DARK_BG, fg=ACCENT,
                     font=("Consolas", 9, "bold"), width=w,
                     anchor=anc).grid(row=0, column=col, pady=(2, 6))

        prev_sec  = None
        row_extra = 0
        for i, (key, label, sec_col) in enumerate(fields):
            if sec_col != prev_sec:
                tk.Frame(sf, bg=sec_col, height=2).grid(
                    row=1 + i + row_extra, column=0, columnspan=5,
                    sticky="ew", pady=(8, 4), padx=4)
                row_extra += 1
                prev_sec = sec_col

            row = 1 + i + row_extra
            tk.Label(sf, text=label, bg=DARK_BG, fg=TEXT,
                     font=("Consolas", 10), width=36, anchor="w").grid(
                row=row, column=0, pady=5, sticky="w")

            vx = tk.IntVar(value=self.cfg.get(key, {}).get("x", 0))
            vy = tk.IntVar(value=self.cfg.get(key, {}).get("y", 0))
            self.coord_vars[key] = (vx, vy)

            ttk.Spinbox(sf, from_=0, to=9999, width=7,
                        textvariable=vx, font=("Consolas", 10)).grid(row=row, column=1, padx=5)
            ttk.Spinbox(sf, from_=0, to=9999, width=7,
                        textvariable=vy, font=("Consolas", 10)).grid(row=row, column=2, padx=5)

            def mk_cap(k=key, xv=vx, yv=vy):
                return lambda: self._start_capture(k, xv, yv)
            def mk_tst(k=key, x=vx, y=vy):
                def _t():
                    _move(x.get(), y.get())
                    self._log(f"🖱 → {k}: ({x.get()}, {y.get()})")
                return _t

            self._btn(sf, "🎯 Capturar", mk_cap(), color=CAPTURE, width=12).grid(
                row=row, column=3, padx=6)
            self._btn(sf, "Probar",     mk_tst(), color=ACCENT,  width=9).grid(
                row=row, column=4, padx=4)

        last_row = 1 + len(fields) + row_extra + 2
        tk.Frame(sf, bg=ACCENT, height=1).grid(
            row=last_row, column=0, columnspan=5, sticky="ew", pady=(12, 6), padx=4)
        self._btn(sf, "💾  Guardar todas las coordenadas",
                  self._save_coords, color=ACCENT2, width=30).grid(
            row=last_row + 1, column=0, columnspan=5, pady=8)

    # ── Captura de clic ───────────────────────
    def _start_capture(self, key, xvar, yvar):
        self._capture_target = (key, xvar, yvar)
        self.lbl_capture_msg.config(
            text=f"🎯 CAPTURANDO: {key}  —  haz clic en el punto  |  ESC = cancelar")
        self.capture_banner.pack(fill="x", padx=16, pady=(6, 2))
        self.bind("<Escape>", self._cancel_capture)
        self.iconify()
        threading.Thread(target=self._listen_click, daemon=True).start()

    def _listen_click(self):
        """Detecta el siguiente clic izquierdo usando GetAsyncKeyState (solo Win32, sin pynput)."""
        time.sleep(0.45)
        VK_LBUTTON = 0x01
        was_up = True
        while True:
            pressed = bool(_u32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
            if pressed and was_up:
                x, y = _get_pos()
                self.after(0, self._capture_done, x, y)
                return
            was_up = not pressed
            time.sleep(0.02)

    def _capture_done(self, x, y):
        if self._capture_target is None: return
        key, xvar, yvar = self._capture_target
        xvar.set(x); yvar.set(y)
        self.cfg[key] = {"x": x, "y": y}
        save_config(self.cfg)
        self._capture_target = None
        self.deiconify()
        self.capture_banner.pack_forget()
        self.unbind("<Escape>")
        self._log(f"✔ {key} → ({x}, {y})")

    def _cancel_capture(self, event=None):
        self._capture_target = None
        self.deiconify()
        self.capture_banner.pack_forget()
        self.unbind("<Escape>")
        self._log("✘ Captura cancelada.")

    # ── Pestaña Tiempos ───────────────────────
    def _build_timing(self, parent):
        tk.Label(parent, text="Tiempos de espera  (segundos)",
                 bg=DARK_BG, fg=SUBTEXT,
                 font=("Consolas", 9)).pack(anchor="w", padx=16, pady=(12, 4))
        fields = [
            ("wait_load",           "⏳  Esperar carga de carta en el juego"),
            ("wait_camera",         "📷  Esperar apertura de cámara / Create New"),
            ("wait_between_photo",  "🖱  Entre seleccionar foto y Take Picture"),
            ("wait_take_picture",   "🖼  Después de Take Picture"),
            ("wait_save",           "💾  Después de Save"),
            ("wait_delete",         "🗑  Después de borrar carta"),
        ]
        self.time_vars = {}
        grid = tk.Frame(parent, bg=DARK_BG)
        grid.pack(padx=16, pady=4)
        for i, (key, label) in enumerate(fields):
            tk.Label(grid, text=label, bg=DARK_BG, fg=TEXT,
                     font=("Consolas", 10), width=50, anchor="w").grid(
                row=i, column=0, pady=8, sticky="w")
            v = tk.DoubleVar(value=self.cfg.get(key, 1.0))
            self.time_vars[key] = v
            ttk.Spinbox(grid, from_=0.1, to=30.0, increment=0.1,
                        width=8, textvariable=v, format="%.1f",
                        font=("Consolas", 10)).grid(row=i, column=1, padx=10)
            tk.Label(grid, text="seg", bg=DARK_BG, fg=SUBTEXT,
                     font=("Consolas", 9)).grid(row=i, column=2)

        tk.Label(parent,
                 text="⚠  Aumenta 'Esperar carga' si el personaje no cambia entre cartas.\n"
                      "   Si el drag no funciona sube los tiempos paso a paso.",
                 bg=DARK_BG, fg=WARNING,
                 font=("Consolas", 9), justify="left").pack(anchor="w", padx=16, pady=10)
        self._btn(parent, "💾  Guardar tiempos", self._save_timing,
                  color=ACCENT2, width=22).pack(pady=6)

    # ── Helpers ──────────────────────────────
    def _btn(self, parent, text, command, color=BTN_BG, width=None):
        kw = dict(text=text, command=command, bg=color, fg=TEXT,
                  font=("Consolas", 10, "bold"), bd=0, relief="flat",
                  activebackground=BTN_HOV, activeforeground=TEXT,
                  cursor="hand2", padx=10, pady=5)
        if width: kw["width"] = width
        return tk.Button(parent, **kw)

    def _track_mouse(self):
        try:
            x, y = _get_pos()
            self.lbl_mouse.config(text=f"Cursor: ({x}, {y})")
        except Exception:
            pass
        self.after(150, self._track_mouse)

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")

    def _set_progress(self, done, total):
        if total == 0: return
        pct = (done / total) * 100
        self.var_prog.set(pct)
        self.lbl_prog.config(text=f"{done} / {total}  ({pct:.1f}%)")

    def _set_status(self, msg):
        self.lbl_status.config(text=msg)

    # ── Acciones ─────────────────────────────
    def _save_coords(self):
        for key, (vx, vy) in self.coord_vars.items():
            self.cfg[key] = {"x": vx.get(), "y": vy.get()}
        save_config(self.cfg)
        self._log("💾 Coordenadas guardadas.")

    def _save_timing(self):
        for key, v in self.time_vars.items():
            self.cfg[key] = round(v.get(), 1)
        save_config(self.cfg)
        self._log("💾 Tiempos guardados.")

    def _start(self):
        total = self.var_total.get()
        if total <= 0:
            messagebox.showwarning("Atención", "Pon el número total de cartas.")
            return
        self._save_coords()
        self._save_timing()
        self.cfg["total_cards"] = total
        save_config(self.cfg)

        start_idx = max(0, self.var_start.get())
        self.engine = AutomationEngine(
            cfg=self.cfg,
            log_cb      = lambda m: self.after(0, self._log, m),
            progress_cb = lambda d, t: self.after(0, self._set_progress, d, t),
            status_cb   = lambda s: self.after(0, self._set_status, s),
        )
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_stop.config(state="normal")

        self.worker = threading.Thread(
            target=self.engine.run,
            args=(total, start_idx),
            daemon=True)
        self.worker.start()
        self._log(f"🚀 {total} cartas desde #{start_idx + 1}")
        self._monitor_worker()

    def _monitor_worker(self):
        if self.worker and self.worker.is_alive():
            self.after(500, self._monitor_worker)
        else:
            self.btn_start.config(state="normal")
            self.btn_pause.config(state="disabled")
            self.btn_stop.config(state="disabled")

    def _toggle_pause(self):
        if not self.engine: return
        if self.btn_pause.cget("text").startswith("⏸"):
            self.engine.pause()
            self.btn_pause.config(text="▶  REANUDAR", bg=ACCENT2)
            self._log("⏸ Pausado.")
        else:
            self.engine.resume()
            self.btn_pause.config(text="⏸  PAUSAR", bg=WARNING)
            self._log("▶ Reanudado.")

    def _stop(self):
        if self.engine:
            self.engine.stop()
            self.btn_pause.config(text="⏸  PAUSAR", bg=WARNING, state="disabled")
            self.btn_stop.config(state="disabled")
            self._log("⏹ Detención solicitada...")


# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()