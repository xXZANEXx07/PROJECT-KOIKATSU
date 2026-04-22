import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
import shutil
from datetime import datetime
import threading
import csv

# ──────────────────────────────────────────────
#  FIRMAS (magic numbers)
# ──────────────────────────────────────────────
FIRMAS_IMAGENES = {
    'PNG':  [b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A'],
    'JPEG': [b'\xFF\xD8\xFF\xDB', b'\xFF\xD8\xFF\xE0',
             b'\xFF\xD8\xFF\xE1', b'\xFF\xD8\xFF\xEE',
             b'\xFF\xD8\xFF\xE2', b'\xFF\xD8\xFF\xE3'],
    'GIF':  [b'\x47\x49\x46\x38\x37\x61', b'\x47\x49\x46\x38\x39\x61'],
    'BMP':  [b'\x42\x4D'],
    'ICO':  [b'\x00\x00\x01\x00'],
    'PSD':  [b'\x38\x42\x50\x53'],
}

FIRMAS_RAW = {
    'RAF': [b'\x46\x55\x4A\x49\x46\x49\x4C\x4D'],  # Fujifilm
    'ORF': [b'\x49\x49\x52\x4F', b'\x49\x49\x52\x53'],  # Olympus
    'RW2': [b'\x49\x49\x55\x00'],  # Panasonic
}

FIRMAS_VIDEOS = {
    'MKV':  [b'\x1A\x45\xDF\xA3'],
    'WMV':  [b'\x30\x26\xB2\x75\x8E\x66\xCF\x11'],
    'FLV':  [b'\x46\x4C\x56'],
    'MPEG': [b'\x00\x00\x01\xBA', b'\x00\x00\x01\xB3'],
}

EXTENSIONES_MULTIMEDIA = {
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif',
    '.webp', '.ico', '.psd', '.heic', '.heif', '.avif',
    '.cr2', '.cr3', '.nef', '.arw', '.dng', '.orf', '.raf',
    '.rw2', '.pef', '.srw',
    '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv',
    '.mpeg', '.mpg', '.webm',
}

TIPO_LABEL = {
    'PNG': 'Imagen', 'JPEG': 'Imagen', 'GIF': 'Imagen', 'BMP': 'Imagen',
    'TIFF': 'Imagen', 'WebP': 'Imagen', 'ICO': 'Imagen', 'PSD': 'Imagen',
    'HEIC': 'Imagen', 'AVIF': 'Imagen',
    'CR2': 'RAW', 'CR3': 'RAW', 'NEF': 'RAW', 'ARW': 'RAW',
    'DNG': 'RAW', 'ORF': 'RAW', 'RAF': 'RAW', 'RW2': 'RAW',
    'PEF': 'RAW', 'SRW': 'RAW',
    'MP4': 'Video', 'MOV': 'Video', 'AVI': 'Video', 'MKV': 'Video',
    'WMV': 'Video', 'FLV': 'Video', 'MPEG': 'Video', 'WEBM': 'Video',
}


# ──────────────────────────────────────────────
#  LÓGICA DE DETECCIÓN
# ──────────────────────────────────────────────
def detectar_formato(ruta_archivo):
    """Devuelve (formato_real:str, extension_actual:str, error:str|None)"""
    try:
        with open(ruta_archivo, 'rb') as f:
            cabecera = f.read(32)

            # ── Contenedores ISOM / QuickTime / HEIC / CR3 ──────────────
            if len(cabecera) >= 12 and cabecera[4:8] == b'ftyp':
                tipo = cabecera[8:12]
                if tipo in (b'crx ', b'cr3 '):
                    fmt = 'CR3'
                elif tipo in (b'heic', b'heix', b'hevc', b'hevx',
                              b'mif1', b'msf1'):
                    fmt = 'HEIC'
                elif tipo == b'avif':
                    fmt = 'AVIF'
                elif tipo in (b'qt  ', b'qtif'):
                    fmt = 'MOV'
                else:
                    fmt = 'MP4'
                return fmt, _ext(ruta_archivo), None

            # ── RIFF (AVI / WebP) ────────────────────────────────────────
            if cabecera.startswith(b'\x52\x49\x46\x46'):
                if b'WEBP' in cabecera:
                    return 'WebP', _ext(ruta_archivo), None
                if b'AVI ' in cabecera[:16]:
                    return 'AVI', _ext(ruta_archivo), None

            # ── MKV / WEBM ───────────────────────────────────────────────
            if cabecera.startswith(b'\x1A\x45\xDF\xA3'):
                f.seek(0)
                muestra = f.read(4096)
                fmt = 'WEBM' if b'webm' in muestra.lower() else 'MKV'
                return fmt, _ext(ruta_archivo), None

            # ── WMV ──────────────────────────────────────────────────────
            if cabecera.startswith(b'\x30\x26\xB2\x75\x8E\x66\xCF\x11'):
                return 'WMV', _ext(ruta_archivo), None

            # ── FLV ──────────────────────────────────────────────────────
            if cabecera.startswith(b'\x46\x4C\x56'):
                return 'FLV', _ext(ruta_archivo), None

            # ── MPEG ─────────────────────────────────────────────────────
            if cabecera.startswith(b'\x00\x00\x01\xBA') or \
               cabecera.startswith(b'\x00\x00\x01\xB3'):
                return 'MPEG', _ext(ruta_archivo), None

            # ── RAF (Fujifilm) ───────────────────────────────────────────
            if cabecera.startswith(b'\x46\x55\x4A\x49\x46\x49\x4C\x4D'):
                return 'RAF', _ext(ruta_archivo), None

            # ── ORF (Olympus) ────────────────────────────────────────────
            if cabecera.startswith(b'\x49\x49\x52\x4F') or \
               cabecera.startswith(b'\x49\x49\x52\x53'):
                return 'ORF', _ext(ruta_archivo), None

            # ── RW2 (Panasonic) ──────────────────────────────────────────
            if cabecera.startswith(b'\x49\x49\x55\x00'):
                return 'RW2', _ext(ruta_archivo), None

            # ── Familia TIFF (CR2, NEF, ARW, DNG, PEF, SRW, TIFF) ───────
            if cabecera.startswith(b'\x49\x49\x2A\x00') or \
               cabecera.startswith(b'\x4D\x4D\x00\x2A'):
                f.seek(0)
                datos = f.read(1024)
                DATA = datos.upper()
                if b'CANON' in DATA or b'CR\x02' in datos:
                    return 'CR2', _ext(ruta_archivo), None
                if b'NIKON' in DATA:
                    return 'NEF', _ext(ruta_archivo), None
                if b'SONY' in DATA or b'DSLR-' in datos:
                    return 'ARW', _ext(ruta_archivo), None
                if b'PENTAX' in DATA or b'AOC\x00' in datos:
                    return 'PEF', _ext(ruta_archivo), None
                if b'SAMSUNG' in DATA:
                    return 'SRW', _ext(ruta_archivo), None
                if b'DNG' in datos:
                    return 'DNG', _ext(ruta_archivo), None
                return 'TIFF', _ext(ruta_archivo), None

            # ── Imágenes simples ─────────────────────────────────────────
            for fmt, firmas in FIRMAS_IMAGENES.items():
                for firma in firmas:
                    if cabecera.startswith(firma):
                        return fmt, _ext(ruta_archivo), None

            return 'DESCONOCIDO', _ext(ruta_archivo), None

    except Exception as e:
        return 'ERROR', _ext(ruta_archivo), str(e)


def _ext(ruta):
    return Path(ruta).suffix.upper().lstrip('.')


def formatos_coinciden(formato_real, extension_actual):
    f = formato_real.upper()
    e = extension_actual.upper()
    # Normalizar aliases
    if f == 'JPEG': f = 'JPG'
    if e == 'JPEG': e = 'JPG'
    if f in ('HEIC', 'HEIF'): f = 'HEIC'
    if e in ('HEIC', 'HEIF'): e = 'HEIC'
    if f in ('TIFF', 'TIF'): f = 'TIFF'
    if e in ('TIFF', 'TIF'): e = 'TIFF'
    if f == 'MPG': f = 'MPEG'
    if e == 'MPG': e = 'MPEG'
    return f == e


# ──────────────────────────────────────────────
#  GUI
# ──────────────────────────────────────────────
class App:
    COLOR_OK  = '#1a7a1a'
    COLOR_ERR = '#c0392b'
    COLOR_WARN = '#d68910'
    COLOR_BG  = '#1e1e2e'
    COLOR_FG  = '#cdd6f4'
    COLOR_ACCENT = '#89b4fa'
    COLOR_SURFACE = '#313244'
    COLOR_GREEN = '#a6e3a1'
    COLOR_RED   = '#f38ba8'
    COLOR_YELLOW = '#f9e2af'

    def __init__(self, root):
        self.root = root
        self.root.title("🔍 Detector de Formato Real — v2.0")
        self.root.geometry("1100x780")
        self.root.minsize(900, 650)
        self.root.configure(bg=self.COLOR_BG)

        self.ruta_actual = tk.StringVar()
        self.archivos_analizados = []   # [(ruta, fmt_real, ext_actual, coincide)]
        self.modo_renombrado = tk.StringVar(value="backup")
        self.incluir_subcarpetas = tk.BooleanVar(value=True)
        self.filtro_tipo = tk.StringVar(value="Todos")
        self._cancelar = threading.Event()

        self._aplicar_estilos()
        self._build_ui()
        self._msg_bienvenida()

    # ── Estilos ──────────────────────────────────────────────────────────
    def _aplicar_estilos(self):
        s = ttk.Style()
        s.theme_use('clam')
        bg, fg, surf, acc = self.COLOR_BG, self.COLOR_FG, self.COLOR_SURFACE, self.COLOR_ACCENT

        # Frames / labels
        for w in ('TFrame', 'TLabelframe', 'TLabelframe.Label'):
            s.configure(w, background=bg, foreground=fg)
        s.configure('TLabel', background=bg, foreground=fg)
        s.configure('TRadiobutton', background=bg, foreground=fg,
                    selectcolor=surf)
        s.configure('TCheckbutton', background=bg, foreground=fg,
                    selectcolor=surf)

        # Botones
        s.configure('TButton', background=surf, foreground=fg, padding=6,
                    relief='flat', borderwidth=0)
        s.map('TButton',
              background=[('active', acc), ('pressed', acc)],
              foreground=[('active', bg)])

        s.configure('Accent.TButton', background=acc, foreground=bg,
                    padding=6, font=('Arial', 9, 'bold'))
        s.map('Accent.TButton',
              background=[('active', '#74c7ec'), ('pressed', '#74c7ec')])

        # Combobox
        s.configure('TCombobox', fieldbackground=surf, background=surf,
                    foreground=fg, selectbackground=acc)

        # Progressbar
        s.configure('TProgressbar', troughcolor=surf, background=acc,
                    thickness=14)

        # Treeview
        s.configure('Treeview', background=surf, foreground=fg,
                    fieldbackground=surf, rowheight=24)
        s.configure('Treeview.Heading', background=bg, foreground=acc,
                    font=('Arial', 9, 'bold'))
        s.map('Treeview', background=[('selected', acc)],
              foreground=[('selected', bg)])

    # ── Layout ───────────────────────────────────────────────────────────
    def _build_ui(self):
        bg = self.COLOR_BG
        pad = dict(padx=10, pady=6)

        # ── Cabecera ─────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg='#181825', pady=12)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="🔍  Detector de Formato Real",
                 bg='#181825', fg=self.COLOR_ACCENT,
                 font=('Arial', 18, 'bold')).pack()
        tk.Label(hdr,
                 text="Detecta el formato real de imágenes, RAW y videos por su firma interna",
                 bg='#181825', fg='#a6adc8', font=('Arial', 9)).pack()

        # ── Cuerpo ───────────────────────────────────────────────────────
        body = ttk.Frame(self.root, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        # ── Fila superior: selección + opciones ─────────────────────────
        top = ttk.Frame(body)
        top.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        top.columnconfigure(1, weight=1)

        # Selección de ruta
        sel = ttk.LabelFrame(top, text="  Origen  ", padding=8)
        sel.grid(row=0, column=0, sticky='nsew', padx=(0, 8))

        ttk.Button(sel, text="📄 Archivo",
                   command=self._sel_archivo).grid(row=0, column=0, padx=4)
        ttk.Button(sel, text="📁 Carpeta",
                   command=self._sel_carpeta).grid(row=0, column=1, padx=4)
        ttk.Button(sel, text="🔍 Analizar",
                   command=self._iniciar_analisis,
                   style='Accent.TButton').grid(row=0, column=2, padx=4)
        ttk.Button(sel, text="⏹ Cancelar",
                   command=self._cancelar_analisis).grid(row=0, column=3, padx=4)

        ruta_frame = ttk.Frame(sel)
        ruta_frame.grid(row=1, column=0, columnspan=4, sticky='ew', pady=(6, 0))
        ruta_frame.columnconfigure(1, weight=1)
        ttk.Label(ruta_frame, text="Ruta:").grid(row=0, column=0, padx=(0, 4))
        ttk.Entry(ruta_frame, textvariable=self.ruta_actual,
                  state='readonly').grid(row=0, column=1, sticky='ew')

        # Opciones de análisis
        opts = ttk.LabelFrame(top, text="  Opciones de Análisis  ", padding=8)
        opts.grid(row=0, column=1, sticky='nsew')

        ttk.Checkbutton(opts, text="Incluir subcarpetas",
                        variable=self.incluir_subcarpetas).grid(
            row=0, column=0, sticky='w', padx=6)

        ttk.Label(opts, text="Mostrar:").grid(row=0, column=1, padx=(16, 4))
        cb = ttk.Combobox(opts, textvariable=self.filtro_tipo, width=12,
                          values=['Todos', 'Sólo errores', 'Imágenes', 'RAW', 'Video'],
                          state='readonly')
        cb.grid(row=0, column=2, padx=4)

        ttk.Label(opts, text="Modo de corrección:").grid(
            row=0, column=3, padx=(16, 4))
        modo_cb = ttk.Combobox(opts, textvariable=self.modo_renombrado, width=22,
                               values=['backup', 'agregar', 'nueva_carpeta', 'directo'],
                               state='readonly')
        modo_cb.grid(row=0, column=4, padx=4)
        modos_display = {
            'backup': '🛡️ Backup + Renombrar',
            'agregar': '📝 Agregar _corrected',
            'nueva_carpeta': '📁 Nueva carpeta',
            'directo': '⚡ Renombrar directo',
        }
        modo_cb['values'] = list(modos_display.keys())

        # ── Barra de progreso ────────────────────────────────────────────
        prog_row = ttk.Frame(body)
        prog_row.grid(row=1, column=0, sticky='ew', pady=(0, 6))
        prog_row.columnconfigure(0, weight=1)
        self.progreso = ttk.Progressbar(prog_row, mode='determinate',
                                        style='TProgressbar')
        self.progreso.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        self.lbl_prog = ttk.Label(prog_row, text="", width=40)
        self.lbl_prog.grid(row=0, column=1)

        # ── Treeview de resultados ────────────────────────────────────────
        tree_frame = ttk.LabelFrame(body, text="  Resultados  ", padding=6)
        tree_frame.grid(row=2, column=0, sticky='nsew')
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        cols = ('estado', 'archivo', 'carpeta', 'ext_actual', 'fmt_real', 'tipo')
        self.tree = ttk.Treeview(tree_frame, columns=cols,
                                 show='headings', selectmode='extended')

        hdr_cfg = [
            ('estado',    '⚡',           50,  tk.CENTER),
            ('archivo',   'Archivo',      260, tk.W),
            ('carpeta',   'Carpeta',      280, tk.W),
            ('ext_actual','Ext. actual',   90, tk.CENTER),
            ('fmt_real',  'Fmt real',      90, tk.CENTER),
            ('tipo',      'Tipo',          70, tk.CENTER),
        ]
        for col, lbl, w, anc in hdr_cfg:
            self.tree.heading(col, text=lbl,
                              command=lambda c=col: self._sort_tree(c, False))
            self.tree.column(col, width=w, anchor=anc, minwidth=40)

        self.tree.tag_configure('ok',   foreground=self.COLOR_GREEN)
        self.tree.tag_configure('err',  foreground=self.COLOR_RED)
        self.tree.tag_configure('unk',  foreground=self.COLOR_YELLOW)

        sb_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                              command=self.tree.yview)
        sb_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL,
                              command=self.tree.xview)
        self.tree.configure(yscrollcommand=sb_y.set,
                            xscrollcommand=sb_x.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        sb_y.grid(row=0, column=1, sticky='ns')
        sb_x.grid(row=1, column=0, sticky='ew')

        # ── Barra inferior ────────────────────────────────────────────────
        bot = ttk.Frame(body)
        bot.grid(row=3, column=0, sticky='ew', pady=(8, 0))

        self.lbl_stats = ttk.Label(bot, text="", font=('Arial', 9))
        self.lbl_stats.pack(side=tk.LEFT)

        ttk.Button(bot, text="📋 Exportar CSV",
                   command=self._exportar_csv).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bot, text="🗑️ Limpiar",
                   command=self._limpiar).pack(side=tk.RIGHT, padx=4)
        self.btn_apply = ttk.Button(bot, text="🔄 Aplicar Correcciones",
                                    command=self._aplicar_correcciones,
                                    state='disabled', style='Accent.TButton')
        self.btn_apply.pack(side=tk.RIGHT, padx=4)

    # ── Mensaje inicial ──────────────────────────────────────────────────
    def _msg_bienvenida(self):
        self.tree.insert('', 'end', values=(
            'ℹ️', 'Selecciona un archivo o carpeta y haz clic en Analizar',
            '', '', '', ''))

    # ── Selección ────────────────────────────────────────────────────────
    def _sel_archivo(self):
        f = filedialog.askopenfilename(
            title="Seleccionar archivo",
            filetypes=[("Multimedia", " ".join(
                f"*{e}" for e in EXTENSIONES_MULTIMEDIA)),
                ("Todos", "*.*")])
        if f:
            self.ruta_actual.set(f)

    def _sel_carpeta(self):
        d = filedialog.askdirectory(title="Seleccionar carpeta")
        if d:
            self.ruta_actual.set(d)

    # ── Análisis (hilo separado) ─────────────────────────────────────────
    def _iniciar_analisis(self):
        ruta = self.ruta_actual.get()
        if not ruta:
            messagebox.showwarning("Sin ruta", "Selecciona un archivo o carpeta primero.")
            return
        if not os.path.exists(ruta):
            messagebox.showerror("Error", "La ruta no existe.")
            return

        self._limpiar()
        self._cancelar.clear()
        self.progreso['value'] = 0
        self.lbl_prog.config(text="Recopilando archivos…")
        threading.Thread(target=self._analisis_worker, args=(ruta,),
                         daemon=True).start()

    def _cancelar_analisis(self):
        self._cancelar.set()

    def _analisis_worker(self, ruta):
        # Recopilar archivos
        archivos = []
        if os.path.isfile(ruta):
            archivos = [ruta]
        else:
            walk = os.walk(ruta) if self.incluir_subcarpetas.get() \
                   else [(ruta, [], os.listdir(ruta))]
            for root_dir, _, files in walk:
                for f in files:
                    if Path(f).suffix.lower() in EXTENSIONES_MULTIMEDIA:
                        archivos.append(os.path.join(root_dir, f))

        total = len(archivos)
        self.root.after(0, lambda: self.progreso.config(maximum=max(total, 1)))
        filtro = self.filtro_tipo.get()
        resultados = []

        for i, ruta_archivo in enumerate(archivos):
            if self._cancelar.is_set():
                break

            fmt_real, ext_actual, error = detectar_formato(ruta_archivo)
            coincide = formatos_coinciden(fmt_real, ext_actual) if not error else False
            tipo = TIPO_LABEL.get(fmt_real, '—')
            resultados.append((ruta_archivo, fmt_real, ext_actual, coincide, tipo, error))

            # Actualizar UI cada 5 archivos o al final
            if i % 5 == 0 or i == total - 1:
                snap = resultados.copy()
                prog_val = i + 1
                self.root.after(0, lambda s=snap, p=prog_val, t=total:
                                self._actualizar_ui(s, p, t))

        self.root.after(0, lambda: self._analisis_completo(resultados))

    def _actualizar_ui(self, resultados, prog, total):
        self.progreso['value'] = prog
        self.lbl_prog.config(text=f"Analizando… {prog}/{total}")
        # Actualizar tree con los últimos registros añadidos
        self._poblar_tree(resultados)

    def _analisis_completo(self, resultados):
        self.archivos_analizados = resultados
        self._poblar_tree(resultados)
        self.lbl_prog.config(text=f"Completado — {len(resultados)} archivos")
        self._actualizar_stats()

    def _poblar_tree(self, resultados):
        self.tree.delete(*self.tree.get_children())
        filtro = self.filtro_tipo.get()
        for ruta_archivo, fmt_real, ext_actual, coincide, tipo, error in resultados:
            # Aplicar filtro
            if filtro == 'Sólo errores' and coincide:
                continue
            if filtro == 'Imágenes' and tipo != 'Imagen':
                continue
            if filtro == 'RAW' and tipo != 'RAW':
                continue
            if filtro == 'Video' and tipo != 'Video':
                continue

            if error:
                estado, tag = '❌', 'unk'
            elif coincide:
                estado, tag = '✓', 'ok'
            else:
                estado, tag = '⚠️', 'err'

            p = Path(ruta_archivo)
            self.tree.insert('', 'end', tags=(tag,),
                             values=(estado, p.name, str(p.parent),
                                     ext_actual, fmt_real, tipo))

    def _actualizar_stats(self):
        total = len(self.archivos_analizados)
        errores = sum(1 for _, _, _, coincide, _, err in self.archivos_analizados
                      if not coincide)
        ok = total - errores
        self.lbl_stats.config(
            text=f"📊 Total: {total}   ✓ Correctos: {ok}   ⚠️ Incorrectos: {errores}")
        estado = 'normal' if errores > 0 else 'disabled'
        self.btn_apply.config(state=estado)

    # ── Ordenar columnas ─────────────────────────────────────────────────
    def _sort_tree(self, col, reverse):
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        items.sort(reverse=reverse)
        for idx, (_, k) in enumerate(items):
            self.tree.move(k, '', idx)
        self.tree.heading(col, command=lambda: self._sort_tree(col, not reverse))

    # ── Exportar CSV ─────────────────────────────────────────────────────
    def _exportar_csv(self):
        if not self.archivos_analizados:
            messagebox.showinfo("Sin datos", "Primero analiza archivos.")
            return
        destino = filedialog.asksaveasfilename(
            defaultextension='.csv', filetypes=[('CSV', '*.csv')],
            title="Guardar reporte CSV")
        if not destino:
            return
        with open(destino, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['Archivo', 'Carpeta', 'Ext actual', 'Fmt real',
                        'Tipo', 'Estado', 'Error'])
            for ruta_archivo, fmt_real, ext_actual, coincide, tipo, error in \
                    self.archivos_analizados:
                p = Path(ruta_archivo)
                estado = 'OK' if coincide else ('ERROR' if error else 'DISCREPANCIA')
                w.writerow([p.name, str(p.parent), ext_actual,
                             fmt_real, tipo, estado, error or ''])
        messagebox.showinfo("Exportado", f"Reporte guardado en:\n{destino}")

    # ── Aplicar correcciones ─────────────────────────────────────────────
    def _aplicar_correcciones(self):
        a_corregir = [(r, f, e, t, err)
                      for r, f, e, coincide, t, err in self.archivos_analizados
                      if not coincide and not err]
        if not a_corregir:
            messagebox.showinfo("Sin cambios", "No hay discrepancias a corregir.")
            return

        modo = self.modo_renombrado.get()
        desc_modo = {
            'backup':        '🛡️  Backup + Renombrar  (original respaldado)',
            'agregar':       '📝 Agregar sufijo _corrected  (original intacto)',
            'nueva_carpeta': '📁 Copiar a _archivos_corregidos  (original intacto)',
            'directo':       '⚡ Renombrar directo  ⚠️ SIN backup',
        }
        if not messagebox.askyesno(
                "Confirmar",
                f"Se procesarán {len(a_corregir)} archivo(s).\n\n"
                f"Modo: {desc_modo.get(modo, modo)}\n\n¿Continuar?"):
            return

        exitosos, errores_op = 0, []
        carpeta_backup = None
        carpeta_nueva = None

        if modo == 'backup':
            primer_dir = str(Path(a_corregir[0][0]).parent)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            carpeta_backup = os.path.join(primer_dir, f"_backup_{ts}")
            os.makedirs(carpeta_backup, exist_ok=True)

        if modo == 'nueva_carpeta':
            primer_dir = str(Path(a_corregir[0][0]).parent)
            carpeta_nueva = os.path.join(primer_dir, "_archivos_corregidos")
            os.makedirs(carpeta_nueva, exist_ok=True)

        for ruta_archivo, fmt_real, ext_actual, tipo, _ in a_corregir:
            try:
                p = Path(ruta_archivo)
                nueva_ext = f".{fmt_real.lower()}"

                if modo == 'backup':
                    shutil.copy2(ruta_archivo, os.path.join(carpeta_backup, p.name))
                    destino = self._nombre_libre(p.parent / (p.stem + nueva_ext), p)
                    os.rename(ruta_archivo, destino)

                elif modo == 'agregar':
                    destino = self._nombre_libre(p.parent / (p.stem + "_corrected" + nueva_ext))
                    shutil.copy2(ruta_archivo, destino)

                elif modo == 'nueva_carpeta':
                    destino = self._nombre_libre(Path(carpeta_nueva) / (p.stem + nueva_ext))
                    shutil.copy2(ruta_archivo, destino)

                else:  # directo
                    destino = self._nombre_libre(p.parent / (p.stem + nueva_ext), p)
                    os.rename(ruta_archivo, destino)

                exitosos += 1
            except Exception as e:
                errores_op.append(f"{Path(ruta_archivo).name}: {e}")

        extra = ""
        if carpeta_backup:
            extra = f"\n\nBackup en: {carpeta_backup}"
        if carpeta_nueva:
            extra = f"\n\nArchivos en: {carpeta_nueva}"
        if errores_op:
            extra += "\n\nErrores:\n" + "\n".join(errores_op[:8])

        msg = f"✓ Procesados: {exitosos}\n✗ Errores: {len(errores_op)}{extra}"
        if errores_op:
            messagebox.showwarning("Completado con errores", msg)
        else:
            messagebox.showinfo("Completado", msg)

        # Re-analizar
        if self.ruta_actual.get():
            self._iniciar_analisis()

    @staticmethod
    def _nombre_libre(ruta: Path, original: Path = None):
        """Devuelve una ruta que no colisione con archivos existentes."""
        if not ruta.exists() or ruta == original:
            return ruta
        contador = 1
        while True:
            candidato = ruta.parent / f"{ruta.stem}_{contador}{ruta.suffix}"
            if not candidato.exists():
                return candidato
            contador += 1

    # ── Limpiar ──────────────────────────────────────────────────────────
    def _limpiar(self):
        self.tree.delete(*self.tree.get_children())
        self.archivos_analizados = []
        self.lbl_stats.config(text="")
        self.progreso['value'] = 0
        self.lbl_prog.config(text="")
        self.btn_apply.config(state='disabled')


# ──────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()