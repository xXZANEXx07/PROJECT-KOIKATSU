import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageTk
import io
import os
import re
import time

BASE_URL = "https://db.bepis.moe"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ── Datos para Cartas ──────────────────────────────────────────────────────────
PERSONALITIES = [
    "Unspecified","Sexy","Ojousama","Snobby","Kouhai","Mysterious","Weirdo",
    "Yamato Nadeshiko","Tomboy","Pure","Simple","Delusional","Motherly",
    "Big Sisterly","Gyaru","Delinquent","Wild","Wannabe","Reluctant","Jinxed",
    "Bookish","Timid","Typical Schoolgirl","Trendy","Otaku","Yandere","Lazy",
    "Quiet","Stubborn","Old-Fashioned","Humble","Friendly","Willful","Honest",
    "Glamorous","Returnee","Slangy","Sadistic","Emotionless","Perfectionist"
]
GAME_TYPES = ["Unspecified","Base","Steam","Steam 18+","Emotion Creators","Sunshine"]
GENDERS    = ["Unspecified","Female","Male"]
ORDER_BY   = ["Popularity","Date (ascending)","Date (descending)"]

GENDER_MAP   = {"Unspecified": "", "Female": "Female", "Male": "Male"}
ORDER_MAP    = {"Popularity": "popularity", "Date (ascending)": "date_asc",
                "Date (descending)": "date_desc"}
GAMETYPE_MAP = {"Unspecified": "", "Base": "0", "Steam": "1",
                "Steam 18+": "2", "Emotion Creators": "3", "Sunshine": "4"}

# ── Constructores de URL ────────────────────────────────────────────────────────
def build_cards_url(page=1, name="", tags="", gender="", personality="",
                    game_type="", order="popularity", show_hidden=True):
    params = [f"page={page}"]
    if name:       params.append(f"name={requests.utils.quote(name)}")
    if tags:       params.append(f"tags={requests.utils.quote(tags)}")
    if gender:     params.append(f"gender={gender}")
    if personality and personality != "Unspecified":
        params.append(f"personality={requests.utils.quote(personality)}")
    if game_type:  params.append(f"gameType={game_type}")
    if order:      params.append(f"orderBy={order}")
    if show_hidden:
        params.append("showHidden=true")
    return f"{BASE_URL}/koikatsu?" + "&".join(params)


def build_scenes_url(page=1, name="", tags="", females="", males="",
                     no_mods=False, has_timeline="", order="popularity",
                     show_hidden=True):
    params = [f"page={page}"]
    if name:   params.append(f"name={requests.utils.quote(name)}")
    if tags:   params.append(f"tags={requests.utils.quote(tags)}")
    if females: params.append(f"females={females}")
    if males:   params.append(f"males={males}")
    if no_mods: params.append("noMods=true")
    if has_timeline and has_timeline != "Unspecified":
        val = "true" if has_timeline == "Yes" else "false"
        params.append(f"hasTimeline={val}")
    if order:  params.append(f"orderBy={order}")
    if show_hidden:
        params.append("showHidden=true")
    return f"{BASE_URL}/kkscenes?" + "&".join(params)


# ── Scraper genérico ────────────────────────────────────────────────────────────
def scrape_page(url, prefix, view_path):
    """
    prefix    : "KK" o "KKSCENE"
    view_path : "koikatsu" o "kkscenes"
    Devuelve (lista_cards, tiene_siguiente_pagina, error)
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        return [], False, str(e)

    soup = BeautifulSoup(r.text, "html.parser")
    cards = []

    pattern = f'/{view_path}/view/'
    for a in soup.select(f"a[href*='{pattern}']"):
        img = a.find("img")
        if not img:
            continue
        thumb_src = img.get("src", "")
        if not thumb_src.startswith("http"):
            thumb_src = BASE_URL + thumb_src

        m = re.search(rf'/{re.escape(view_path)}/view/(\d+)', a["href"])
        if not m:
            continue
        card_id = m.group(1)

        name = ""
        parent = a.parent
        texts = [t.strip() for t in parent.stripped_strings]
        for t in texts:
            if t and "Download" not in t:
                name = t
                break

        padded_id = str(card_id).zfill(6)
        download_url = f"{BASE_URL}/card/download/{prefix}_{padded_id}.png"
        cards.append({
            "id": card_id,
            "name": name or f"{prefix}_{card_id}",
            "thumb_url": thumb_src,
            "download_url": download_url,
            "prefix": prefix,
        })

    has_next = bool(
        soup.find("a", string=re.compile(r'Next|Siguiente|›|»', re.I)) or
        soup.select_one("li.page-item:last-child a[href*='page=']")
    )
    return cards, has_next, None


# ==============================================================================
class KoikatsuDownloader(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🎴 Koikatsu Downloader — BepisDB")
        self.geometry("1200x820")
        self.configure(bg="#1e1e2e")
        self.resizable(True, True)

        self.current_page    = 1
        self.cards           = []
        self.selected_cards  = set()
        self.thumb_cache     = {}
        self.save_dir        = os.path.expanduser("~/Downloads")
        self.loading         = False
        self.card_widgets    = {}

        self._auto_running   = False
        self._cancel_flag    = threading.Event()
        self._auto_total_dl  = 0
        self._auto_ok_dl     = 0

        self._build_styles()
        self._build_ui()

    # ── Estilos ────────────────────────────────────────────────────────────────
    def _build_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        bg, fg = "#1e1e2e", "#cdd6f4"
        cb = "#313244"
        s.configure("TFrame",      background=bg)
        s.configure("TLabel",      background=bg, foreground=fg, font=("Segoe UI", 9))
        s.configure("TButton",     background=cb, foreground=fg,
                                    font=("Segoe UI", 9), relief="flat", padding=5)
        s.map("TButton", background=[("active","#45475a")], foreground=[("active",fg)])
        s.configure("Accent.TButton", background="#89b4fa", foreground="#1e1e2e",
                                       font=("Segoe UI", 9, "bold"), padding=5)
        s.map("Accent.TButton",
              background=[("active","#74c7ec")], foreground=[("active","#1e1e2e")])
        s.configure("Red.TButton", background="#f38ba8", foreground="#1e1e2e",
                                    font=("Segoe UI", 9, "bold"), padding=5)
        s.map("Red.TButton",
              background=[("active","#eba0ac")], foreground=[("active","#1e1e2e")])
        s.configure("TEntry",      fieldbackground=cb, foreground=fg, insertcolor=fg)
        s.configure("TCombobox",   fieldbackground=cb, background=cb,
                                    foreground=fg, selectbackground="#45475a")
        s.map("TCombobox", fieldbackground=[("readonly", cb)])
        s.configure("TScrollbar",  background=cb, troughcolor=bg, arrowcolor=fg)
        s.configure("Green.Horizontal.TProgressbar",
                     troughcolor=cb, background="#a6e3a1", thickness=14)
        s.configure("Blue.Horizontal.TProgressbar",
                     troughcolor=cb, background="#89b4fa", thickness=14)
        s.configure("TNotebook",   background=bg, borderwidth=0)
        s.configure("TNotebook.Tab", background="#313244", foreground=fg,
                     font=("Segoe UI", 10, "bold"), padding=(12, 6))
        s.map("TNotebook.Tab",
              background=[("selected", "#89b4fa")],
              foreground=[("selected", "#1e1e2e")])

    # ── Layout principal ───────────────────────────────────────────────────────
    def _build_ui(self):
        # Panel izquierdo: notebook con dos tabs de filtros
        sidebar = ttk.Frame(self, width=240)
        sidebar.pack(side="left", fill="y", padx=(10,0), pady=10)
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        # Panel derecho: resultados compartidos
        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self._build_right(right)

    # ── Sidebar con notebook ───────────────────────────────────────────────────
    def _build_sidebar(self, p):
        tk.Label(p, text="🎴 KK Downloader", bg="#1e1e2e", fg="#89b4fa",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0,6))

        self.mode_notebook = ttk.Notebook(p)
        self.mode_notebook.pack(fill="both", expand=True)

        # Tab Cartas
        tab_cards = ttk.Frame(self.mode_notebook)
        self.mode_notebook.add(tab_cards, text="🃏 Cartas")
        self._build_cards_filters(tab_cards)

        # Tab Escenas
        tab_scenes = ttk.Frame(self.mode_notebook)
        self.mode_notebook.add(tab_scenes, text="🎬 Escenas")
        self._build_scenes_filters(tab_scenes)

    def _lbl(self, parent, text):
        tk.Label(parent, text=text, bg="#1e1e2e", fg="#a6adc8",
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(5,1))

    def _sep(self, parent):
        tk.Frame(parent, bg="#45475a", height=1).pack(fill="x", pady=8)

    # ── Filtros Cartas ─────────────────────────────────────────────────────────
    def _build_cards_filters(self, p):
        def lbl(t): self._lbl(p, t)

        lbl("Nombre:"); self.c_name_var = tk.StringVar()
        ttk.Entry(p, textvariable=self.c_name_var).pack(fill="x")

        lbl("Tags (separados por coma):"); self.c_tags_var = tk.StringVar()
        ttk.Entry(p, textvariable=self.c_tags_var).pack(fill="x")

        lbl("Género:"); self.c_gender_var = tk.StringVar(value="Unspecified")
        ttk.Combobox(p, textvariable=self.c_gender_var,
                     values=GENDERS, state="readonly").pack(fill="x")

        lbl("Personalidad:"); self.c_personality_var = tk.StringVar(value="Unspecified")
        ttk.Combobox(p, textvariable=self.c_personality_var,
                     values=PERSONALITIES, state="readonly").pack(fill="x")

        lbl("Tipo de juego:"); self.c_gametype_var = tk.StringVar(value="Unspecified")
        ttk.Combobox(p, textvariable=self.c_gametype_var,
                     values=GAME_TYPES, state="readonly").pack(fill="x")

        lbl("Ordenar por:"); self.c_order_var = tk.StringVar(value="Popularity")
        ttk.Combobox(p, textvariable=self.c_order_var,
                     values=ORDER_BY, state="readonly").pack(fill="x")

        self._sep(p)

        self.c_hidden_var = tk.BooleanVar(value=True)
        tk.Checkbutton(p, text="👁  Mostrar cartas ocultas",
                       variable=self.c_hidden_var, bg="#1e1e2e", fg="#cdd6f4",
                       selectcolor="#313244", activebackground="#1e1e2e",
                       activeforeground="#cdd6f4",
                       font=("Segoe UI", 9, "bold")).pack(anchor="w")

        self._sep(p)
        self._build_page_controls(p, "c")
        self._sep(p)
        self._build_action_buttons(p)

    # ── Filtros Escenas ────────────────────────────────────────────────────────
    def _build_scenes_filters(self, p):
        def lbl(t): self._lbl(p, t)

        lbl("Nombre:"); self.s_name_var = tk.StringVar()
        ttk.Entry(p, textvariable=self.s_name_var).pack(fill="x")

        lbl("Tags (separados por coma):"); self.s_tags_var = tk.StringVar()
        ttk.Entry(p, textvariable=self.s_tags_var).pack(fill="x")

        lbl("Nº personajes femeninos:"); self.s_females_var = tk.StringVar()
        ttk.Entry(p, textvariable=self.s_females_var).pack(fill="x")

        lbl("Nº personajes masculinos:"); self.s_males_var = tk.StringVar()
        ttk.Entry(p, textvariable=self.s_males_var).pack(fill="x")

        lbl("Animation Timeline:"); self.s_timeline_var = tk.StringVar(value="Unspecified")
        ttk.Combobox(p, textvariable=self.s_timeline_var,
                     values=["Unspecified","Yes","No"], state="readonly").pack(fill="x")

        lbl("Ordenar por:"); self.s_order_var = tk.StringVar(value="Popularity")
        ttk.Combobox(p, textvariable=self.s_order_var,
                     values=ORDER_BY, state="readonly").pack(fill="x")

        self._sep(p)

        self.s_hidden_var = tk.BooleanVar(value=True)
        tk.Checkbutton(p, text="👁  Mostrar ocultas",
                       variable=self.s_hidden_var, bg="#1e1e2e", fg="#cdd6f4",
                       selectcolor="#313244", activebackground="#1e1e2e",
                       activeforeground="#cdd6f4",
                       font=("Segoe UI", 9, "bold")).pack(anchor="w")

        self.s_nomods_var = tk.BooleanVar(value=False)
        tk.Checkbutton(p, text="🧩  Sin mods",
                       variable=self.s_nomods_var, bg="#1e1e2e", fg="#cdd6f4",
                       selectcolor="#313244", activebackground="#1e1e2e",
                       activeforeground="#cdd6f4",
                       font=("Segoe UI", 9, "bold")).pack(anchor="w")

        self._sep(p)
        self._build_page_controls(p, "s")
        self._sep(p)
        self._build_action_buttons(p)

    def _build_page_controls(self, p, prefix):
        def lbl(t): self._lbl(p, t)
        lbl("Página inicio (auto-descarga):")
        var_start = tk.IntVar(value=1)
        ttk.Spinbox(p, from_=1, to=9999, textvariable=var_start,
                    width=8, font=("Segoe UI",9)).pack(anchor="w")

        lbl("Página fin (0 = hasta el final):")
        var_end = tk.IntVar(value=0)
        ttk.Spinbox(p, from_=0, to=9999, textvariable=var_end,
                    width=8, font=("Segoe UI",9)).pack(anchor="w")

        if prefix == "c":
            self.c_start_page_var = var_start
            self.c_end_page_var   = var_end
        else:
            self.s_start_page_var = var_start
            self.s_end_page_var   = var_end

    def _build_action_buttons(self, p):
        """Botones de acción compartidos (se crean dos veces, uno por tab)."""
        ttk.Button(p, text="🔍  Buscar (ver página)",
                   command=self._search).pack(fill="x", pady=2)

        btn_auto = ttk.Button(p, text="🚀  Auto-Descargar todo",
                              style="Accent.TButton",
                              command=self._start_auto)
        btn_auto.pack(fill="x", pady=2)

        btn_cancel = ttk.Button(p, text="⛔  Cancelar",
                                style="Red.TButton",
                                command=self._cancel_auto,
                                state="disabled")
        btn_cancel.pack(fill="x", pady=2)

        ttk.Button(p, text="↺  Limpiar filtros",
                   command=self._reset_filters).pack(fill="x", pady=(6,2))

        tk.Label(p, text="", bg="#1e1e2e").pack(expand=True)
        ttk.Button(p, text="📁 Carpeta destino",
                   command=self._choose_dir).pack(fill="x", pady=2)
        self.dir_lbl = tk.Label(p, text=f"📁 {self.save_dir}",
                                bg="#1e1e2e", fg="#6c7086",
                                font=("Segoe UI", 7), wraplength=220, justify="left")
        self.dir_lbl.pack(anchor="w")

        # Guardamos referencias a los botones del último tab creado
        # (ambos tabs comparten la misma lógica de estado)
        self.auto_btn   = btn_auto
        self.cancel_btn = btn_cancel

    # ── Panel derecho ─────────────────────────────────────────────────────────
    def _build_right(self, p):
        top = ttk.Frame(p)
        top.pack(fill="x", pady=(0,5))
        self.status_var = tk.StringVar(value="Listo. Usa 'Buscar' o 'Auto-Descargar todo'.")
        ttk.Label(top, textvariable=self.status_var,
                  font=("Segoe UI", 9, "italic")).pack(side="left")
        bf = ttk.Frame(top)
        bf.pack(side="right")
        ttk.Button(bf, text="✔ Todo",    command=self._select_all).pack(side="left", padx=2)
        ttk.Button(bf, text="✘ Ninguno", command=self._deselect_all).pack(side="left", padx=2)
        ttk.Button(bf, text="⬇ Descargar selección",
                   style="Accent.TButton",
                   command=self._download_selected).pack(side="left", padx=2)

        # Barras de progreso
        pf = tk.Frame(p, bg="#252535", bd=0)
        pf.pack(fill="x", pady=(0,5))

        r1 = tk.Frame(pf, bg="#252535")
        r1.pack(fill="x", padx=8, pady=(7,2))
        tk.Label(r1, text="Cartas (página):", bg="#252535", fg="#a6adc8",
                 font=("Segoe UI", 8), width=17, anchor="w").pack(side="left")
        self.prog_page = ttk.Progressbar(r1, style="Green.Horizontal.TProgressbar",
                                          mode="determinate", maximum=100, value=0)
        self.prog_page.pack(side="left", fill="x", expand=True, padx=4)
        self.prog_page_lbl = tk.Label(r1, text="0 / 0", bg="#252535", fg="#a6e3a1",
                                       font=("Consolas", 9, "bold"), width=10)
        self.prog_page_lbl.pack(side="left")

        r2 = tk.Frame(pf, bg="#252535")
        r2.pack(fill="x", padx=8, pady=(2,7))
        tk.Label(r2, text="Páginas totales:", bg="#252535", fg="#a6adc8",
                 font=("Segoe UI", 8), width=17, anchor="w").pack(side="left")
        self.prog_total = ttk.Progressbar(r2, style="Blue.Horizontal.TProgressbar",
                                           mode="determinate", maximum=100, value=0)
        self.prog_total.pack(side="left", fill="x", expand=True, padx=4)
        self.prog_total_lbl = tk.Label(r2, text="Pág 0 / ?", bg="#252535", fg="#89b4fa",
                                        font=("Consolas", 9, "bold"), width=10)
        self.prog_total_lbl.pack(side="left")

        # Log
        lf = ttk.Frame(p)
        lf.pack(fill="x", pady=(0,5))
        self.log_text = tk.Text(lf, height=5, bg="#11111b", fg="#a6e3a1",
                                 font=("Consolas", 8), relief="flat",
                                 state="disabled", wrap="word")
        self.log_text.pack(side="left", fill="x", expand=True)
        tk.Scrollbar(lf, orient="vertical", command=self.log_text.yview,
                     bg="#313244").pack(side="right", fill="y")

        # Grilla
        cf = ttk.Frame(p)
        cf.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(cf, bg="#1e1e2e", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(cf, orient="vertical", command=self.canvas.yview)
        vsb.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.bind("<Configure>", lambda e: self._reflow_grid())

        self.grid_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0,0), window=self.grid_frame,
                                                        anchor="nw")
        self.grid_frame.bind("<Configure>",
                             lambda e: self.canvas.configure(
                                 scrollregion=self.canvas.bbox("all")))
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(-1*(e.delta//120), "units"))

        # Paginación manual
        pag = ttk.Frame(p)
        pag.pack(fill="x", pady=(5,0))
        ttk.Button(pag, text="◀ Anterior", command=self._prev_page).pack(side="left", padx=2)
        self.page_var = tk.StringVar(value="Página 1")
        ttk.Label(pag, textvariable=self.page_var,
                  font=("Segoe UI", 10, "bold")).pack(side="left", padx=10)
        ttk.Button(pag, text="Siguiente ▶", command=self._next_page).pack(side="left", padx=2)

    # ── Modo activo ────────────────────────────────────────────────────────────
    def _is_scenes_mode(self):
        return self.mode_notebook.index("current") == 1

    def _get_mode_info(self):
        """Devuelve (prefix, view_path, url_builder_fn)."""
        if self._is_scenes_mode():
            return "KKSCENE", "kkscenes"
        return "KK", "koikatsu"

    def _get_filters(self):
        if self._is_scenes_mode():
            return dict(
                name=self.s_name_var.get().strip(),
                tags=self.s_tags_var.get().strip(),
                females=self.s_females_var.get().strip(),
                males=self.s_males_var.get().strip(),
                no_mods=self.s_nomods_var.get(),
                has_timeline=self.s_timeline_var.get(),
                order=ORDER_MAP.get(self.s_order_var.get(), "popularity"),
                show_hidden=self.s_hidden_var.get(),
            )
        else:
            return dict(
                name=self.c_name_var.get().strip(),
                tags=self.c_tags_var.get().strip(),
                gender=GENDER_MAP.get(self.c_gender_var.get(), ""),
                personality=self.c_personality_var.get(),
                game_type=GAMETYPE_MAP.get(self.c_gametype_var.get(), ""),
                order=ORDER_MAP.get(self.c_order_var.get(), "popularity"),
                show_hidden=self.c_hidden_var.get(),
            )

    def _get_page_range(self):
        if self._is_scenes_mode():
            return self.s_start_page_var.get(), self.s_end_page_var.get()
        return self.c_start_page_var.get(), self.c_end_page_var.get()

    def _build_url(self, page):
        filters = self._get_filters()
        if self._is_scenes_mode():
            return build_scenes_url(page=page, **filters)
        return build_cards_url(page=page, **filters)

    # ── Log ───────────────────────────────────────────────────────────────────
    def _log(self, msg):
        def _do():
            self.log_text.config(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.after(0, _do)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _reset_filters(self):
        if self._is_scenes_mode():
            self.s_name_var.set(""); self.s_tags_var.set("")
            self.s_females_var.set(""); self.s_males_var.set("")
            self.s_timeline_var.set("Unspecified")
            self.s_order_var.set("Popularity")
            self.s_hidden_var.set(True); self.s_nomods_var.set(False)
            self.s_start_page_var.set(1); self.s_end_page_var.set(0)
        else:
            self.c_name_var.set(""); self.c_tags_var.set("")
            self.c_gender_var.set("Unspecified"); self.c_personality_var.set("Unspecified")
            self.c_gametype_var.set("Unspecified"); self.c_order_var.set("Popularity")
            self.c_hidden_var.set(True)
            self.c_start_page_var.set(1); self.c_end_page_var.set(0)

    def _choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.save_dir, title="Carpeta destino")
        if d:
            self.save_dir = d
            self.dir_lbl.config(text=f"📁 {d}")

    # ── Búsqueda / paginación manual ──────────────────────────────────────────
    def _search(self):
        self.current_page = 1
        self._load_page()

    def _prev_page(self):
        if self.current_page > 1 and not self.loading:
            self.current_page -= 1
            self._load_page()

    def _next_page(self):
        if not self.loading:
            self.current_page += 1
            self._load_page()

    def _load_page(self):
        if self.loading: return
        self.loading = True
        self.status_var.set("Cargando página…")
        # Capturar modo en el momento de la llamada
        prefix, view_path = self._get_mode_info()
        url = self._build_url(self.current_page)
        threading.Thread(
            target=self._fetch_show_thread,
            args=(url, prefix, view_path),
            daemon=True
        ).start()

    def _fetch_show_thread(self, url, prefix, view_path):
        cards, _, error = scrape_page(url, prefix, view_path)
        self.after(0, self._on_fetch_done, cards, error)

    def _on_fetch_done(self, cards, error):
        self.loading = False
        if error:
            self.status_var.set(f"❌ {error}")
            messagebox.showerror("Error", error); return
        self.cards = cards
        self.selected_cards.clear()
        self.page_var.set(f"Página {self.current_page}")
        mode_label = "escenas" if self._is_scenes_mode() else "cartas"
        self.status_var.set(f"{len(cards)} {mode_label} — página {self.current_page}")
        self._render_grid()

    # ── Grilla ────────────────────────────────────────────────────────────────
    CARD_W, CARD_H = 140, 210

    def _render_grid(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.thumb_cache.clear()
        self.card_widgets.clear()
        for i, card in enumerate(self.cards):
            self._create_card_widget(card, i)
        self._reflow_grid()
        self.canvas.yview_moveto(0)
        threading.Thread(target=self._load_thumbs, daemon=True).start()

    def _create_card_widget(self, card, idx):
        frame = tk.Frame(self.grid_frame, bg="#313244", relief="flat",
                         bd=0, cursor="hand2",
                         width=self.CARD_W, height=self.CARD_H)
        frame.pack_propagate(False)
        img_lbl = tk.Label(frame, bg="#45475a", text="⏳", fg="#6c7086",
                           font=("Segoe UI", 18), width=self.CARD_W, height=6)
        img_lbl.pack(fill="x")
        tk.Label(frame, text=card["name"][:22], bg="#313244", fg="#cdd6f4",
                 font=("Segoe UI", 8), wraplength=130, justify="center").pack(pady=(2,0))
        var = tk.BooleanVar(value=False)
        tk.Checkbutton(frame, variable=var, bg="#313244",
                       activebackground="#45475a", selectcolor="#1e1e2e",
                       command=lambda c=card["id"], v=var: self._toggle(c, v)).pack()
        tk.Button(frame, text="⬇", bg="#89b4fa", fg="#1e1e2e",
                  font=("Segoe UI", 8, "bold"), relief="flat",
                  command=lambda c=card: self._download_one(c)).pack(pady=(0,3))
        self.card_widgets[card["id"]] = {"frame": frame, "img_lbl": img_lbl, "var": var}

    def _reflow_grid(self):
        cw = self.canvas.winfo_width() or 800
        cols = max(1, cw // (self.CARD_W + 10))
        for i, card in enumerate(self.cards):
            w = self.card_widgets.get(card["id"])
            if w:
                r, c = divmod(i, cols)
                w["frame"].grid(row=r, column=c, padx=5, pady=5, sticky="nw")
        self.canvas.itemconfig(self.canvas_window, width=cw)

    def _load_thumbs(self):
        for card in list(self.cards):
            if card["id"] not in self.card_widgets: continue
            try:
                r = requests.get(card["thumb_url"], headers=HEADERS, timeout=10)
                r.raise_for_status()
                img = Image.open(io.BytesIO(r.content))
                img.thumbnail((self.CARD_W, 130))
                self.after(0, self._set_thumb, card["id"], img)
            except Exception:
                pass

    def _set_thumb(self, card_id, img):
        if card_id not in self.card_widgets: return
        photo = ImageTk.PhotoImage(img)
        self.thumb_cache[card_id] = photo
        lbl = self.card_widgets[card_id]["img_lbl"]
        lbl.config(image=photo, text="", width=self.CARD_W, height=130)
        lbl.image = photo

    # ── Selección ─────────────────────────────────────────────────────────────
    def _toggle(self, card_id, var):
        if var.get(): self.selected_cards.add(card_id)
        else:         self.selected_cards.discard(card_id)

    def _select_all(self):
        for card in self.cards:
            w = self.card_widgets.get(card["id"])
            if w:
                w["var"].set(True)
                self.selected_cards.add(card["id"])

    def _deselect_all(self):
        for card in self.cards:
            w = self.card_widgets.get(card["id"])
            if w: w["var"].set(False)
        self.selected_cards.clear()

    # ── Descarga manual ───────────────────────────────────────────────────────
    def _download_one(self, card):
        threading.Thread(target=self._dl_list, args=([card], False), daemon=True).start()

    def _download_selected(self):
        to_dl = [c for c in self.cards if c["id"] in self.selected_cards]
        if not to_dl:
            messagebox.showinfo("Sin selección", "Selecciona al menos una carta.")
            return
        threading.Thread(target=self._dl_list, args=(to_dl, False), daemon=True).start()

    # ── AUTO-DESCARGA ─────────────────────────────────────────────────────────
    def _start_auto(self):
        if self._auto_running: return
        self._auto_running  = True
        self._cancel_flag.clear()
        self._auto_total_dl = 0
        self._auto_ok_dl    = 0
        self.auto_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        # Capturar modo y parámetros antes de lanzar hilo
        prefix, view_path = self._get_mode_info()
        start_page, end_page = self._get_page_range()
        # Construir URL factory (captura filtros actuales)
        filters_snap = self._get_filters()
        is_scenes = self._is_scenes_mode()
        threading.Thread(
            target=self._auto_worker,
            args=(prefix, view_path, filters_snap, is_scenes, start_page, end_page),
            daemon=True
        ).start()

    def _cancel_auto(self):
        self._cancel_flag.set()
        self._log("⛔ Cancelación solicitada…")

    def _auto_worker(self, prefix, view_path, filters, is_scenes, start_page, end_page):
        page       = start_page
        pages_done = 0
        total_pages = (end_page - start_page + 1) if end_page > 0 else None

        while not self._cancel_flag.is_set():
            if end_page > 0 and page > end_page:
                break

            self.after(0, self._update_total_bar, pages_done, total_pages, page)
            self.after(0, self.status_var.set, f"🔍 Scrapeando página {page}…")
            self.after(0, self.page_var.set, f"Página {page}")

            if is_scenes:
                url = build_scenes_url(page=page, **filters)
            else:
                url = build_cards_url(page=page, **filters)

            self._log(f"━━━ Página {page} ━━━")

            cards, has_next, error = scrape_page(url, prefix, view_path)

            if error:
                self._log(f"  ❌ Error: {error}")
                self.after(0, self.status_var.set, f"❌ Error en página {page}: {error}")
                break

            if not cards:
                self._log(f"  📭 Sin resultados. Fin del scraping.")
                break

            self._log(f"  📦 {len(cards)} encontradas")
            self.after(0, self._show_auto_cards, list(cards))

            ok = self._dl_list(cards, is_auto=True)
            self._auto_ok_dl    += ok
            self._auto_total_dl += len(cards)
            pages_done          += 1

            self.after(0, self._update_total_bar, pages_done, total_pages, page)
            self._log(f"  ✅ {ok}/{len(cards)} descargadas. Total: {self._auto_ok_dl}")

            if self._cancel_flag.is_set():
                break

            if not has_next and end_page == 0:
                self._log("🏁 Última página alcanzada.")
                break

            page += 1
            time.sleep(1.2)

        self.after(0, self._auto_done)

    def _show_auto_cards(self, cards):
        self.cards = cards
        self.selected_cards.clear()
        self._render_grid()

    def _update_total_bar(self, done, total, cur_page):
        if total and total > 0:
            self.prog_total.config(maximum=total, value=done)
            self.prog_total_lbl.config(text=f"Pág {done}/{total}")
        else:
            self.prog_total.config(maximum=max(done+1, 10), value=done)
            self.prog_total_lbl.config(text=f"Pág {done}/?")

    def _auto_done(self):
        self._auto_running = False
        self.auto_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        msg = (f"✅ Auto-descarga completada\n"
               f"OK: {self._auto_ok_dl} / {self._auto_total_dl}\n"
               f"📁 {self.save_dir}")
        self._log(msg)
        self.status_var.set(f"✅ {self._auto_ok_dl} archivos descargados en total.")
        messagebox.showinfo("Auto-descarga completa", msg)

    # ── Worker de descarga ────────────────────────────────────────────────────
    def _dl_list(self, cards, is_auto=False):
        os.makedirs(self.save_dir, exist_ok=True)
        total = len(cards)
        ok = 0

        self.after(0, self.prog_page.config, {"maximum": total, "value": 0})
        self.after(0, self.prog_page_lbl.config, {"text": f"0 / {total}"})

        for i, card in enumerate(cards, 1):
            if is_auto and self._cancel_flag.is_set():
                break

            prefix = card.get("prefix", "KK")
            fname = f"{prefix}_{card['id']}_{card['name'][:30].strip()}.png"
            fname = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", fname)
            path  = os.path.join(self.save_dir, fname)

            if os.path.exists(path):
                self._log(f"    ⏭ Ya existe: {fname}")
                ok += 1
            else:
                try:
                    r = requests.get(card["download_url"], headers=HEADERS, timeout=30)
                    r.raise_for_status()
                    with open(path, "wb") as f:
                        f.write(r.content)
                    ok += 1
                    self._log(f"    ⬇ {fname}")
                except Exception as e:
                    self._log(f"    ❌ {card['name']}: {e}")

            self.after(0, self.prog_page.config,    {"value": i})
            self.after(0, self.prog_page_lbl.config, {"text": f"{i} / {total}"})
            self.after(0, self.status_var.set,
                       f"{'🚀 ' if is_auto else '⬇ '}{i}/{total}: {card['name'][:30]}")

        return ok


if __name__ == "__main__":
    app = KoikatsuDownloader()
    app.mainloop()