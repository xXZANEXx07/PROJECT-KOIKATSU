"""
Telegram Group Downloader — Versión mejorada
============================================
Mejoras sobre la versión original:
  • Panel de chats: lista todos tus chats/grupos al conectarte
  • Barra de progreso por archivo (con velocidad y tamaño)
  • Vista previa: abre el archivo descargado con el programa predeterminado
  • Botón para abrir la carpeta de destino directamente

INSTALACIÓN:
    pip install telethon

CÓMO OBTENER API_ID y API_HASH:
    1. Ve a https://my.telegram.org
    2. Inicia sesión con tu número de teléfono
    3. Haz clic en "API development tools"
    4. Crea una nueva aplicación
    5. Copia api_id y api_hash
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
import os
import asyncio
import sys
import time
import subprocess
import platform
from datetime import datetime

try:
    from telethon import TelegramClient
    from telethon.tl.types import (
        MessageMediaPhoto, MessageMediaDocument,
        User, Chat, Channel
    )
    from telethon.errors import SessionPasswordNeededError, FloodWaitError
    TELETHON_OK = True
except ImportError:
    TELETHON_OK = False


# ══════════════════════════════════════════════════════════════════════════════
#  MOTOR DE DESCARGA
# ══════════════════════════════════════════════════════════════════════════════

class DownloadEngine:
    def __init__(self, log_q: queue.Queue, progress_q: queue.Queue,
                 file_prog_q: queue.Queue, chats_q: queue.Queue):
        self.log_q      = log_q
        self.progress_q = progress_q
        self.file_prog_q = file_prog_q   # (current_bytes, total_bytes, filename)
        self.chats_q    = chats_q        # lista de (id, nombre, tipo, icono)
        self._cancel    = threading.Event()
        self.client: TelegramClient | None = None
        self.loop:  asyncio.AbstractEventLoop | None = None
        self._last_downloaded_path: str | None = None

    def log(self, msg, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_q.put((level, f"[{ts}] {msg}"))

    def cancel(self):
        self._cancel.set()

    # ── Listar chats ───────────────────────────────────────────────────────────
    def run_list_chats(self, api_id, api_hash, phone, dest):
        self._cancel.clear()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(
                self._list_chats(api_id, api_hash, phone, dest)
            )
        except Exception as e:
            self.log(f"Error: {e}", "error")
        finally:
            self.loop.close()
            self.progress_q.put(None)

    async def _list_chats(self, api_id, api_hash, phone, dest):
        session_file = os.path.join(dest, "tg_session")
        self.client  = TelegramClient(session_file, api_id, api_hash)
        self.log("Conectando a Telegram…")
        await self.client.connect()
        await self._ensure_auth(phone)
        if self._cancel.is_set():
            return

        self.log("Cargando lista de chats…", "ok")
        chats = []
        async for dialog in self.client.iter_dialogs():
            entity = dialog.entity
            if isinstance(entity, User):
                icon = "👤"
                tipo = "Usuario"
                name = dialog.name or f"Usuario {entity.id}"
            elif isinstance(entity, Channel):
                if entity.megagroup:
                    icon = "👥"
                    tipo = "Supergrupo"
                elif entity.broadcast:
                    icon = "📢"
                    tipo = "Canal"
                else:
                    icon = "👥"
                    tipo = "Grupo"
                name = dialog.name or f"Canal {entity.id}"
            elif isinstance(entity, Chat):
                icon = "👥"
                tipo = "Grupo"
                name = dialog.name or f"Grupo {entity.id}"
            else:
                icon = "💬"
                tipo = "Chat"
                name = dialog.name or str(entity.id)

            chats.append({
                "id":   str(entity.id),
                "name": name,
                "type": tipo,
                "icon": icon,
                "username": getattr(entity, "username", None) or str(entity.id),
            })

        self.chats_q.put(chats)
        self.log(f"Se encontraron {len(chats)} chats/grupos.", "ok")
        await self.client.disconnect()

    # ── Descarga ───────────────────────────────────────────────────────────────
    def run(self, api_id, api_hash, phone, group, dest,
            dl_photos, dl_videos, dl_docs, limit):
        self._cancel.clear()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(
                self._main(api_id, api_hash, phone, group, dest,
                           dl_photos, dl_videos, dl_docs, limit)
            )
        except Exception as e:
            self.log(f"Error fatal: {e}", "error")
        finally:
            self.loop.close()
            self.progress_q.put(None)

    async def _ensure_auth(self, phone):
        if not await self.client.is_user_authorized():
            self.log("Enviando código de verificación…")
            await self.client.send_code_request(phone)
            code_q: queue.Queue = queue.Queue()
            self.log_q.put(("ASK_CODE", code_q))
            code = code_q.get(timeout=120)
            try:
                await self.client.sign_in(phone, code)
            except SessionPasswordNeededError:
                self.log("Cuenta con 2FA activo.", "warn")
                pwd_q: queue.Queue = queue.Queue()
                self.log_q.put(("ASK_PASS", pwd_q))
                pw = pwd_q.get(timeout=120)
                await self.client.sign_in(password=pw)
        self.log("Sesión iniciada ✓", "ok")

    async def _main(self, api_id, api_hash, phone, group, dest,
                    dl_photos, dl_videos, dl_docs, limit):
        session_file = os.path.join(dest, "tg_session")
        self.client  = TelegramClient(session_file, api_id, api_hash)
        self.log("Conectando a Telegram…")
        await self.client.connect()
        await self._ensure_auth(phone)
        if self._cancel.is_set():
            return

        self.log(f"Buscando: {group}")
        try:
            entity = await self.client.get_entity(group)
        except Exception as e:
            self.log(f"No se encontró el grupo: {e}", "error")
            return

        group_name = getattr(entity, "title", None) or getattr(entity, "first_name", group)
        self.log(f"Grupo: {group_name}", "ok")

        safe_name = "".join(c for c in group_name if c.isalnum() or c in " _-").strip()
        out_dir   = os.path.join(dest, safe_name or "telegram_download")
        photos_dir = os.path.join(out_dir, "fotos")
        videos_dir = os.path.join(out_dir, "videos")
        docs_dir   = os.path.join(out_dir, "documentos")
        for d in [photos_dir, videos_dir, docs_dir]:
            os.makedirs(d, exist_ok=True)

        # Guardar ruta para abrir carpeta después
        self._last_downloaded_path = out_dir
        self.log_q.put(("OUT_DIR", out_dir))

        self.log("Contando archivos…")
        total_media = 0
        async for msg in self.client.iter_messages(entity, limit=limit):
            if self._cancel.is_set():
                break
            if not msg.media:
                continue
            if isinstance(msg.media, MessageMediaPhoto) and dl_photos:
                total_media += 1
            elif isinstance(msg.media, MessageMediaDocument) and (dl_videos or dl_docs):
                total_media += 1

        if self._cancel.is_set():
            self.log("Cancelado.", "warn")
            return

        self.log(f"Archivos a descargar: {total_media}", "ok")

        downloaded = skipped = errors = 0

        async for msg in self.client.iter_messages(entity, limit=limit):
            if self._cancel.is_set():
                self.log("Descarga cancelada.", "warn")
                break
            if not msg.media:
                continue

            try:
                # ── Fotos ──────────────────────────────────────────────────
                if isinstance(msg.media, MessageMediaPhoto) and dl_photos:
                    fname = f"{msg.id}.jpg"
                    fpath = os.path.join(photos_dir, fname)
                    if os.path.exists(fpath):
                        skipped += 1
                    else:
                        self.log(f"📷 Foto {msg.id}")
                        self.file_prog_q.put((0, 1, fname, fpath))

                        def _prog_photo(recv, total, _fn=fname, _fp=fpath):
                            self.file_prog_q.put((recv, total or 1, _fn, _fp))

                        await self.client.download_media(msg, fpath,
                                                         progress_callback=_prog_photo)
                        downloaded += 1
                    self.progress_q.put((downloaded, total_media, fname))

                # ── Videos / Documentos ───────────────────────────────────
                elif isinstance(msg.media, MessageMediaDocument):
                    doc  = msg.media.document
                    mime = doc.mime_type or ""
                    is_video = mime.startswith("video/")

                    fname = None
                    for attr in doc.attributes:
                        fn = getattr(attr, "file_name", None)
                        if fn:
                            fname = fn
                            break
                    if not fname:
                        ext   = mime.split("/")[-1] if "/" in mime else "bin"
                        fname = f"{msg.id}.{ext}"

                    if is_video and dl_videos:
                        fpath = os.path.join(videos_dir, fname)
                    elif not is_video and dl_docs:
                        fpath = os.path.join(docs_dir, fname)
                    else:
                        continue

                    if os.path.exists(fpath):
                        skipped += 1
                        self.progress_q.put((downloaded, total_media, fname))
                        continue

                    icon = "🎬" if is_video else "📄"
                    self.log(f"{icon} {fname}")
                    self.file_prog_q.put((0, 1, fname, fpath))

                    def _prog_doc(recv, total, _fn=fname, _fp=fpath):
                        self.file_prog_q.put((recv, total or 1, _fn, _fp))

                    await self.client.download_media(msg, fpath,
                                                     progress_callback=_prog_doc)
                    downloaded += 1
                    self.progress_q.put((downloaded, total_media, fname))

            except FloodWaitError as e:
                self.log(f"FloodWait: {e.seconds}s…", "warn")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                self.log(f"Error en mensaje {msg.id}: {e}", "error")
                errors += 1

        self.log("─" * 40)
        self.log(f"✔ Descargados: {downloaded}  |  Ya existían: {skipped}  |  Errores: {errors}", "ok")
        self.log(f"📁 Guardado en: {out_dir}", "ok")
        await self.client.disconnect()


# ══════════════════════════════════════════════════════════════════════════════
#  INTERFAZ GRÁFICA
# ══════════════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    C = {
        "bg":       "#0d0f18",
        "surface":  "#161925",
        "surface2": "#1e2235",
        "border":   "#2c3050",
        "accent":   "#5865f2",
        "accent2":  "#7289da",
        "ok":       "#57f287",
        "warn":     "#fee75c",
        "error":    "#ed4245",
        "text":     "#e3e5e8",
        "muted":    "#72767d",
        "entry_bg": "#1a1d2e",
        "hover":    "#404470",
    }

    def __init__(self):
        super().__init__()
        self.title("Telegram Group Downloader ✈")
        self.geometry("1000x780")
        self.minsize(860, 640)
        self.configure(bg=self.C["bg"])
        self.resizable(True, True)

        self._engine: DownloadEngine | None = None
        self._thread: threading.Thread | None = None
        self._log_q:      queue.Queue = queue.Queue()
        self._prog_q:     queue.Queue = queue.Queue()
        self._file_prog_q:queue.Queue = queue.Queue()
        self._chats_q:    queue.Queue = queue.Queue()
        self._running     = False
        self._out_dir: str | None = None
        self._last_fpath: str | None = None  # último archivo descargado

        self._build_ui()
        self._poll_queues()

        if not TELETHON_OK:
            self._show_install_warning()

    # ══════════════════════════════════════════════════════════════════════════
    #  CONSTRUCCIÓN UI
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        C = self.C

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=C["surface"], height=58)
        hdr.pack(fill="x")
        tk.Label(hdr, text="✈  Telegram Group Downloader",
                 font=("Helvetica", 15, "bold"),
                 fg=C["accent2"], bg=C["surface"]).pack(side="left", padx=20, pady=16)

        # ── Main layout: left sidebar (chats) + right notebook ────────────────
        main = tk.Frame(self, bg=C["bg"])
        main.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Sidebar de chats ──────────────────────────────────────────────────
        sidebar = tk.Frame(main, bg=C["surface"], width=240)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="💬 Mis chats",
                 font=("Helvetica", 10, "bold"),
                 fg=C["accent2"], bg=C["surface"]).pack(pady=(14, 4), padx=12, anchor="w")

        # Buscador de chats
        search_f = tk.Frame(sidebar, bg=C["entry_bg"])
        search_f.pack(fill="x", padx=10, pady=(0, 6))
        self._chat_search_var = tk.StringVar()
        self._chat_search_var.trace_add("write", self._filter_chats)
        tk.Entry(search_f, textvariable=self._chat_search_var,
         bg=C["entry_bg"], fg=C["text"],
         insertbackground=C["text"],
         relief="flat", bd=6,
         font=("Helvetica", 9)).pack(fill="x")

        # Lista de chats
        list_f = tk.Frame(sidebar, bg=C["surface"])
        list_f.pack(fill="both", expand=True, padx=6)

        self._chats_listbox = tk.Listbox(
            list_f,
            bg=C["surface"], fg=C["text"],
            selectbackground=C["accent"],
            selectforeground="#fff",
            activestyle="none",
            relief="flat", bd=0,
            font=("Helvetica", 9),
            highlightthickness=0,
            cursor="hand2"
        )
        self._chats_listbox.pack(side="left", fill="both", expand=True)
        scrollbar_c = ttk.Scrollbar(list_f, orient="vertical",
                                     command=self._chats_listbox.yview)
        scrollbar_c.pack(side="right", fill="y")
        self._chats_listbox.configure(yscrollcommand=scrollbar_c.set)
        self._chats_listbox.bind("<<ListboxSelect>>", self._on_chat_select)

        self._all_chats: list[dict] = []

        # Botón conectar / cargar chats
        tk.Button(sidebar, text="🔄 Conectar y listar chats",
                   bg=C["accent"], fg="#fff",
                   activebackground=C["hover"],
                   activeforeground="#fff",
                   relief="flat", bd=0,
                   padx=8, pady=7,
                   font=("Helvetica", 9, "bold"),
                   cursor="hand2",
                   command=self._connect_and_list).pack(fill="x", padx=10, pady=8)

        # ── Área principal (notebook) ─────────────────────────────────────────
        right = tk.Frame(main, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook",        background=C["bg"],       borderwidth=0)
        style.configure("TNotebook.Tab",    background=C["surface2"], foreground=C["muted"],
                         padding=[14, 6],   font=("Helvetica", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", C["accent"])],
                  foreground=[("selected", "#ffffff")])
        style.configure("TFrame",           background=C["bg"])
        style.configure("Horizontal.TProgressbar",
                         troughcolor=C["border"], background=C["accent"],
                         thickness=8, borderwidth=0)
        style.configure("File.Horizontal.TProgressbar",
                         troughcolor=C["border"], background=C["ok"],
                         thickness=5, borderwidth=0)

        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True, padx=10, pady=(8, 0))

        tab_config = ttk.Frame(nb)
        tab_log    = ttk.Frame(nb)
        nb.add(tab_config, text="  Configuración  ")
        nb.add(tab_log,    text="  Registro  ")

        self._nb = nb
        self._build_config_tab(tab_config)
        self._build_log_tab(tab_log)

        # ── Barra inferior: progreso global + por archivo ─────────────────────
        bottom = tk.Frame(right, bg=C["surface"], pady=8)
        bottom.pack(fill="x", padx=10, pady=(4, 6))

        # Progreso global
        global_f = tk.Frame(bottom, bg=C["surface"])
        global_f.pack(fill="x", padx=12, pady=(0, 4))

        self._global_label = tk.Label(global_f, text="En espera…",
                                       fg=C["muted"], bg=C["surface"],
                                       font=("Helvetica", 9))
        self._global_label.pack(side="left")

        self._open_folder_btn = tk.Button(global_f, text="📂 Abrir carpeta",
                                           bg=C["border"], fg=C["muted"],
                                           activebackground=C["surface2"],
                                           activeforeground=C["text"],
                                           relief="flat", bd=0,
                                           padx=8, pady=2,
                                           font=("Helvetica", 8),
                                           cursor="hand2",
                                           state="disabled",
                                           command=self._open_folder)
        self._open_folder_btn.pack(side="right")

        self._prog_bar = ttk.Progressbar(bottom, mode="determinate",
                                          style="Horizontal.TProgressbar",
                                          length=400)
        self._prog_bar.pack(fill="x", padx=12, pady=(0, 6))

        # Progreso por archivo
        file_f = tk.Frame(bottom, bg=C["surface"])
        file_f.pack(fill="x", padx=12)

        self._file_label = tk.Label(file_f, text="",
                                     fg=C["accent2"], bg=C["surface"],
                                     font=("Courier", 8))
        self._file_label.pack(side="left")

        self._preview_btn = tk.Button(file_f, text="👁 Ver archivo",
                                       bg=C["border"], fg=C["muted"],
                                       activebackground=C["surface2"],
                                       activeforeground=C["text"],
                                       relief="flat", bd=0,
                                       padx=8, pady=2,
                                       font=("Helvetica", 8),
                                       cursor="hand2",
                                       state="disabled",
                                       command=self._preview_file)
        self._preview_btn.pack(side="right")

        self._file_prog_bar = ttk.Progressbar(bottom, mode="determinate",
                                               style="File.Horizontal.TProgressbar",
                                               length=400)
        self._file_prog_bar.pack(fill="x", padx=12, pady=(2, 0))

    # ── Tab Configuración ─────────────────────────────────────────────────────
    def _build_config_tab(self, parent):
        C = self.C
        scroll = tk.Frame(parent, bg=C["bg"])
        scroll.pack(fill="both", expand=True, padx=20, pady=14)

        def section(title):
            f = tk.LabelFrame(scroll, text=f"  {title}  ",
                               bg=C["surface2"], fg=C["accent2"],
                               bd=1, relief="flat",
                               font=("Helvetica", 9, "bold"),
                               labelanchor="nw")
            f.pack(fill="x", pady=(0, 10))
            return f

        def row(parent, label, wfactory, hint=None):
            r = tk.Frame(parent, bg=C["surface2"])
            r.pack(fill="x", padx=14, pady=5)
            tk.Label(r, text=label, fg=C["text"], bg=C["surface2"],
                     width=18, anchor="w",
                     font=("Helvetica", 10)).pack(side="left")
            w = wfactory(r)
            w.pack(side="left", fill="x", expand=True)
            if hint:
                tk.Label(r, text=hint, fg=C["muted"], bg=C["surface2"],
                         font=("Helvetica", 8)).pack(side="left", padx=(6, 0))
            return w

        def entry(parent, show=None):
            return tk.Entry(parent, bg=C["entry_bg"], fg=C["text"],
                             insertbackground=C["text"],
                             relief="flat", bd=6,
                             font=("Helvetica", 10),
                             show=show or "")

        # Credenciales
        sec1 = section("Credenciales API  (my.telegram.org → API development tools)")
        self._api_id   = row(sec1, "API ID",   entry,              "Número entero")
        self._api_hash = row(sec1, "API Hash", lambda p: entry(p, show="•"), "32 chars hex")
        self._phone    = row(sec1, "Teléfono", entry,              "+521234567890")
        tk.Label(sec1,
                 text="→ https://my.telegram.org  — crea una app y copia api_id y api_hash",
                 fg=C["muted"], bg=C["surface2"],
                 font=("Helvetica", 8)).pack(anchor="w", padx=14, pady=(0, 8))

        # Grupo / canal
        sec2 = section("Grupo / Canal")
        self._group = row(sec2, "Destino",
                           entry, "username, t.me/... o ID numérico — o selecciona del panel izquierdo")

        # Qué descargar
        sec3 = section("Qué descargar")
        opts = tk.Frame(sec3, bg=C["surface2"])
        opts.pack(fill="x", padx=14, pady=8)
        self._dl_photos = tk.BooleanVar(value=True)
        self._dl_videos = tk.BooleanVar(value=True)
        self._dl_docs   = tk.BooleanVar(value=True)
        for var, label, emoji in [
            (self._dl_photos, "Fotos / Imágenes",     "🖼"),
            (self._dl_videos, "Videos",                "🎬"),
            (self._dl_docs,   "Documentos",            "📄"),
        ]:
            tk.Checkbutton(opts, text=f"  {emoji}  {label}",
                            variable=var,
                            bg=C["surface2"], fg=C["text"],
                            selectcolor=C["entry_bg"],
                            activebackground=C["surface2"],
                            activeforeground=C["text"],
                            font=("Helvetica", 10),
                            bd=0).pack(side="left", padx=(0, 24))

        lim_f = tk.Frame(sec3, bg=C["surface2"])
        lim_f.pack(fill="x", padx=14, pady=(0, 10))
        tk.Label(lim_f, text="Límite de mensajes:",
                 fg=C["text"], bg=C["surface2"],
                 font=("Helvetica", 10)).pack(side="left")
        self._limit = tk.Entry(lim_f, bg=C["entry_bg"], fg=C["text"],
                                insertbackground=C["text"],
                                relief="flat", bd=6,
                                font=("Helvetica", 10), width=10)
        self._limit.insert(0, "0")
        self._limit.pack(side="left", padx=8)
        tk.Label(lim_f, text="(0 = sin límite)",
                 fg=C["muted"], bg=C["surface2"],
                 font=("Helvetica", 8)).pack(side="left")

        # Carpeta destino
        sec4 = section("Carpeta de destino")
        dest_f = tk.Frame(sec4, bg=C["surface2"])
        dest_f.pack(fill="x", padx=14, pady=8)
        self._dest = tk.Entry(dest_f, bg=C["entry_bg"], fg=C["text"],
                               insertbackground=C["text"],
                               relief="flat", bd=6,
                               font=("Helvetica", 10))
        self._dest.pack(side="left", fill="x", expand=True)
        default_dl = os.path.expanduser("~/Downloads")
        if not os.path.isdir(default_dl):
            default_dl = os.path.expanduser("~/Descargas")
        self._dest.insert(0, default_dl)
        tk.Button(dest_f, text="Examinar…",
                   bg=C["border"], fg=C["text"],
                   activebackground=C["accent"],
                   activeforeground="#fff",
                   relief="flat", bd=0, padx=10,
                   font=("Helvetica", 9),
                   command=self._browse_dest).pack(side="left", padx=(8, 0))

        # Botones
        btn_f = tk.Frame(scroll, bg=C["bg"])
        btn_f.pack(fill="x", pady=10)
        self._btn_start = tk.Button(btn_f, text="▶  Iniciar descarga",
                                     bg=C["accent"], fg="#ffffff",
                                     activebackground=C["accent2"],
                                     activeforeground="#ffffff",
                                     relief="flat", bd=0,
                                     padx=24, pady=10,
                                     font=("Helvetica", 11, "bold"),
                                     cursor="hand2",
                                     command=self._start)
        self._btn_start.pack(side="left")

        self._btn_cancel = tk.Button(btn_f, text="⏹  Cancelar",
                                      bg=C["error"], fg="#ffffff",
                                      activebackground="#c0393b",
                                      activeforeground="#ffffff",
                                      relief="flat", bd=0,
                                      padx=20, pady=10,
                                      font=("Helvetica", 11),
                                      cursor="hand2",
                                      state="disabled",
                                      command=self._cancel)
        self._btn_cancel.pack(side="left", padx=12)

    # ── Tab Registro ──────────────────────────────────────────────────────────
    def _build_log_tab(self, parent):
        C = self.C
        f = tk.Frame(parent, bg=C["bg"])
        f.pack(fill="both", expand=True, padx=12, pady=10)
        self._log = scrolledtext.ScrolledText(
            f, bg=C["surface2"], fg=C["text"],
            insertbackground=C["text"],
            font=("Courier", 9),
            relief="flat", bd=0,
            wrap="word",
            state="disabled"
        )
        self._log.pack(fill="both", expand=True)
        for tag, color in [("ok", C["ok"]), ("warn", C["warn"]),
                            ("error", C["error"]), ("info", C["text"])]:
            self._log.tag_configure(tag, foreground=color)

        tk.Button(f, text="Limpiar registro",
                   bg=C["border"], fg=C["muted"],
                   activebackground=C["surface2"],
                   relief="flat", bd=0, padx=10, pady=4,
                   font=("Helvetica", 8),
                   command=self._clear_log).pack(anchor="e", pady=(6, 0))

    # ══════════════════════════════════════════════════════════════════════════
    #  PANEL DE CHATS
    # ══════════════════════════════════════════════════════════════════════════

    def _connect_and_list(self):
        if not TELETHON_OK:
            self._show_install_warning()
            return
        api_id_s = self._api_id.get().strip()
        api_hash = self._api_hash.get().strip()
        phone    = self._phone.get().strip()
        dest     = self._dest.get().strip()

        if not all([api_id_s, api_hash, phone]):
            messagebox.showerror("Faltan datos", "Ingresa API ID, API Hash y teléfono primero.")
            return
        try:
            api_id = int(api_id_s)
        except ValueError:
            messagebox.showerror("API ID inválido", "El API ID debe ser un número.")
            return
        if not os.path.isdir(dest):
            messagebox.showerror("Carpeta inválida", "La carpeta de destino no existe.")
            return

        self._log_q   = queue.Queue()
        self._prog_q  = queue.Queue()
        self._file_prog_q = queue.Queue()
        self._chats_q = queue.Queue()
        self._engine  = DownloadEngine(self._log_q, self._prog_q,
                                        self._file_prog_q, self._chats_q)
        t = threading.Thread(
            target=self._engine.run_list_chats,
            args=(api_id, api_hash, phone, dest),
            daemon=True
        )
        t.start()

    def _filter_chats(self, *_):
        q = self._chat_search_var.get().lower()
        self._populate_chat_list(
            [c for c in self._all_chats if q in c["name"].lower()] if q else self._all_chats
        )

    def _populate_chat_list(self, chats):
        self._chats_listbox.delete(0, "end")
        for c in chats:
            self._chats_listbox.insert("end", f"  {c['icon']}  {c['name']}")

    def _on_chat_select(self, event):
        sel = self._chats_listbox.curselection()
        if not sel:
            return
        q = self._chat_search_var.get().lower()
        visible = [c for c in self._all_chats if q in c["name"].lower()] if q else self._all_chats
        idx = sel[0]
        if idx < len(visible):
            chat = visible[idx]
            target = chat["username"] if chat["username"] else chat["id"]
            self._group.delete(0, "end")
            self._group.insert(0, target)

    # ══════════════════════════════════════════════════════════════════════════
    #  INICIO / CANCELAR
    # ══════════════════════════════════════════════════════════════════════════

    def _start(self):
        if not TELETHON_OK:
            self._show_install_warning()
            return

        api_id_s = self._api_id.get().strip()
        api_hash = self._api_hash.get().strip()
        phone    = self._phone.get().strip()
        group    = self._group.get().strip()
        dest     = self._dest.get().strip()
        limit_s  = self._limit.get().strip()

        if not all([api_id_s, api_hash, phone, group, dest]):
            messagebox.showerror("Campos incompletos",
                                  "Rellena todos los campos obligatorios.")
            return
        try:
            api_id = int(api_id_s)
        except ValueError:
            messagebox.showerror("API ID inválido", "Debe ser número entero.")
            return
        try:
            limit = int(limit_s)
            limit = None if limit <= 0 else limit
        except ValueError:
            limit = None
        if not os.path.isdir(dest):
            messagebox.showerror("Carpeta inválida", "La carpeta de destino no existe.")
            return
        if not any([self._dl_photos.get(), self._dl_videos.get(), self._dl_docs.get()]):
            messagebox.showerror("Sin contenido", "Selecciona al menos un tipo de archivo.")
            return

        self._btn_start.configure(state="disabled")
        self._btn_cancel.configure(state="normal")
        self._running = True
        self._prog_bar["value"] = 0
        self._file_prog_bar["value"] = 0
        self._global_label.configure(text="Iniciando…")
        self._file_label.configure(text="")

        self._log_q       = queue.Queue()
        self._prog_q      = queue.Queue()
        self._file_prog_q = queue.Queue()
        self._chats_q     = queue.Queue()
        self._engine = DownloadEngine(self._log_q, self._prog_q,
                                       self._file_prog_q, self._chats_q)

        self._thread = threading.Thread(
            target=self._engine.run,
            args=(api_id, api_hash, phone, group, dest,
                  self._dl_photos.get(), self._dl_videos.get(), self._dl_docs.get(),
                  limit),
            daemon=True
        )
        self._thread.start()
        # Cambiar a pestaña de registro automáticamente
        self._nb.select(1)

    def _cancel(self):
        if self._engine:
            self._engine.cancel()
        self._btn_cancel.configure(state="disabled")

    # ══════════════════════════════════════════════════════════════════════════
    #  POLLING
    # ══════════════════════════════════════════════════════════════════════════

    def _poll_queues(self):
        # ── Cola de log ───────────────────────────────────────────────────────
        try:
            while True:
                item = self._log_q.get_nowait()
                if not isinstance(item, tuple):
                    continue
                kind = item[0]
                if kind == "ASK_CODE":
                    self._ask_code(item[1])
                elif kind == "ASK_PASS":
                    self._ask_password(item[1])
                elif kind == "OUT_DIR":
                    self._out_dir = item[1]
                    self._open_folder_btn.configure(state="normal",
                                                     fg=self.C["text"])
                elif len(item) == 2:
                    self._log_write(item[0], item[1])
        except queue.Empty:
            pass

        # ── Cola de progreso global ───────────────────────────────────────────
        try:
            while True:
                p = self._prog_q.get_nowait()
                if p is None:
                    self._on_done()
                else:
                    current, total, label = p
                    if total:
                        self._prog_bar["value"] = current / total * 100
                        self._global_label.configure(
                            text=f"Archivos: {current}/{total}  —  {label[:45]}")
        except queue.Empty:
            pass

        # ── Cola de progreso por archivo ──────────────────────────────────────
        try:
            while True:
                fp = self._file_prog_q.get_nowait()
                if fp:
                    recv, total, fname, fpath = fp
                    pct = (recv / total * 100) if total else 0
                    self._file_prog_bar["value"] = pct
                    recv_kb  = recv  // 1024
                    total_kb = total // 1024
                    self._file_label.configure(
                        text=f"  {fname[:42]}  {recv_kb:,} / {total_kb:,} KB  ({pct:.0f}%)")
                    if pct >= 100 and fpath and os.path.exists(fpath):
                        self._last_fpath = fpath
                        self._preview_btn.configure(state="normal",
                                                     fg=self.C["text"])
        except queue.Empty:
            pass

        # ── Cola de chats ─────────────────────────────────────────────────────
        try:
            while True:
                chats = self._chats_q.get_nowait()
                self._all_chats = chats
                self._populate_chat_list(chats)
        except queue.Empty:
            pass

        self.after(120, self._poll_queues)

    def _on_done(self):
        self._running = False
        self._btn_start.configure(state="normal")
        self._btn_cancel.configure(state="disabled")
        self._prog_bar["value"] = 100
        self._file_prog_bar["value"] = 100
        self._global_label.configure(text="✔ Descarga completada")

    # ══════════════════════════════════════════════════════════════════════════
    #  ABRIR ARCHIVO / CARPETA
    # ══════════════════════════════════════════════════════════════════════════

    def _open_folder(self):
        if self._out_dir and os.path.isdir(self._out_dir):
            _open_path(self._out_dir)

    def _preview_file(self):
        if self._last_fpath and os.path.exists(self._last_fpath):
            _open_path(self._last_fpath)

    # ══════════════════════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _browse_dest(self):
        d = filedialog.askdirectory(title="Carpeta de destino")
        if d:
            self._dest.delete(0, "end")
            self._dest.insert(0, d)

    def _log_write(self, level, msg):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n", level)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _show_install_warning(self):
        messagebox.showwarning(
            "Dependencia faltante",
            "Telethon no está instalado.\n\nEjecuta en una terminal:\n\n"
            "    pip install telethon\n\nLuego reinicia la aplicación."
        )

    # ── Diálogos de autenticación ─────────────────────────────────────────────
    def _ask_code(self, result_q: queue.Queue):
        win = tk.Toplevel(self)
        win.title("Código de verificación")
        win.geometry("340x170")
        win.configure(bg=self.C["bg"])
        win.grab_set()
        tk.Label(win, text="Ingresa el código recibido en Telegram:",
                 fg=self.C["text"], bg=self.C["bg"],
                 wraplength=300, font=("Helvetica", 10)).pack(pady=(20, 8))
        e = tk.Entry(win, bg=self.C["entry_bg"], fg=self.C["text"],
                      insertbackground=self.C["text"],
                      font=("Helvetica", 15, "bold"),
                      justify="center", relief="flat", bd=8)
        e.pack(padx=30, fill="x")
        e.focus()

        def submit(_=None):
            code = e.get().strip()
            if code:
                result_q.put(code)
                win.destroy()

        e.bind("<Return>", submit)
        tk.Button(win, text="Aceptar",
                   bg=self.C["accent"], fg="#fff",
                   relief="flat", bd=0, padx=20, pady=6,
                   font=("Helvetica", 10, "bold"),
                   command=submit).pack(pady=12)

    def _ask_password(self, result_q: queue.Queue):
        win = tk.Toplevel(self)
        win.title("Contraseña 2FA")
        win.geometry("340x170")
        win.configure(bg=self.C["bg"])
        win.grab_set()
        tk.Label(win, text="Tu cuenta tiene 2FA activo.\nIngresa tu contraseña:",
                 fg=self.C["text"], bg=self.C["bg"],
                 wraplength=300, font=("Helvetica", 10)).pack(pady=(20, 8))
        e = tk.Entry(win, bg=self.C["entry_bg"], fg=self.C["text"],
                      insertbackground=self.C["text"],
                      font=("Helvetica", 12), show="•",
                      relief="flat", bd=8)
        e.pack(padx=30, fill="x")
        e.focus()

        def submit(_=None):
            pw = e.get().strip()
            if pw:
                result_q.put(pw)
                win.destroy()

        e.bind("<Return>", submit)
        tk.Button(win, text="Aceptar",
                   bg=self.C["accent"], fg="#fff",
                   relief="flat", bd=0, padx=20, pady=6,
                   font=("Helvetica", 10, "bold"),
                   command=submit).pack(pady=12)


# ══════════════════════════════════════════════════════════════════════════════
#  UTILIDAD: abrir archivo/carpeta con el explorador del sistema
# ══════════════════════════════════════════════════════════════════════════════

def _open_path(path: str):
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(path)
        elif system == "Darwin":   # macOS
            subprocess.Popen(["open", path])
        else:                       # Linux / otros
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("Error al abrir", str(e))


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = App()
    app.mainloop()