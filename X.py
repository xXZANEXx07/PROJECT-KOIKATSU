"""
Gallery-DL  //  X / Twitter Downloader
GUI especializada para descargar contenido de X (Twitter)
Requiere: pip install gallery-dl
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import subprocess
import sys
import os
import queue
import json
import shlex
from pathlib import Path
from datetime import datetime


# ─── Tema ───────────────────────────────────────────────────────────────────────
BG       = "#0a0a0a"
BG2      = "#111111"
BG3      = "#1a1a1a"
BG4      = "#222222"
ACCENT   = "#1d9bf0"       # azul X
ACCENT2  = "#0f6cbd"
SUCCESS  = "#00ba7c"
WARNING  = "#ffad1f"
ERROR    = "#f4212e"
TEXT     = "#e7e9ea"
TEXT_DIM = "#536471"
BORDER   = "#2f3336"
BIRD     = "#1d9bf0"


def make_style():
    s = ttk.Style()
    s.theme_use("clam")
    s.configure("TFrame",       background=BG)
    s.configure("Card.TFrame",  background=BG2, relief="flat")
    s.configure("TLabel",       background=BG,  foreground=TEXT,  font=("Consolas", 10))
    s.configure("Card.TLabel",  background=BG2, foreground=TEXT,  font=("Consolas", 10))
    s.configure("Dim.TLabel",   background=BG2, foreground=TEXT_DIM, font=("Consolas", 9))
    s.configure("TEntry",       fieldbackground=BG3, foreground=TEXT,
                insertcolor=ACCENT, bordercolor=BORDER, relief="flat",
                font=("Consolas", 10))
    s.configure("TButton",      background=ACCENT2, foreground="#fff",
                font=("Consolas", 10, "bold"), relief="flat", borderwidth=0)
    s.map("TButton",
          background=[("active", ACCENT), ("disabled", BG3)],
          foreground=[("disabled", TEXT_DIM)])
    s.configure("TCheckbutton", background=BG2, foreground=TEXT, font=("Consolas", 9))
    s.map("TCheckbutton", background=[("active", BG2)])
    s.configure("TCombobox",    fieldbackground=BG3, foreground=TEXT,
                background=BG3, font=("Consolas", 10))
    s.configure("Horizontal.TProgressbar",
                troughcolor=BG3, background=ACCENT,
                bordercolor=BG3, lightcolor=ACCENT, darkcolor=ACCENT2)
    s.configure("TNotebook",    background=BG, borderwidth=0)
    s.configure("TNotebook.Tab", background=BG3, foreground=TEXT_DIM,
                font=("Consolas", 10), padding=[14, 6])
    s.map("TNotebook.Tab",
          background=[("selected", BG2)],
          foreground=[("selected", ACCENT)])
    s.configure("TScrollbar",   background=BG3, troughcolor=BG,
                bordercolor=BG, arrowcolor=TEXT_DIM)
    s.configure("TSeparator",   background=BORDER)
    return s


# ─── Historial ──────────────────────────────────────────────────────────────────
HISTORY_FILE = Path.home() / ".gdl_twitter_history.json"

def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def save_history(entries):
    try:
        HISTORY_FILE.write_text(
            json.dumps(entries[-300:], indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception:
        pass


# ─── Helpers UI ────────────────────────────────────────────────────────────────
def _entry(parent, var, width=None, placeholder=None):
    kw = dict(textvariable=var, bg=BG3, fg=TEXT, insertbackground=ACCENT,
              relief="flat", font=("Consolas", 10),
              highlightthickness=1, highlightbackground=BORDER,
              highlightcolor=ACCENT)
    if width:
        kw["width"] = width
    e = tk.Entry(parent, **kw)
    if placeholder:
        _placeholder(e, placeholder, var)
    return e

def _placeholder(entry, text, var):
    def _in(ev):
        if entry.get() == text:
            entry.delete(0, "end")
            entry.config(fg=TEXT)
    def _out(ev):
        if not entry.get():
            entry.insert(0, text)
            entry.config(fg=TEXT_DIM)
    entry.insert(0, text)
    entry.config(fg=TEXT_DIM)
    entry.bind("<FocusIn>",  _in)
    entry.bind("<FocusOut>", _out)

def _chk(parent, text, var, detail=""):
    fr = tk.Frame(parent, bg=BG2)
    fr.pack(fill="x", padx=20, pady=2)
    tk.Checkbutton(fr, text=text, variable=var,
                   bg=BG2, fg=TEXT, selectcolor=BG3,
                   activebackground=BG2, activeforeground=ACCENT,
                   font=("Consolas", 9), cursor="hand2").pack(side="left")
    if detail:
        tk.Label(fr, text=detail, bg=BG2, fg=TEXT_DIM,
                 font=("Consolas", 8)).pack(side="left", padx=(6, 0))

def _section(parent, text):
    tk.Label(parent, text=text, bg=BG2, fg=ACCENT,
             font=("Consolas", 10, "bold")).pack(anchor="w", padx=20, pady=(14, 3))
    ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=20, pady=(0, 6))

def _row_entry(parent, label, var, ph=""):
    fr = tk.Frame(parent, bg=BG2)
    fr.pack(fill="x", padx=20, pady=3)
    tk.Label(fr, text=label, bg=BG2, fg=TEXT,
             font=("Consolas", 9), width=28, anchor="w").pack(side="left")
    e = _entry(fr, var)
    e.pack(side="left", fill="x", expand=True, ipady=4)
    if ph:
        _placeholder(e, ph, var)
    return e


# ═══════════════════════════════════════════════════════════════════════════════
class TwitterDLApp(tk.Tk):

    # ── MODOS de descarga disponibles ──────────────────────────────────────────
    MODES = {
        "timeline":    ("Timeline",        "https://x.com/{user}"),
        "media":       ("Solo media",      "https://x.com/{user}/media"),
        "likes":       ("Likes",           "https://x.com/{user}/likes"),
        "bookmarks":   ("Bookmarks",       "https://x.com/i/bookmarks"),
        "tweet":       ("Tweet único",     "https://x.com/{user}/status/{id}"),
        "search":      ("Búsqueda",        "https://x.com/search?q={query}&src=typed_query&f=top"),
        "list":        ("Lista",           "https://x.com/i/lists/{list_id}"),
        "url_manual":  ("URL manual",      ""),
    }

    def __init__(self):
        super().__init__()
        self.title("X Downloader  //  gallery-dl")
        self.geometry("860x700")
        self.minsize(700, 560)
        self.configure(bg=BG)

        self._style   = make_style()
        self._queue   = queue.Queue()
        self._process = None
        self._cancel  = threading.Event()
        self._history = load_history()

        self._build_ui()
        self._poll_queue()
        self.after(100, self._check_gallery_dl)

    # ── Check instalación ──────────────────────────────────────────────────────
    def _check_gallery_dl(self):
        try:
            r = subprocess.run(["gallery-dl", "--version"],
                               capture_output=True, text=True, timeout=5)
            ver = (r.stdout.strip() or r.stderr.strip()).split("\n")[0]
            self._log(f"✓ gallery-dl: {ver}", SUCCESS)
        except FileNotFoundError:
            self._log("✗ gallery-dl no encontrado → pip install gallery-dl", ERROR)
            messagebox.showwarning("gallery-dl no encontrado",
                "Ejecuta en tu terminal:\n\n  pip install gallery-dl\n\nLuego reinicia.")
        except Exception as e:
            self._log(f"✗ Error: {e}", ERROR)

    # ══════════════════════════════════════════════════════════════════════════
    # UI
    # ══════════════════════════════════════════════════════════════════════════
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=BG, pady=10)
        hdr.pack(fill="x", padx=20)

        # Logo X
        tk.Label(hdr, text="𝕏", bg=BG, fg=ACCENT,
                 font=("Consolas", 22, "bold")).pack(side="left")
        tk.Label(hdr, text=" Downloader", bg=BG, fg=TEXT,
                 font=("Consolas", 16, "bold")).pack(side="left")
        tk.Label(hdr, text="  powered by gallery-dl", bg=BG, fg=TEXT_DIM,
                 font=("Consolas", 9)).pack(side="left", padx=(6, 0))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=20)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=20, pady=(10, 0))

        self._tab_main    = ttk.Frame(nb)
        self._tab_auth    = ttk.Frame(nb)
        self._tab_options = ttk.Frame(nb)
        self._tab_history = ttk.Frame(nb)

        nb.add(self._tab_main,    text="  Descargar  ")
        nb.add(self._tab_auth,    text="  Auth / Cookies  ")
        nb.add(self._tab_options, text="  Opciones  ")
        nb.add(self._tab_history, text="  Historial  ")

        self._build_tab_main()
        self._build_tab_auth()
        self._build_tab_options()
        self._build_tab_history()

        # Status bar
        sb = tk.Frame(self, bg=BG3, height=26)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self._status_var = tk.StringVar(value="Listo")
        tk.Label(sb, textvariable=self._status_var,
                 bg=BG3, fg=TEXT_DIM, font=("Consolas", 9),
                 anchor="w", padx=12).pack(fill="both", expand=True)

    # ── Tab principal ──────────────────────────────────────────────────────────
    def _build_tab_main(self):
        f = self._tab_main
        f.configure(style="Card.TFrame")

        # ── Modo de descarga
        mode_fr = tk.Frame(f, bg=BG2)
        mode_fr.pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(mode_fr, text="Modo de descarga", bg=BG2, fg=TEXT_DIM,
                 font=("Consolas", 9)).pack(anchor="w")

        self._mode_var = tk.StringVar(value="media")
        mode_inner = tk.Frame(f, bg=BG2)
        mode_inner.pack(fill="x", padx=16, pady=(2, 8))

        mode_labels = {k: v[0] for k, v in self.MODES.items()}
        self._mode_combo = ttk.Combobox(
            mode_inner, textvariable=self._mode_var,
            values=list(mode_labels.values()),
            state="readonly", font=("Consolas", 10), width=22
        )
        # mapear label → key
        self._label_to_key = {v[0]: k for k, v in self.MODES.items()}
        self._mode_combo.set("Solo media")
        self._mode_combo.pack(side="left")
        self._mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)

        self._mode_hint = tk.Label(mode_inner, text="", bg=BG2, fg=TEXT_DIM,
                                    font=("Consolas", 8))
        self._mode_hint.pack(side="left", padx=(10, 0))

        # ── Input dinámico según modo
        self._input_frame = tk.Frame(f, bg=BG2)
        self._input_frame.pack(fill="x", padx=16, pady=(0, 6))

        self._inputs = {}          # widget entries dinámicos
        self._url_var = tk.StringVar()   # URL final construida / manual
        self._build_input_widgets()

        # ── Carpeta destino
        tk.Label(f, text="Carpeta destino", bg=BG2, fg=TEXT_DIM,
                 font=("Consolas", 9)).pack(anchor="w", padx=16)

        dest_inner = tk.Frame(f, bg=BG2)
        dest_inner.pack(fill="x", padx=16, pady=(2, 8))

        self._dest_var = tk.StringVar(
            value=str(Path.home() / "Downloads" / "twitter-dl"))
        de = _entry(dest_inner, self._dest_var)
        de.pack(side="left", fill="x", expand=True, ipady=5)

        tk.Button(dest_inner, text=" … ", bg=BG3, fg=ACCENT,
                  relief="flat", font=("Consolas", 10),
                  activebackground=BORDER, cursor="hand2",
                  command=self._browse_dest).pack(side="left", padx=(4, 0), ipady=5, ipadx=4)

        ttk.Separator(f, orient="horizontal").pack(fill="x", padx=16, pady=4)

        # ── Opciones rápidas específicas de Twitter
        quick = tk.Frame(f, bg=BG2)
        quick.pack(fill="x", padx=16, pady=4)

        self._q_images   = tk.BooleanVar(value=True)
        self._q_videos   = tk.BooleanVar(value=True)
        self._q_retweets = tk.BooleanVar(value=False)
        self._q_replies  = tk.BooleanVar(value=False)
        self._q_no_part  = tk.BooleanVar(value=True)

        def qchk(text, var):
            tk.Checkbutton(quick, text=text, variable=var,
                           bg=BG2, fg=TEXT, selectcolor=BG3,
                           activebackground=BG2, activeforeground=ACCENT,
                           font=("Consolas", 9), cursor="hand2"
                           ).pack(side="left", padx=(0, 12))

        qchk("Imágenes", self._q_images)
        qchk("Videos",   self._q_videos)
        qchk("Retweets", self._q_retweets)
        qchk("Replies",  self._q_replies)

        # ── Límite de tweets
        lim_fr = tk.Frame(f, bg=BG2)
        lim_fr.pack(fill="x", padx=16, pady=(2, 6))
        tk.Label(lim_fr, text="Límite de tweets (0 = sin límite):", bg=BG2, fg=TEXT_DIM,
                 font=("Consolas", 9)).pack(side="left")
        self._limit_var = tk.StringVar(value="0")
        tk.Entry(lim_fr, textvariable=self._limit_var,
                 bg=BG3, fg=TEXT, insertbackground=ACCENT,
                 relief="flat", font=("Consolas", 9), width=8,
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side="left", padx=(8, 0), ipady=3)

        ttk.Separator(f, orient="horizontal").pack(fill="x", padx=16, pady=4)

        # ── Botones
        btn_row = tk.Frame(f, bg=BG2)
        btn_row.pack(fill="x", padx=16, pady=(4, 10))

        self._btn_start = tk.Button(
            btn_row, text="▶  DESCARGAR", bg=ACCENT, fg="#fff",
            relief="flat", font=("Consolas", 11, "bold"),
            activebackground=ACCENT2, activeforeground="#fff",
            cursor="hand2", command=self._start,
        )
        self._btn_start.pack(side="left", padx=(0, 8), ipadx=18, ipady=6)

        self._btn_cancel = tk.Button(
            btn_row, text="■  CANCELAR", bg=BG3, fg=ERROR,
            relief="flat", font=("Consolas", 11, "bold"),
            activebackground="#2a1515", activeforeground=ERROR,
            cursor="hand2", command=self._cancel_download,
            state="disabled",
        )
        self._btn_cancel.pack(side="left", ipadx=18, ipady=6)

        tk.Button(btn_row, text="📂 Abrir carpeta", bg=BG3, fg=TEXT_DIM,
                  relief="flat", font=("Consolas", 9),
                  activebackground=BORDER, cursor="hand2",
                  command=self._open_dest).pack(side="right", ipadx=10, ipady=6)

        # ── Progress
        self._progress = ttk.Progressbar(f, mode="indeterminate",
                                          style="Horizontal.TProgressbar")
        self._progress.pack(fill="x", padx=16, pady=(0, 6))

        ttk.Separator(f, orient="horizontal").pack(fill="x", padx=16)

        # ── Log
        tk.Label(f, text="Salida", bg=BG2, fg=TEXT_DIM,
                 font=("Consolas", 9)).pack(anchor="w", padx=16, pady=(4, 0))

        log_fr = tk.Frame(f, bg=BG2)
        log_fr.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        self._log_text = tk.Text(
            log_fr, bg=BG, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Consolas", 9), wrap="word",
            state="disabled",
            highlightthickness=1, highlightbackground=BORDER
        )
        vsb = tk.Scrollbar(log_fr, orient="vertical",
                           command=self._log_text.yview,
                           bg=BG3, troughcolor=BG, bd=0, width=10)
        self._log_text.configure(yscrollcommand=vsb.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        for tag, color in [("success", SUCCESS), ("error", ERROR),
                           ("warning", WARNING), ("accent", ACCENT),
                           ("dim", TEXT_DIM)]:
            self._log_text.tag_configure(tag, foreground=color)

    # ── Inputs dinámicos según modo ────────────────────────────────────────────
    def _build_input_widgets(self):
        for w in self._input_frame.winfo_children():
            w.destroy()
        self._inputs = {}

        mode_label = self._mode_combo.get()
        key = self._label_to_key.get(mode_label, "url_manual")

        hints = {
            "timeline":   "Usuario (sin @)",
            "media":      "Usuario (sin @)",
            "likes":      "Usuario (sin @)",
            "bookmarks":  None,               # no necesita input
            "tweet":      None,               # usuario + id
            "search":     "Búsqueda (ej: #AI OR lang:es)",
            "list":       "ID numérico de la lista",
            "url_manual": "URL completa de X",
        }

        if key == "bookmarks":
            tk.Label(self._input_frame,
                     text="Se descargará https://x.com/i/bookmarks  (requiere cookies)",
                     bg=BG2, fg=TEXT_DIM, font=("Consolas", 9)
                     ).pack(anchor="w", pady=4)
            self._mode_hint.config(text="⚠ Necesita cookies de sesión")

        elif key == "tweet":
            tk.Label(self._input_frame, text="Usuario", bg=BG2, fg=TEXT_DIM,
                     font=("Consolas", 9)).pack(anchor="w")
            v_user = tk.StringVar()
            e_user = _entry(self._input_frame, v_user)
            e_user.pack(fill="x", ipady=5, pady=(0, 4))
            _placeholder(e_user, "usuario (sin @)", v_user)

            tk.Label(self._input_frame, text="ID del tweet", bg=BG2, fg=TEXT_DIM,
                     font=("Consolas", 9)).pack(anchor="w")
            v_id = tk.StringVar()
            e_id = _entry(self._input_frame, v_id)
            e_id.pack(fill="x", ipady=5)
            _placeholder(e_id, "1234567890123456789", v_id)

            self._inputs = {"user": v_user, "id": v_id}
            self._mode_hint.config(text="")

        elif key == "url_manual":
            tk.Label(self._input_frame, text="URL", bg=BG2, fg=TEXT_DIM,
                     font=("Consolas", 9)).pack(anchor="w")
            v = tk.StringVar()
            e = _entry(self._input_frame, v)
            e.pack(fill="x", ipady=6)
            e.bind("<Return>", lambda _: self._start())
            _placeholder(e, "https://x.com/…", v)
            self._inputs = {"url": v}
            self._mode_hint.config(text="")

        elif key == "search":
            tk.Label(self._input_frame, text="Búsqueda", bg=BG2, fg=TEXT_DIM,
                     font=("Consolas", 9)).pack(anchor="w")
            v = tk.StringVar()
            e = _entry(self._input_frame, v)
            e.pack(fill="x", ipady=6)
            _placeholder(e, hints[key], v)
            self._inputs = {"query": v}
            self._mode_hint.config(text="ej: from:user OR #tag")

        else:
            hint = hints.get(key, "Usuario")
            tk.Label(self._input_frame, text="Usuario de X", bg=BG2, fg=TEXT_DIM,
                     font=("Consolas", 9)).pack(anchor="w")
            v = tk.StringVar()
            e = _entry(self._input_frame, v)
            e.pack(fill="x", ipady=6)
            e.bind("<Return>", lambda _: self._start())
            _placeholder(e, hint, v)
            self._inputs = {"user": v}
            self._mode_hint.config(text=self.MODES[key][1])

    def _on_mode_change(self, _=None):
        self._build_input_widgets()

    def _get_url(self):
        """Construye la URL a partir del modo e inputs."""
        mode_label = self._mode_combo.get()
        key = self._label_to_key.get(mode_label, "url_manual")
        template = self.MODES[key][1]

        if key == "bookmarks":
            return "https://x.com/i/bookmarks"

        if key == "url_manual":
            url = self._inputs.get("url", tk.StringVar()).get().strip()
            return url if url and url != "https://x.com/…" else ""

        if key == "tweet":
            user = self._inputs.get("user", tk.StringVar()).get().strip()
            tid  = self._inputs.get("id",   tk.StringVar()).get().strip()
            if not user or not tid:
                return ""
            return template.replace("{user}", user).replace("{id}", tid)

        if key == "search":
            q = self._inputs.get("query", tk.StringVar()).get().strip()
            if not q or q == "ej: #AI OR lang:es":
                return ""
            import urllib.parse
            return template.replace("{query}", urllib.parse.quote(q))

        user = self._inputs.get("user", tk.StringVar()).get().strip()
        if not user or user in ("usuario (sin @)", "Usuario (sin @)"):
            return ""
        return template.replace("{user}", user)

    # ── Tab: Auth / Cookies ────────────────────────────────────────────────────
    def _build_tab_auth(self):
        f = self._tab_auth
        f.configure(style="Card.TFrame")

        canvas = tk.Canvas(f, bg=BG2, highlightthickness=0)
        vsb    = tk.Scrollbar(f, orient="vertical", command=canvas.yview,
                               bg=BG3, troughcolor=BG, bd=0, width=10)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=BG2)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win, width=e.width))

        # ── Advertencia
        warn_fr = tk.Frame(inner, bg="#1a1500", highlightthickness=1,
                           highlightbackground="#4a3500")
        warn_fr.pack(fill="x", padx=20, pady=(16, 8))
        tk.Label(warn_fr,
                 text="⚠  Para bookmarks, likes y contenido privado necesitas autenticación.",
                 bg="#1a1500", fg=WARNING, font=("Consolas", 9),
                 wraplength=600, justify="left", padx=10, pady=8
                 ).pack(anchor="w")

        _section(inner, "Cookies (método recomendado)")

        # Archivo cookies
        fr1 = tk.Frame(inner, bg=BG2)
        fr1.pack(fill="x", padx=20, pady=4)
        tk.Label(fr1, text="Archivo cookies.txt", bg=BG2, fg=TEXT,
                 font=("Consolas", 9), width=28, anchor="w").pack(side="left")
        self._cookies_var = tk.StringVar()
        e_cook = _entry(fr1, self._cookies_var)
        e_cook.pack(side="left", fill="x", expand=True, ipady=4)
        _placeholder(e_cook, "/ruta/cookies.txt (exporta desde browser)", self._cookies_var)
        tk.Button(fr1, text=" … ", bg=BG3, fg=ACCENT, relief="flat",
                  font=("Consolas", 9), cursor="hand2",
                  command=self._browse_cookies).pack(side="left", padx=(4, 0), ipadx=4, ipady=4)

        # Cookies desde browser
        fr_browser = tk.Frame(inner, bg=BG2)
        fr_browser.pack(fill="x", padx=20, pady=4)
        tk.Label(fr_browser, text="Cookies desde browser", bg=BG2, fg=TEXT,
                 font=("Consolas", 9), width=28, anchor="w").pack(side="left")
        self._browser_var = tk.StringVar(value="")
        browsers = ["", "chrome", "firefox", "edge", "safari", "opera", "chromium"]
        ttk.Combobox(fr_browser, textvariable=self._browser_var,
                     values=browsers, state="readonly",
                     font=("Consolas", 9), width=18
                     ).pack(side="left")
        tk.Label(fr_browser, text="  (--cookies-from-browser)",
                 bg=BG2, fg=TEXT_DIM, font=("Consolas", 8)).pack(side="left")

        _section(inner, "Usuario / Contraseña")
        info_lbl = tk.Label(inner,
            text="Nota: X/Twitter puede requerir autenticación con cookies en lugar de usuario/contraseña.",
            bg=BG2, fg=TEXT_DIM, font=("Consolas", 8), wraplength=600,
            justify="left")
        info_lbl.pack(anchor="w", padx=20, pady=(0, 6))

        self._user_var = tk.StringVar()
        self._pass_var = tk.StringVar()
        _row_entry(inner, "--username           ", self._user_var, "@usuario o email")
        pw_fr = tk.Frame(inner, bg=BG2)
        pw_fr.pack(fill="x", padx=20, pady=3)
        tk.Label(pw_fr, text="--password           ", bg=BG2, fg=TEXT,
                 font=("Consolas", 9), width=28, anchor="w").pack(side="left")
        pw = tk.Entry(pw_fr, textvariable=self._pass_var,
                      show="●", bg=BG3, fg=TEXT,
                      insertbackground=ACCENT, relief="flat",
                      font=("Consolas", 9),
                      highlightthickness=1, highlightbackground=BORDER,
                      highlightcolor=ACCENT)
        pw.pack(side="left", fill="x", expand=True, ipady=4)

        _section(inner, "Token de API (avanzado)")
        tk.Label(inner,
                 text="Si tienes un bearer token propio configúralo en gallery-dl.conf\n"
                      "bajo extractor.twitter.access-token.",
                 bg=BG2, fg=TEXT_DIM, font=("Consolas", 8),
                 justify="left").pack(anchor="w", padx=20, pady=(0, 8))

        # Guía rápida
        _section(inner, "Guía rápida: exportar cookies")
        steps = [
            "1. Instala la extensión 'Get cookies.txt LOCALLY' en Chrome/Firefox.",
            "2. Ve a x.com e inicia sesión.",
            "3. Haz clic en la extensión y exporta 'x.com' como cookies.txt.",
            "4. Selecciona ese archivo arriba en 'Archivo cookies.txt'.",
        ]
        for s in steps:
            tk.Label(inner, text=s, bg=BG2, fg=TEXT_DIM,
                     font=("Consolas", 8), justify="left"
                     ).pack(anchor="w", padx=24, pady=1)

    def _browse_cookies(self):
        f = filedialog.askopenfilename(
            title="Seleccionar cookies.txt",
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")]
        )
        if f:
            self._cookies_var.set(f)

    # ── Tab: Opciones ──────────────────────────────────────────────────────────
    def _build_tab_options(self):
        f = self._tab_options
        f.configure(style="Card.TFrame")

        canvas = tk.Canvas(f, bg=BG2, highlightthickness=0)
        vsb    = tk.Scrollbar(f, orient="vertical", command=canvas.yview,
                               bg=BG3, troughcolor=BG, bd=0, width=10)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=BG2)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win, width=e.width))

        # Variables
        self._opt_filename    = tk.StringVar(value="")
        self._opt_retries     = tk.StringVar(value="4")
        self._opt_sleep       = tk.StringVar(value="")
        self._opt_extra       = tk.StringVar(value="")
        self._opt_verbose     = tk.BooleanVar(value=False)
        self._opt_simulate    = tk.BooleanVar(value=False)
        self._opt_no_mtime    = tk.BooleanVar(value=False)
        self._opt_zip         = tk.BooleanVar(value=False)
        self._opt_write_info  = tk.BooleanVar(value=False)
        self._opt_write_tags  = tk.BooleanVar(value=False)

        _section(inner, "Archivos")
        _row_entry(inner, "--filename           ", self._opt_filename,
                   "{author[name]}_{date:%Y%m%d}_{id}.{extension}")
        _chk(inner, "--write-info-json",  self._opt_write_info,  "guardar metadatos JSON")
        _chk(inner, "--write-tags",       self._opt_write_tags,  "guardar tags en .txt")
        _chk(inner, "--no-mtime",         self._opt_no_mtime,    "no preservar fecha")
        _chk(inner, "--zip",              self._opt_zip,         "comprimir en .zip")

        _section(inner, "Red")
        _row_entry(inner, "--retries           ", self._opt_retries)
        _row_entry(inner, "--sleep (seg)       ", self._opt_sleep, "0.5-2.0")

        _section(inner, "Comportamiento")
        _chk(inner, "--verbose",   self._opt_verbose,  "salida debug completa")
        _chk(inner, "--simulate",  self._opt_simulate, "solo simular, sin descargar")

        _section(inner, "Argumentos adicionales")
        _row_entry(inner, "Args extra          ", self._opt_extra, "--option valor …")

        tk.Button(inner, text="↺  Restaurar defaults",
                  bg=BG3, fg=TEXT_DIM, relief="flat", font=("Consolas", 9),
                  activebackground=BORDER, cursor="hand2",
                  command=self._reset_options).pack(anchor="w", padx=20, pady=14, ipadx=10, ipady=4)

    def _reset_options(self):
        self._opt_filename.set("")
        self._opt_retries.set("4")
        self._opt_sleep.set("")
        self._opt_extra.set("")
        self._opt_verbose.set(False)
        self._opt_simulate.set(False)
        self._opt_no_mtime.set(False)
        self._opt_zip.set(False)
        self._opt_write_info.set(False)
        self._opt_write_tags.set(False)

    # ── Tab: Historial ─────────────────────────────────────────────────────────
    def _build_tab_history(self):
        f = self._tab_history
        f.configure(style="Card.TFrame")

        toolbar = tk.Frame(f, bg=BG2)
        toolbar.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(toolbar, text="Descargas recientes", bg=BG2, fg=ACCENT,
                 font=("Consolas", 10, "bold")).pack(side="left")
        tk.Button(toolbar, text="Limpiar", bg=BG3, fg=ERROR,
                  relief="flat", font=("Consolas", 9),
                  activebackground="#2a1515", cursor="hand2",
                  command=self._clear_history).pack(side="right", ipadx=8, ipady=3)

        cols = ("Fecha", "Modo", "Target", "Estado")
        style_tree = ttk.Style()
        style_tree.configure("Treeview", background=BG3, foreground=TEXT,
                             fieldbackground=BG3, rowheight=24,
                             font=("Consolas", 9))
        style_tree.configure("Treeview.Heading", background=BG2,
                             foreground=ACCENT, font=("Consolas", 9, "bold"))
        style_tree.map("Treeview", background=[("selected", ACCENT2)])

        self._hist_tree = ttk.Treeview(f, columns=cols, show="headings", height=22)
        self._hist_tree.heading("Fecha",  text="Fecha")
        self._hist_tree.heading("Modo",   text="Modo")
        self._hist_tree.heading("Target", text="Target")
        self._hist_tree.heading("Estado", text="Estado")
        self._hist_tree.column("Fecha",  width=130, stretch=False)
        self._hist_tree.column("Modo",   width=110, stretch=False)
        self._hist_tree.column("Target", width=480)
        self._hist_tree.column("Estado", width=90,  stretch=False)

        vsb2 = ttk.Scrollbar(f, orient="vertical", command=self._hist_tree.yview)
        self._hist_tree.configure(yscrollcommand=vsb2.set)
        self._hist_tree.pack(side="left", fill="both", expand=True,
                             padx=(16, 0), pady=(0, 12))
        vsb2.pack(side="right", fill="y", pady=(0, 12), padx=(0, 8))
        self._hist_tree.bind("<Double-1>", self._load_from_history)
        self._refresh_history_tree()

    # ══════════════════════════════════════════════════════════════════════════
    # Lógica de descarga
    # ══════════════════════════════════════════════════════════════════════════
    def _start(self):
        url = self._get_url()
        if not url:
            messagebox.showwarning("Datos incompletos",
                "Completa los campos requeridos para el modo seleccionado.")
            return

        dest = self._dest_var.get().strip()
        if not dest:
            messagebox.showwarning("Destino vacío", "Elige una carpeta de destino.")
            return

        Path(dest).mkdir(parents=True, exist_ok=True)
        cmd = self._build_command(url, dest)

        self._log(f"\n── Nueva descarga ───────────────────────", "dim")
        self._log(f"$ {' '.join(cmd)}", "accent")
        self._log("", "dim")

        self._cancel.clear()
        self._btn_start.config(state="disabled")
        self._btn_cancel.config(state="normal")
        self._progress.start(12)
        self._set_status("Descargando…")

        mode_label = self._mode_combo.get()
        self._add_history(mode_label, url, "⏳ en curso")

        threading.Thread(
            target=self._run_process, args=(cmd, url, mode_label), daemon=True
        ).start()

    def _build_command(self, url, dest):
        cmd = ["gallery-dl", "--destination", dest]

        # Autenticación
        cookies = self._cookies_var.get().strip()
        if cookies and cookies != "/ruta/cookies.txt (exporta desde browser)":
            cmd += ["--cookies", cookies]

        browser = self._browser_var.get().strip()
        if browser:
            cmd += ["--cookies-from-browser", browser]

        user = self._user_var.get().strip()
        if user and user != "@usuario o email":
            cmd += ["--username", user]

        pw = self._pass_var.get().strip()
        if pw:
            cmd += ["--password", pw]

        # Filtro de tipo de contenido (extractor.twitter.*)
        # gallery-dl permite pasar opciones de config via -o key=value
        if not self._q_retweets.get():
            cmd += ["-o", "extractor.twitter.retweets=false"]
        if not self._q_replies.get():
            cmd += ["-o", "extractor.twitter.replies=false"]

        media_filter = []
        if self._q_images.get():
            media_filter.append("photo")
        if self._q_videos.get():
            media_filter.append("video")
        if media_filter:
            cmd += ["-o", f"extractor.twitter.media-types=[{','.join(media_filter)}]"]

        # Límite
        limit = self._limit_var.get().strip()
        if limit and limit != "0":
            try:
                int(limit)
                cmd += ["--range", f"1-{limit}"]
            except ValueError:
                pass

        # Opciones de archivo
        fname = self._opt_filename.get().strip()
        ph = "{author[name]}_{date:%Y%m%d}_{id}.{extension}"
        if fname and fname != ph:
            cmd += ["--filename", fname]

        if self._q_no_part.get():
            cmd.append("--no-part")
        if self._opt_write_info.get():
            cmd.append("--write-info-json")
        if self._opt_write_tags.get():
            cmd.append("--write-tags")
        if self._opt_no_mtime.get():
            cmd.append("--no-mtime")
        if self._opt_zip.get():
            cmd.append("--zip")

        # Red
        retries = self._opt_retries.get().strip()
        if retries:
            cmd += ["--retries", retries]

        sleep = self._opt_sleep.get().strip()
        if sleep and sleep != "0.5-2.0":
            cmd += ["--sleep", sleep]

        if self._opt_verbose.get():
            cmd.append("--verbose")
        if self._opt_simulate.get():
            cmd.append("--simulate")

        extra = self._opt_extra.get().strip()
        if extra and extra != "--option valor …":
            cmd += shlex.split(extra)

        cmd.append(url)
        return cmd

    def _run_process(self, cmd, url, mode_label):
        try:
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, encoding="utf-8", errors="replace"
            )
            for line in self._process.stdout:
                if self._cancel.is_set():
                    self._process.terminate()
                    self._queue.put(("log", "⚠ Cancelado.", "warning"))
                    break
                line = line.rstrip()
                if not line:
                    continue
                tag = "dim"
                lo = line.lower()
                if "error" in lo or "failed" in lo:
                    tag = "error"
                elif "warning" in lo or "warn" in lo:
                    tag = "warning"
                elif any(x in lo for x in ("downloaded", "skip", "tweet", "media")):
                    tag = "success"
                elif "%" in line:
                    tag = "success"
                self._queue.put(("log", line, tag))

            self._process.wait()
            rc = self._process.returncode

            if self._cancel.is_set():
                self._queue.put(("done", url, mode_label, "cancelado"))
            elif rc == 0:
                self._queue.put(("log", "✓ Completado.", "success"))
                self._queue.put(("done", url, mode_label, "✓ ok"))
            else:
                self._queue.put(("log", f"✗ Código de salida: {rc}", "error"))
                self._queue.put(("done", url, mode_label, f"✗ cod {rc}"))

        except FileNotFoundError:
            self._queue.put(("log",
                "✗ gallery-dl no encontrado. pip install gallery-dl", "error"))
            self._queue.put(("done", url, mode_label, "✗ no instalado"))
        except Exception as e:
            self._queue.put(("log", f"✗ {e}", "error"))
            self._queue.put(("done", url, mode_label, "✗ error"))
        finally:
            self._process = None

    def _cancel_download(self):
        self._cancel.set()
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass
        self._log("⚠ Cancelando…", "warning")

    # ── Cola ───────────────────────────────────────────────────────────────────
    def _poll_queue(self):
        try:
            while True:
                item = self._queue.get_nowait()
                if item[0] == "log":
                    self._log(item[1], item[2] if len(item) > 2 else None)
                elif item[0] == "done":
                    self._on_done(item[1], item[2], item[3])
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _on_done(self, url, mode_label, estado):
        self._progress.stop()
        self._btn_start.config(state="normal")
        self._btn_cancel.config(state="disabled")
        self._set_status(f"Listo — {estado}")
        self._update_history(url, estado)
        self._refresh_history_tree()

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _log(self, msg, tag=None):
        self._log_text.config(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_text.insert("end", f"[{ts}] ", "dim")
        self._log_text.insert("end", msg + "\n", tag or "")
        self._log_text.see("end")
        self._log_text.config(state="disabled")

    def _set_status(self, msg):
        self._status_var.set(msg)

    def _browse_dest(self):
        d = filedialog.askdirectory(title="Carpeta destino")
        if d:
            self._dest_var.set(d)

    def _open_dest(self):
        dest = self._dest_var.get().strip()
        if not dest or not Path(dest).exists():
            messagebox.showinfo("Carpeta", "La carpeta no existe todavía.")
            return
        if sys.platform == "win32":
            os.startfile(dest)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", dest])
        else:
            subprocess.Popen(["xdg-open", dest])

    # ── Historial ──────────────────────────────────────────────────────────────
    def _add_history(self, mode_label, url, estado):
        entry = {
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "modo":  mode_label,
            "url":   url,
            "estado": estado
        }
        for e in self._history:
            if e.get("url") == url:
                e.update({"fecha": entry["fecha"], "estado": estado})
                save_history(self._history)
                return
        self._history.append(entry)
        save_history(self._history)

    def _update_history(self, url, estado):
        for e in self._history:
            if e.get("url") == url:
                e["estado"] = estado
                save_history(self._history)
                return

    def _refresh_history_tree(self):
        for row in self._hist_tree.get_children():
            self._hist_tree.delete(row)
        for entry in reversed(self._history):
            self._hist_tree.insert("", "end", values=(
                entry.get("fecha", ""),
                entry.get("modo",  ""),
                entry.get("url",   ""),
                entry.get("estado","")
            ))

    def _load_from_history(self, _=None):
        sel = self._hist_tree.selection()
        if not sel:
            return
        values = self._hist_tree.item(sel[0], "values")
        if values and len(values) >= 3:
            # Intentar restaurar modo
            mode_label = values[1]
            if mode_label in self._label_to_key:
                self._mode_combo.set(mode_label)
                self._build_input_widgets()
            # Poner URL en modo manual si no matchea
            url = values[2]
            key = self._label_to_key.get(mode_label, "url_manual")
            if key == "url_manual" and "url" in self._inputs:
                self._inputs["url"].set(url)

    def _clear_history(self):
        if messagebox.askyesno("Limpiar historial", "¿Eliminar todo el historial?"):
            self._history.clear()
            save_history(self._history)
            self._refresh_history_tree()


# ─── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = TwitterDLApp()
    app.mainloop()