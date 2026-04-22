"""
VK Group Downloader v3 — JDownloader Edition
Extrae links de posts de un grupo VK y los lista para usar con JDownloader.
Requiere: pip install requests pillow
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
import re
import time
import io
import mimetypes
import requests
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime, timedelta
from PIL import Image, ImageTk


# ─────────────────────────────────────────────
#  VK API
# ─────────────────────────────────────────────

VK_API = "https://api.vk.com/method"
VK_VER = "5.199"

MIME_EXT = {
    "image/jpeg":       ".jpg",
    "image/jpg":        ".jpg",
    "image/png":        ".png",
    "image/gif":        ".gif",
    "image/webp":       ".webp",
    "image/bmp":        ".bmp",
    "image/tiff":       ".tiff",
    "application/pdf":  ".pdf",
    "application/zip":  ".zip",
    "application/x-zip-compressed": ".zip",
    "application/x-rar-compressed": ".rar",
    "application/vnd.rar": ".rar",
    "application/octet-stream": "",
    "video/mp4":        ".mp4",
    "audio/mpeg":       ".mp3",
    "text/plain":       ".txt",
}


def vk_call(method, params, token, retries=3):
    params = {**params, "access_token": token, "v": VK_VER}
    for attempt in range(retries):
        try:
            r = requests.get(f"{VK_API}/{method}", params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise RuntimeError(
                    f"VK error {data['error']['error_code']}: {data['error']['error_msg']}")
            return data["response"]
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def resolve_group_id(owner, token):
    owner = owner.strip()
    if re.match(r"^-?\d+$", owner):
        return owner
    resp = vk_call("groups.getById", {"group_id": owner.lstrip("-")}, token)
    return f"-{resp[0]['id']}"


def get_total_posts(owner_id, token):
    resp = vk_call("wall.get", {"owner_id": owner_id, "count": 1,
                                 "filter": "owner"}, token)
    return resp.get("count", 0)


def fetch_range_posts(owner_id, token, post_from, post_to,
                      progress_cb, cancel_ev):
    offset_start = post_from - 1
    need = post_to - post_from + 1
    all_posts = []
    batch = 100
    fetched = 0

    while not cancel_ev.is_set() and fetched < need:
        to_get = min(batch, need - fetched)
        resp = vk_call("wall.get", {
            "owner_id": owner_id,
            "offset": offset_start + fetched,
            "count": to_get,
            "filter": "owner",
        }, token)
        items = resp.get("items", [])
        total = resp.get("count", 0)
        all_posts.extend(items)
        fetched += len(items)
        progress_cb(
            f"Posts obtenidos: {len(all_posts)} / {need}  (total en grupo: {total})",
            need, len(all_posts)
        )
        if not items:
            break
        time.sleep(0.35)

    return all_posts


def detect_extension(url: str, content_type: str) -> str:
    path = urlparse(url).path
    url_ext = Path(path).suffix.lower()
    known = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
             ".tiff", ".pdf", ".zip", ".rar", ".mp4", ".mp3",
             ".txt", ".doc", ".docx", ".psd", ".ai", ".svg"}
    if url_ext in known:
        return url_ext
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime in MIME_EXT and MIME_EXT[mime]:
        return MIME_EXT[mime]
    ext = mimetypes.guess_extension(mime)
    if ext and ext != ".jpe":
        return ext.replace(".jpe", ".jpg")
    return url_ext or ""


def extract_urls(posts):
    results = []

    def add(url, post_id, att_type, name="", text=""):
        if url:
            results.append({"url": url, "post_id": post_id,
                             "type": att_type, "name": name, "text": text})

    for post in posts:
        pid = post["id"]
        text = post.get("text", "")[:200]
        for att in post.get("attachments", []):
            t = att.get("type")
            obj = att.get(t, {})
            if t == "photo":
                sizes = obj.get("sizes", [])
                if sizes:
                    best = max(sizes,
                               key=lambda s: s.get("width", 0) * s.get("height", 0))
                    add(best.get("url"), pid, "photo",
                        f"photo_{obj.get('id')}", text)
            elif t == "doc":
                add(obj.get("url"), pid, "doc",
                    obj.get("title", f"doc_{obj.get('id')}"), text)
            elif t == "video":
                img = obj.get("image", [])
                if img:
                    best = max(img, key=lambda s: s.get("width", 0))
                    add(best.get("url"), pid, "video_thumb",
                        f"video_{obj.get('id')}_thumb", text)
            elif t == "link":
                photo = obj.get("photo", {})
                sizes = photo.get("sizes", []) if photo else []
                if sizes:
                    best = max(sizes, key=lambda s: s.get("width", 0))
                    add(best.get("url"), pid, "link_photo",
                        f"link_{pid}", text)
    return results


def safe_filename(name, max_len=80):
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return name[:max_len]


def download_file(item, folder, skip_existing, speed_cb):
    url      = item["url"]
    post_id  = item["post_id"]
    att_type = item["type"]
    raw_name = safe_filename(item["name"])

    try:
        head = requests.head(url, timeout=10, allow_redirects=True)
        ct = head.headers.get("content-type", "")
    except Exception:
        ct = ""

    ext = detect_extension(url, ct)
    name_no_ext = raw_name
    if raw_name.lower().endswith(ext.lower()) and ext:
        name_no_ext = raw_name[: -len(ext)]

    filename = f"post{post_id}_{att_type}_{name_no_ext}{ext}"
    dest = folder / filename

    if skip_existing and dest.exists():
        return False, f"[SKIP] {filename}", dest, 0

    try:
        r = requests.get(url, timeout=30, stream=True)
        r.raise_for_status()

        real_ct = r.headers.get("content-type", ct)
        real_ext = detect_extension(url, real_ct)
        if real_ext and real_ext != ext:
            name_no_ext2 = raw_name
            if raw_name.lower().endswith(real_ext.lower()):
                name_no_ext2 = raw_name[: -len(real_ext)]
            filename = f"post{post_id}_{att_type}_{name_no_ext2}{real_ext}"
            dest = folder / filename
            if skip_existing and dest.exists():
                return False, f"[SKIP] {filename}", dest, 0

        total_size = int(r.headers.get("content-length", 0))
        downloaded = 0
        start = time.time()

        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    elapsed = time.time() - start
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    speed_cb(speed, downloaded, total_size)

        return True, f"[OK]   {filename}", dest, downloaded
    except Exception as e:
        return False, f"[ERR]  {filename} — {e}", None, 0


# ─────────────────────────────────────────────
#  Estilos
# ─────────────────────────────────────────────

DARK_BG  = "#0d1117"
PANEL_BG = "#161b22"
CARD_BG  = "#1c2128"
BORDER   = "#30363d"
ACCENT   = "#e94560"
ACCENT2  = "#1f6feb"
FG       = "#e6edf3"
FG2      = "#8b949e"
SUCCESS  = "#3fb950"
WARNING  = "#d29922"
MONO     = ("Consolas", 9)
UI       = ("Segoe UI", 10)
HEAD     = ("Segoe UI Semibold", 11)
SMALL    = ("Segoe UI", 8)


def styled_btn(parent, text, cmd, color=ACCENT2, **kw):
    return tk.Button(parent, text=text, command=cmd,
                     bg=color, fg=FG, activebackground=color,
                     activeforeground=FG, relief="flat",
                     font=UI, cursor="hand2", padx=12, pady=6, **kw)


def mk_entry(parent, var, width=30, show=""):
    return tk.Entry(parent, textvariable=var, width=width,
                    bg=CARD_BG, fg=FG, insertbackground=FG,
                    font=UI, relief="flat", bd=4,
                    highlightthickness=1, highlightbackground=BORDER,
                    show=show)


def mk_spinbox(parent, var, lo=0, hi=999999, width=8):
    return tk.Spinbox(parent, textvariable=var, from_=lo, to=hi,
                      width=width, bg=CARD_BG, fg=FG,
                      buttonbackground=CARD_BG, font=UI, relief="flat",
                      highlightthickness=1, highlightbackground=BORDER)


def mk_lbl(parent, text, fg=FG2, bg=DARK_BG):
    return tk.Label(parent, text=text, bg=bg, fg=fg, font=UI)


# ─────────────────────────────────────────────
#  Galería
# ─────────────────────────────────────────────

class GalleryTab(tk.Frame):
    THUMB = 130

    def __init__(self, parent):
        super().__init__(parent, bg=DARK_BG)
        self._images = []
        self._count  = 0
        self._cols   = 5
        self._row    = 0
        self._col    = 0

        top = tk.Frame(self, bg=DARK_BG)
        top.pack(fill="x", padx=10, pady=(8, 4))
        self.count_lbl = tk.Label(top, text="0 imágenes",
                                   bg=DARK_BG, fg=FG2, font=UI)
        self.count_lbl.pack(side="left")

        container = tk.Frame(self, bg=DARK_BG)
        container.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self.canvas = tk.Canvas(container, bg=DARK_BG, highlightthickness=0)
        vsb = ttk.Scrollbar(container, orient="vertical",
                             command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.frame = tk.Frame(self.canvas, bg=DARK_BG)
        self._win = self.canvas.create_window(
            (0, 0), window=self.frame, anchor="nw")

        self.frame.bind("<Configure>",
                        lambda e: self.canvas.configure(
                            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(
                                 int(-1 * e.delta / 120), "units"))

    def _on_resize(self, e):
        cols = max(1, e.width // (self.THUMB + 10))
        self._cols = cols
        self.canvas.itemconfig(self._win, width=e.width)

    def add_image(self, path: Path):
        try:
            img = Image.open(path)
            img.thumbnail((self.THUMB, self.THUMB), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
        except Exception:
            return

        self._images.append(photo)
        self._count += 1
        self.count_lbl.config(text=f"{self._count} imágenes")

        cell = tk.Frame(self.frame, bg=CARD_BG,
                        highlightthickness=1, highlightbackground=BORDER)
        cell.grid(row=self._row, column=self._col, padx=4, pady=4, sticky="nw")
        tk.Label(cell, image=photo, bg=CARD_BG).pack()
        name = path.name[:18] + "…" if len(path.name) > 18 else path.name
        tk.Label(cell, text=name, bg=CARD_BG, fg=FG2,
                 font=SMALL, wraplength=self.THUMB).pack()

        self._col += 1
        if self._col >= self._cols:
            self._col = 0
            self._row += 1

    def clear(self):
        for w in self.frame.winfo_children():
            w.destroy()
        self._images.clear()
        self._count = self._row = self._col = 0
        self.count_lbl.config(text="0 imágenes")


# ─────────────────────────────────────────────
#  Posts Tab
# ─────────────────────────────────────────────

class PostsTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=DARK_BG)
        top = tk.Frame(self, bg=DARK_BG)
        top.pack(fill="x", padx=10, pady=(8, 4))
        self.count_lbl = tk.Label(top, text="0 posts",
                                   bg=DARK_BG, fg=FG2, font=UI)
        self.count_lbl.pack(side="left")

        self.text = scrolledtext.ScrolledText(
            self, bg=PANEL_BG, fg=FG, font=MONO,
            relief="flat", wrap="word", state="disabled")
        self.text.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.text.tag_configure("post_id",  foreground=ACCENT2,
                                font=("Segoe UI Semibold", 10))
        self.text.tag_configure("text",     foreground=FG)
        self.text.tag_configure("attachs",  foreground=FG2, font=SMALL)
        self.text.tag_configure("sep",      foreground=BORDER)
        self._count = 0

    def add_posts(self, posts):
        self.text.config(state="normal")
        for p in posts:
            self._count += 1
            pid  = p.get("id", "?")
            date = datetime.fromtimestamp(p.get("date", 0)).strftime("%Y-%m-%d %H:%M")
            text = p.get("text", "").strip() or "(sin texto)"
            atts = p.get("attachments", [])
            att_types = ", ".join(a.get("type", "?") for a in atts) if atts else "—"
            self.text.insert("end", f"  Post #{pid}  ·  {date}\n", "post_id")
            self.text.insert("end", f"  {text[:300]}\n", "text")
            self.text.insert("end", f"  Adjuntos: {att_types}\n", "attachs")
            self.text.insert("end", "  " + "─" * 60 + "\n", "sep")
        self.text.see("end")
        self.text.config(state="disabled")
        self.count_lbl.config(text=f"{self._count} posts")

    def clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")
        self._count = 0
        self.count_lbl.config(text="0 posts")


# ─────────────────────────────────────────────
#  Links Tab (JDownloader)
# ─────────────────────────────────────────────

class LinksTab(tk.Frame):
    """
    Muestra todos los links extraídos de los posts para copiarlos
    a JDownloader u otro gestor de descargas.
    """

    def __init__(self, parent):
        super().__init__(parent, bg=DARK_BG)
        self._links = []   # lista de dicts con url, post_id, type

        # ── barra superior ──────────────────────────────
        top = tk.Frame(self, bg=DARK_BG)
        top.pack(fill="x", padx=10, pady=(8, 4))

        self.count_lbl = tk.Label(top, text="0 links",
                                   bg=DARK_BG, fg=FG2, font=UI)
        self.count_lbl.pack(side="left")

        # Filtros rápidos
        filter_frame = tk.Frame(top, bg=DARK_BG)
        filter_frame.pack(side="left", padx=(20, 0))

        self.show_photos = tk.BooleanVar(value=True)
        self.show_docs   = tk.BooleanVar(value=True)
        self.show_thumbs = tk.BooleanVar(value=True)

        for var, label in [(self.show_photos, "Fotos"),
                            (self.show_docs,   "Docs"),
                            (self.show_thumbs, "Thumbs")]:
            tk.Checkbutton(filter_frame, text=label, variable=var,
                           bg=DARK_BG, fg=FG, selectcolor=CARD_BG,
                           activebackground=DARK_BG, activeforeground=FG,
                           font=SMALL, command=self._refresh
                           ).pack(side="left", padx=(0, 6))

        # Botones de acción
        btn_frame = tk.Frame(top, bg=DARK_BG)
        btn_frame.pack(side="right")

        styled_btn(btn_frame, "📋 Copiar todos",
                   self._copy_all, ACCENT2).pack(side="left", padx=(0, 6))
        styled_btn(btn_frame, "💾 Exportar .txt",
                   self._export_txt, CARD_BG).pack(side="left", padx=(0, 6))
        styled_btn(btn_frame, "🗑 Limpiar",
                   self.clear, CARD_BG).pack(side="left")

        # ── área de texto con links ──────────────────────
        self.text = scrolledtext.ScrolledText(
            self, bg=PANEL_BG, fg=FG, font=MONO,
            relief="flat", wrap="none", state="disabled")
        self.text.pack(fill="both", expand=True, padx=10, pady=(0, 4))

        # Tags de colores por tipo
        self.text.tag_configure("photo",      foreground="#58a6ff")
        self.text.tag_configure("doc",        foreground="#d2a679")
        self.text.tag_configure("video_thumb",foreground="#bc8cff")
        self.text.tag_configure("link_photo", foreground="#79c0ff")
        self.text.tag_configure("header",     foreground=FG2, font=SMALL)

        # ── barra de estado inferior ─────────────────────
        bot = tk.Frame(self, bg=PANEL_BG,
                       highlightthickness=1, highlightbackground=BORDER)
        bot.pack(fill="x", padx=10, pady=(0, 8))
        self.status_lbl = tk.Label(
            bot,
            text="ℹ️  Copia los links y pégalos en JDownloader → Añadir enlaces",
            bg=PANEL_BG, fg=FG2, font=SMALL, anchor="w")
        self.status_lbl.pack(fill="x", padx=8, pady=4)

    # ── métodos públicos ─────────────────────────────────

    def add_links(self, items: list):
        """Recibe la lista de dicts {url, post_id, type, name} y los agrega."""
        self._links.extend(items)
        self._refresh()

    def clear(self):
        self._links.clear()
        self._render([])
        self.count_lbl.config(text="0 links")

    # ── métodos internos ─────────────────────────────────

    def _filtered(self):
        out = []
        for it in self._links:
            t = it["type"]
            if t == "photo" and not self.show_photos.get():
                continue
            if t == "doc" and not self.show_docs.get():
                continue
            if t in ("video_thumb", "link_photo") and not self.show_thumbs.get():
                continue
            out.append(it)
        return out

    def _refresh(self):
        filtered = self._filtered()
        self._render(filtered)
        self.count_lbl.config(text=f"{len(filtered)} links "
                                    f"({len(self._links)} total)")

    def _render(self, items):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")

        if not items:
            self.text.insert("end",
                "  (sin links — primero extrae posts con el botón 'Extraer links')\n",
                "header")
            self.text.config(state="disabled")
            return

        # Agrupar por post_id para mejor legibilidad
        by_post = {}
        for it in items:
            pid = it["post_id"]
            by_post.setdefault(pid, []).append(it)

        for pid, its in by_post.items():
            self.text.insert("end", f"# Post #{pid}\n", "header")
            for it in its:
                tag  = it["type"]
                name = it.get("name", "")
                url  = it["url"]
                line = f"  {url}\n"
                self.text.insert("end", line, tag)
            self.text.insert("end", "\n")

        self.text.config(state="disabled")

    def _urls_plain(self):
        """Retorna solo las URLs (una por línea) de los items filtrados."""
        return "\n".join(it["url"] for it in self._filtered())

    def _copy_all(self):
        urls = self._urls_plain()
        if not urls:
            messagebox.showinfo("Sin links", "No hay links para copiar.")
            return
        self.clipboard_clear()
        self.clipboard_append(urls)
        total = len(self._filtered())
        self.status_lbl.config(
            text=f"✅  {total} links copiados al portapapeles — "
                 "pégalos en JDownloader → Añadir enlaces",
            fg=SUCCESS)
        # Restaurar mensaje después de 4 s
        self.after(4000, lambda: self.status_lbl.config(
            text="ℹ️  Copia los links y pégalos en JDownloader → Añadir enlaces",
            fg=FG2))

    def _export_txt(self):
        if not self._links:
            messagebox.showinfo("Sin links", "No hay links para exportar.")
            return
        path = filedialog.asksaveasfilename(
            title="Guardar links como…",
            defaultextension=".txt",
            filetypes=[("Archivo de texto", "*.txt"), ("Todos", "*.*")],
            initialfile="vk_links_jdownloader.txt")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._urls_plain())
        total = len(self._filtered())
        messagebox.showinfo("Exportado",
                            f"{total} links guardados en:\n{path}")


# ─────────────────────────────────────────────
#  App principal
# ─────────────────────────────────────────────

class VKDownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VK Group Downloader v3 — JDownloader Edition")
        self.configure(bg=DARK_BG)
        self.resizable(True, True)
        self.minsize(820, 660)
        self.geometry("980x740")

        self._queue      = queue.Queue()
        self._cancel     = threading.Event()
        self._worker     = None
        self._start_time = None
        self._total_bytes = 0

        self._build_ui()
        self._poll()

    # ── UI ──────────────────────────────────

    def _build_ui(self):
        hdr = tk.Frame(self, bg=ACCENT2, padx=16, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⬇  VK Group Downloader",
                 font=HEAD, bg=ACCENT2, fg=FG).pack(side="left")
        tk.Label(hdr, text="v3  ·  JDownloader Edition",
                 font=SMALL, bg=ACCENT2, fg=FG2).pack(side="right")

        paned = tk.PanedWindow(self, orient="horizontal",
                               bg=DARK_BG, sashwidth=4, sashrelief="flat")
        paned.pack(fill="both", expand=True)

        left = tk.Frame(paned, bg=DARK_BG)
        paned.add(left, minsize=340, width=400)
        self._build_config(left)
        self._build_stats(left)
        self._build_log(left)

        right = tk.Frame(paned, bg=DARK_BG)
        paned.add(right, minsize=380)
        nb = ttk.Notebook(right)
        s = ttk.Style(self)
        s.theme_use("default")
        s.configure("TNotebook",      background=DARK_BG, borderwidth=0)
        s.configure("TNotebook.Tab",  background=PANEL_BG, foreground=FG2,
                    padding=[12, 6], font=UI)
        s.map("TNotebook.Tab",
              background=[("selected", CARD_BG)],
              foreground=[("selected", FG)])
        s.configure("TProgressbar",   troughcolor=PANEL_BG,
                    background=ACCENT2, thickness=6)
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        # ── pestañas ──
        self.links_tab   = LinksTab(nb)
        self.posts_tab   = PostsTab(nb)
        self.gallery_tab = GalleryTab(nb)

        nb.add(self.links_tab,   text="🔗  Links (JDownloader)")
        nb.add(self.posts_tab,   text="📄  Posts")
        nb.add(self.gallery_tab, text="🖼  Galería")

    def _build_config(self, parent):
        cfg = tk.LabelFrame(parent, text=" Configuración ",
                            bg=DARK_BG, fg=FG2, font=UI,
                            bd=1, relief="groove", padx=10, pady=8)
        cfg.pack(fill="x", padx=8, pady=(8, 4))

        # Token
        mk_lbl(cfg, "Access Token:").grid(
            row=0, column=0, sticky="w", pady=3, padx=(0, 8))
        self.token_var = tk.StringVar()
        te = mk_entry(cfg, self.token_var, width=36, show="•")
        te.grid(row=0, column=1, columnspan=3, sticky="ew", pady=3)
        tk.Button(cfg, text="👁", bg=CARD_BG, fg=FG2, relief="flat",
                  cursor="hand2",
                  command=lambda: te.config(
                      show="" if te.cget("show") == "•" else "•")
                  ).grid(row=0, column=4, padx=(4, 0))

        # Owner
        mk_lbl(cfg, "Owner ID:").grid(
            row=1, column=0, sticky="w", pady=3, padx=(0, 8))
        self.owner_var = tk.StringVar(value="-196068525")
        mk_entry(cfg, self.owner_var, width=22).grid(
            row=1, column=1, sticky="ew", pady=3)

        self.total_lbl = tk.Label(cfg, text="", bg=DARK_BG,
                                   fg=SUCCESS, font=SMALL)
        self.total_lbl.grid(row=1, column=2, columnspan=2,
                             sticky="w", padx=(8, 0))
        tk.Button(cfg, text="🔍 Consultar total", bg=CARD_BG, fg=FG2,
                  font=SMALL, relief="flat", cursor="hand2",
                  command=self._query_total
                  ).grid(row=1, column=4, padx=(4, 0))

        # Rango de posts
        range_frame = tk.LabelFrame(cfg, text=" Rango de posts ",
                                     bg=DARK_BG, fg=FG2, font=SMALL,
                                     bd=1, relief="groove", padx=8, pady=6)
        range_frame.grid(row=2, column=0, columnspan=5,
                         sticky="ew", pady=(6, 4))

        mk_lbl(range_frame, "Desde post #:").grid(
            row=0, column=0, sticky="w", padx=(0, 6))
        self.from_var = tk.IntVar(value=1)
        mk_spinbox(range_frame, self.from_var, lo=1).grid(
            row=0, column=1, sticky="w")

        mk_lbl(range_frame, "  Hasta post #:").grid(
            row=0, column=2, sticky="w", padx=(8, 6))
        self.to_var = tk.IntVar(value=200)
        mk_spinbox(range_frame, self.to_var, lo=1).grid(
            row=0, column=3, sticky="w")

        info = tk.Label(range_frame,
                        text="  Post #1 = el más reciente del grupo",
                        bg=DARK_BG, fg=FG2, font=SMALL)
        info.grid(row=0, column=4, sticky="w", padx=(12, 0))

        # Carpeta (solo para modo descarga)
        mk_lbl(cfg, "Carpeta:").grid(
            row=3, column=0, sticky="w", pady=3, padx=(0, 8))
        self.folder_var = tk.StringVar(
            value=str(Path.home() / "VK_Downloads"))
        mk_entry(cfg, self.folder_var, width=30).grid(
            row=3, column=1, columnspan=3, sticky="ew", pady=3)
        tk.Button(cfg, text="📂", bg=CARD_BG, fg=FG2, relief="flat",
                  cursor="hand2", command=self._pick_folder
                  ).grid(row=3, column=4, padx=(4, 0))

        # Opciones
        opts = tk.Frame(cfg, bg=DARK_BG)
        opts.grid(row=4, column=0, columnspan=5, sticky="w", pady=(6, 2))
        self.skip_var   = tk.BooleanVar(value=True)
        self.photos_var = tk.BooleanVar(value=True)
        self.docs_var   = tk.BooleanVar(value=True)
        self.thumbs_var = tk.BooleanVar(value=False)
        for var, text in [(self.skip_var,   "Saltar existentes"),
                           (self.photos_var, "Fotos"),
                           (self.docs_var,   "Docs"),
                           (self.thumbs_var, "Thumbs video")]:
            tk.Checkbutton(opts, text=text, variable=var,
                           bg=DARK_BG, fg=FG, selectcolor=CARD_BG,
                           activebackground=DARK_BG, activeforeground=FG,
                           font=UI).pack(side="left", padx=(0, 10))

        cfg.columnconfigure(1, weight=1)

        # ── Botones principales ──────────────────────────
        btn_row = tk.Frame(parent, bg=DARK_BG)
        btn_row.pack(fill="x", padx=8, pady=4)

        # Botón principal: solo extraer links (sin descargar)
        self.extract_btn = styled_btn(
            btn_row, "🔗 Extraer links", self._extract_links, ACCENT2)
        self.extract_btn.pack(side="left", padx=(0, 6))

        # Botón secundario: descargar directamente (comportamiento original)
        self.start_btn = styled_btn(
            btn_row, "▶ Descargar", self._start, ACCENT)
        self.start_btn.pack(side="left", padx=(0, 8))

        self.cancel_btn = styled_btn(btn_row, "⏹ Cancelar",
                                     self._cancel_download, CARD_BG)
        self.cancel_btn.config(state="disabled")
        self.cancel_btn.pack(side="left")
        styled_btn(btn_row, "🗑 Limpiar",
                   self._clear_all, CARD_BG).pack(side="right")

    def _build_stats(self, parent):
        sf = tk.Frame(parent, bg=PANEL_BG,
                      highlightthickness=1, highlightbackground=BORDER)
        sf.pack(fill="x", padx=8, pady=4)

        self.status_lbl = tk.Label(sf, text="Listo.", bg=PANEL_BG,
                                   fg=FG2, font=UI, anchor="w")
        self.status_lbl.pack(fill="x", padx=10, pady=(6, 2))

        bar_f = tk.Frame(sf, bg=PANEL_BG)
        bar_f.pack(fill="x", padx=10, pady=(0, 4))
        self.progress = ttk.Progressbar(bar_f, mode="determinate")
        self.progress.pack(fill="x", side="left", expand=True, padx=(0, 8))
        self.pct_lbl = tk.Label(bar_f, text="0%", bg=PANEL_BG,
                                 fg=FG2, font=SMALL, width=4)
        self.pct_lbl.pack(side="left")

        sr = tk.Frame(sf, bg=PANEL_BG)
        sr.pack(fill="x", padx=10, pady=(0, 6))
        self.speed_lbl = self._stat(sr, "Velocidad", "—")
        self.size_lbl  = self._stat(sr, "Descargado", "—")
        self.eta_lbl   = self._stat(sr, "ETA", "—")
        self.files_lbl = self._stat(sr, "Archivos", "0 / 0")

    def _stat(self, parent, title, val):
        f = tk.Frame(parent, bg=CARD_BG,
                     highlightthickness=1, highlightbackground=BORDER)
        f.pack(side="left", expand=True, fill="x", padx=(0, 4))
        tk.Label(f, text=title, bg=CARD_BG, fg=FG2, font=SMALL).pack(pady=(4, 0))
        lv = tk.Label(f, text=val, bg=CARD_BG,
                      fg=SUCCESS, font=("Segoe UI Semibold", 10))
        lv.pack(pady=(0, 4))
        return lv

    def _build_log(self, parent):
        lf = tk.LabelFrame(parent, text=" Log ", bg=DARK_BG, fg=FG2,
                            font=UI, bd=1, relief="groove")
        lf.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self.log = scrolledtext.ScrolledText(
            lf, bg=PANEL_BG, fg=FG, font=MONO,
            relief="flat", wrap="none", state="disabled")
        self.log.pack(fill="both", expand=True, padx=4, pady=4)
        self.log.tag_configure("ok",   foreground=SUCCESS)
        self.log.tag_configure("err",  foreground=ACCENT)
        self.log.tag_configure("skip", foreground=FG2)
        self.log.tag_configure("info", foreground=WARNING)

    # ── helpers ─────────────────────────────

    def _pick_folder(self):
        d = filedialog.askdirectory(title="Carpeta destino")
        if d:
            self.folder_var.set(d)

    def _log(self, msg, tag="header"):
        self.log.config(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.insert("end", f"[{ts}] {msg}\n", tag)
        self.log.see("end")
        self.log.config(state="disabled")

    def _clear_all(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")
        self.gallery_tab.clear()
        self.posts_tab.clear()
        self.links_tab.clear()
        self.progress["value"] = 0
        self.pct_lbl.config(text="0%")
        for lv in (self.speed_lbl, self.size_lbl, self.eta_lbl):
            lv.config(text="—")
        self.files_lbl.config(text="0 / 0")

    def _fmt_bytes(self, b):
        if b < 1024:        return f"{b} B"
        if b < 1_048_576:   return f"{b/1024:.1f} KB"
        if b < 1_073_741_824: return f"{b/1_048_576:.1f} MB"
        return f"{b/1_073_741_824:.2f} GB"

    def _fmt_speed(self, bps):
        return self._fmt_bytes(int(bps)) + "/s"

    # ── query total ─────────────────────────

    def _query_total(self):
        token = self.token_var.get().strip()
        owner = self.owner_var.get().strip()
        if not token or not owner:
            messagebox.showwarning("Faltan datos",
                                   "Ingresa Token y Owner ID primero.")
            return
        self.total_lbl.config(text="Consultando…", fg=WARNING)

        def _fetch():
            try:
                oid = resolve_group_id(owner, token)
                total = get_total_posts(oid, token)
                self._queue.put(("total_posts", total))
            except Exception as e:
                self._queue.put(("total_posts_err", str(e)))

        threading.Thread(target=_fetch, daemon=True).start()

    # ── Extraer links (sin descargar) ────────

    def _extract_links(self):
        """Solo obtiene posts y extrae URLs; las muestra en la pestaña Links."""
        token = self.token_var.get().strip()
        if not token:
            messagebox.showerror("Token requerido",
                                 "Ingresa tu Access Token de VK.")
            return
        owner = self.owner_var.get().strip()
        if not owner:
            messagebox.showerror("Owner ID requerido",
                                 "Ingresa el ID del grupo.")
            return

        post_from = self.from_var.get()
        post_to   = self.to_var.get()
        if post_from < 1:
            messagebox.showerror("Rango inválido", "Desde post debe ser ≥ 1.")
            return
        if post_to < post_from:
            messagebox.showerror("Rango inválido",
                                 "Hasta post debe ser ≥ Desde post.")
            return

        self._cancel.clear()
        self.extract_btn.config(state="disabled")
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress["value"] = 0
        self.links_tab.clear()
        self.posts_tab.clear()

        self._worker = threading.Thread(
            target=self._run_extract,
            args=(token, owner, post_from, post_to),
            daemon=True)
        self._worker.start()

    def _run_extract(self, token, owner, post_from, post_to):
        """Hilo: solo extrae posts y sus URLs sin descargar nada."""
        q = self._queue

        def info(msg, total=0, current=0):
            q.put(("status", msg))
            if total:
                q.put(("fetch_prog", current, total))

        def log(msg, tag="header"):
            q.put(("log", msg, tag))

        try:
            info("Resolviendo grupo…")
            owner_id = resolve_group_id(owner, token)
            log(f"Grupo: {owner_id}  |  Posts {post_from} → {post_to}", "info")

            info("Obteniendo posts…")
            posts = fetch_range_posts(owner_id, token,
                                      post_from, post_to,
                                      info, self._cancel)
            log(f"Posts obtenidos: {len(posts)}", "info")

            if posts:
                q.put(("add_posts", posts))

            if self._cancel.is_set():
                log("Cancelado.", "err")
                return

            items = extract_urls(posts)
            log(f"Links extraídos: {len(items)}", "info")

            if items:
                q.put(("add_links", items))
            else:
                log("Sin adjuntos encontrados.", "err")

            q.put(("progress", 100, len(items), len(items)))

        except Exception as e:
            log(f"Error: {e}", "err")
        finally:
            q.put(("done",))

    # ── worker (descarga directa) ────────────

    def _start(self):
        token = self.token_var.get().strip()
        if not token:
            messagebox.showerror("Token requerido",
                                 "Ingresa tu Access Token de VK.")
            return
        owner = self.owner_var.get().strip()
        if not owner:
            messagebox.showerror("Owner ID requerido",
                                 "Ingresa el ID del grupo.")
            return

        post_from = self.from_var.get()
        post_to   = self.to_var.get()
        if post_from < 1:
            messagebox.showerror("Rango inválido", "Desde post debe ser ≥ 1.")
            return
        if post_to < post_from:
            messagebox.showerror("Rango inválido",
                                 "Hasta post debe ser ≥ Desde post.")
            return

        folder = Path(self.folder_var.get().strip())
        folder.mkdir(parents=True, exist_ok=True)

        self._cancel.clear()
        self._total_bytes = 0
        self._start_time  = time.time()
        self.start_btn.config(state="disabled")
        self.extract_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress["value"] = 0
        self.gallery_tab.clear()
        self.posts_tab.clear()
        self.links_tab.clear()

        self._worker = threading.Thread(
            target=self._run,
            args=(token, owner, post_from, post_to, folder),
            daemon=True)
        self._worker.start()

    def _cancel_download(self):
        self._cancel.set()
        self._log("Cancelando…", "info")

    def _run(self, token, owner, post_from, post_to, folder):
        q = self._queue

        def info(msg, total=0, current=0):
            q.put(("status", msg))
            if total:
                q.put(("fetch_prog", current, total))

        def log(msg, tag="header"):
            q.put(("log", msg, tag))

        try:
            info("Resolviendo grupo…")
            owner_id = resolve_group_id(owner, token)
            log(f"Grupo: {owner_id}  |  Posts {post_from} → {post_to}", "info")

            info("Obteniendo posts…")
            posts = fetch_range_posts(owner_id, token,
                                      post_from, post_to,
                                      info, self._cancel)
            log(f"Posts obtenidos: {len(posts)}", "info")

            if posts:
                q.put(("add_posts", posts))

            if self._cancel.is_set():
                log("Cancelado.", "err")
                return

            items = extract_urls(posts)

            filtered = []
            for it in items:
                t = it["type"]
                if t == "photo" and not self.photos_var.get(): continue
                if t == "doc"   and not self.docs_var.get():   continue
                if t in ("video_thumb", "link_photo") \
                        and not self.thumbs_var.get(): continue
                filtered.append(it)

            total_files = len(filtered)
            log(f"Archivos a descargar: {total_files}", "info")
            if not filtered:
                log("Sin adjuntos con los filtros actuales.", "err")
                return

            # También mostrar links mientras descarga
            q.put(("add_links", filtered))

            skip        = self.skip_var.get()
            done        = 0
            total_bytes = 0

            for i, item in enumerate(filtered):
                if self._cancel.is_set():
                    log("Cancelado.", "err")
                    break

                def speed_cb(speed, dl, _ts,
                             _i=i, _done=done,
                             _total=total_files, _prev=total_bytes):
                    q.put(("speed", speed, _prev + dl, _i + 1, _total, _done))

                ok, msg, dest, nbytes = download_file(
                    item, folder, skip, speed_cb)

                tag = "ok" if ok else ("skip" if "SKIP" in msg else "err")
                log(msg, tag)

                if ok:
                    done        += 1
                    total_bytes += nbytes
                    if dest and item["type"] in ("photo", "link_photo"):
                        q.put(("add_image", dest))

                pct = int((i + 1) / total_files * 100)
                q.put(("progress", pct, i + 1, total_files))
                time.sleep(0.02)

            elapsed = time.time() - self._start_time
            avg = total_bytes / elapsed if elapsed > 0 else 0
            log(f"─── Fin: {done} archivos · "
                f"{self._fmt_bytes(total_bytes)} · "
                f"prom {self._fmt_speed(avg)} ───", "info")

        except Exception as e:
            log(f"Error: {e}", "err")
        finally:
            q.put(("done",))

    # ── poll ────────────────────────────────

    def _poll(self):
        try:
            while True:
                msg  = self._queue.get_nowait()
                kind = msg[0]

                if kind == "log":
                    self._log(msg[1], msg[2] if len(msg) > 2 else "header")

                elif kind == "status":
                    self.status_lbl.config(text=msg[1])

                elif kind == "fetch_prog":
                    cur, total = msg[1], msg[2]
                    pct = int(cur / total * 100) if total else 0
                    self.progress["value"] = pct
                    self.pct_lbl.config(text=f"{pct}%")

                elif kind == "progress":
                    pct, cur, total = msg[1], msg[2], msg[3]
                    self.progress["value"] = pct
                    self.pct_lbl.config(text=f"{pct}%")
                    self.files_lbl.config(text=f"{cur} / {total}")

                elif kind == "speed":
                    speed, total_dl, cur_f, total_f, done = (
                        msg[1], msg[2], msg[3], msg[4], msg[5])
                    self.speed_lbl.config(text=self._fmt_speed(speed))
                    self.size_lbl.config(text=self._fmt_bytes(total_dl))
                    if speed > 0 and cur_f < total_f and self._start_time:
                        eta_s = max(0, int(
                            (total_dl / cur_f * (total_f - cur_f)) / speed))
                        self.eta_lbl.config(
                            text=str(timedelta(seconds=eta_s)))
                    else:
                        self.eta_lbl.config(text="—")

                elif kind == "add_image":
                    self.gallery_tab.add_image(msg[1])

                elif kind == "add_posts":
                    self.posts_tab.add_posts(msg[1])

                elif kind == "add_links":
                    self.links_tab.add_links(msg[1])

                elif kind == "total_posts":
                    n = msg[1]
                    self.total_lbl.config(
                        text=f"Total en grupo: {n:,} posts", fg=SUCCESS)
                    self.to_var.set(n)

                elif kind == "total_posts_err":
                    self.total_lbl.config(text=f"Error: {msg[1]}", fg=ACCENT)

                elif kind == "done":
                    self.start_btn.config(state="normal")
                    self.extract_btn.config(state="normal")
                    self.cancel_btn.config(state="disabled")
                    self.status_lbl.config(text="Listo.")
                    self.progress["value"] = 100
                    self.pct_lbl.config(text="100%")

        except queue.Empty:
            pass
        self.after(60, self._poll)


# ─────────────────────────────────────────────

if __name__ == "__main__":
    app = VKDownloaderApp()
    app.mainloop()