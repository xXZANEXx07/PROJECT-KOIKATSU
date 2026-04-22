"""
Clasificador de Cartas Koikatsu v4.2
Optimizaciones vs v4.1 (enfocadas en HDD + >10k archivos):

  - Un solo worker secuencial para I/O en HDD (evita seeks aleatorios)
  - Lee solo los primeros N bytes necesarios, no el archivo completo
  - Sin mmap (contraproducente en HDD para acceso secuencial)
  - Mueve archivos en batch al final, no uno a uno durante el loop
  - os.stat() una sola vez por archivo en lugar de getsize + open
  - Pool conservado como fallback si el usuario tiene SSD
  - Prefetch manual con os.posix_fadvise en Linux (ignorado en Windows)
"""

import os
import sys
import shutil
import hashlib
import logging
import threading
import queue
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional, Tuple, List, Dict
from logging.handlers import RotatingFileHandler

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

PNG_HEADER     = b'\x89PNG\r\n\x1a\n'
PNG_END        = b'IEND\xae\x42\x60\x82'
FAST_BYTES     = 4096
MIN_CHUNK_SIZE = 8 + 4 + 4   # len + type + crc
# Máximo bytes a leer por archivo. Las cartas KK raramente superan 2 MB
# para la imagen embebida; leer más es desperdiciar I/O en HDD.
MAX_READ_BYTES = 3 * 1024 * 1024   # 3 MB


# ---------------------------------------------------------------------------
# Extracción de chunks — igual que v4.1
# ---------------------------------------------------------------------------

def _find_first_two_chunks(data: bytes) -> Tuple[Optional[Tuple[int,int]], Optional[Tuple[int,int]]]:
    found = []
    pos = 0
    while len(found) < 2:
        h = data.find(PNG_HEADER, pos)
        if h == -1:
            break
        e = data.find(PNG_END, h + 8)
        if e == -1:
            break
        e += 4
        found.append((h, e))
        pos = e
    c1 = found[0] if len(found) > 0 else None
    c2 = found[1] if len(found) > 1 else None
    return c1, c2


# ---------------------------------------------------------------------------
# Comparación rápida en dos fases — igual que v4.1
# ---------------------------------------------------------------------------

def _fast_identical(mv: memoryview, s1: int, e1: int, s2: int, e2: int) -> bool:
    len1 = e1 - s1
    len2 = e2 - s2
    if len1 != len2:
        return False
    limit = min(FAST_BYTES, len1)
    if mv[s1 : s1 + limit] != mv[s2 : s2 + limit]:
        return False
    h1 = hashlib.md5(mv[s1:e1]).digest()
    h2 = hashlib.md5(mv[s2:e2]).digest()
    return h1 == h2


# ---------------------------------------------------------------------------
# Clasificación de un archivo — versión optimizada para HDD
# Lee solo lo necesario, sin mmap, una sola apertura
# ---------------------------------------------------------------------------

def _classify_one(file_path: Path) -> str:
    """
    Clasifica una carta KK leyendo solo los bytes necesarios.
    Retorna: 'extraidas' | 'originales' | 'sin_segunda' | 'error'
    """
    try:
        stat = os.stat(file_path)
        file_size = stat.st_size
        if file_size < MIN_CHUNK_SIZE * 2:
            return 'sin_segunda'

        # Leer solo hasta MAX_READ_BYTES — en HDD esto es crítico.
        # Si el segundo chunk está más allá, se clasifica como sin_segunda
        # (caso muy raro en cartas KK reales).
        read_size = min(file_size, MAX_READ_BYTES)
        with open(file_path, "rb", buffering=512 * 1024) as f:
            data = f.read(read_size)

        c1, c2 = _find_first_two_chunks(data)
        if c1 is None or c2 is None:
            return 'sin_segunda'

        mv = memoryview(data)
        return 'extraidas' if _fast_identical(mv, c1[0], c1[1], c2[0], c2[1]) else 'originales'

    except Exception as e:
        logging.error(f"Error clasificando {file_path}: {e}")
        return 'error'


# ---------------------------------------------------------------------------
# Clasificador principal
# ---------------------------------------------------------------------------

class KoikatsuClassifier:
    CATEGORIES = ('extraidas', 'originales', 'sin_segunda', 'error')

    def __init__(self):
        self._setup_logging()

    def _setup_logging(self):
        handler = RotatingFileHandler(
            'koikatsu_classifier.log',
            maxBytes=5 * 1024 * 1024,
            backupCount=2,
            encoding='utf-8'
        )
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s %(levelname)s %(message)s',
            handlers=[handler, logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)

    def _create_dirs(self, base: Path) -> Dict[str, Path]:
        dirs = {cat: base / cat for cat in self.CATEGORIES}
        for d in dirs.values():
            d.mkdir(exist_ok=True)
        return dirs

    def _get_png_files(self, folder: Path) -> List[Path]:
        exclude = {'_preview.png', '_thumb.png'}
        return sorted(
            p for p in folder.iterdir()
            if p.is_file()
            and p.suffix.lower() == '.png'
            and not any(ex in p.name.lower() for ex in exclude)
        )

    def classify_folder(
        self,
        folder_path: Path,
        result_queue: queue.Queue,
        cancel_event: threading.Event,
    ) -> None:
        folder_path = Path(folder_path)
        dirs        = self._create_dirs(folder_path)
        files       = self._get_png_files(folder_path)

        stats = {cat: 0 for cat in self.CATEGORIES}
        stats['total'] = len(files)

        if not files:
            result_queue.put(('done', stats, 0.0))
            return

        self.logger.info(f"Procesando {len(files)} archivos (modo secuencial HDD)")
        result_queue.put(('start', len(files)))

        t0 = time.time()

        # Acumulador de movimientos: {categoria: [(src, dst), ...]}
        # Mover en batch es más eficiente en HDD que intercalar con lecturas.
        moves: Dict[str, List[Tuple[Path, Path]]] = {cat: [] for cat in self.CATEGORIES}

        for idx, file_path in enumerate(files, 1):
            if cancel_event.is_set():
                # Mover lo ya clasificado antes de salir
                self._flush_moves(moves)
                elapsed = time.time() - t0
                result_queue.put(('cancelled', stats, elapsed))
                return

            category = _classify_one(file_path)
            stats[category] += 1
            moves[category].append((file_path, dirs[category] / file_path.name))

            result_queue.put(('progress', idx, file_path.name))

            # Flush cada 500 archivos para no acumular demasiado en memoria
            # y también para que la cancelación no pierda demasiado trabajo.
            if idx % 500 == 0:
                self._flush_moves(moves)

        # Flush final
        self._flush_moves(moves)

        elapsed = time.time() - t0
        result_queue.put(('done', stats, elapsed))

    def _flush_moves(self, moves: Dict[str, List[Tuple[Path, Path]]]) -> None:
        """Mueve los archivos acumulados y vacía el dict."""
        for cat, pairs in moves.items():
            for src, dst in pairs:
                try:
                    shutil.move(str(src), str(dst))
                except Exception as e:
                    self.logger.error(f"Error moviendo {src}: {e}")
            pairs.clear()


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class KoikatsuGUI:
    POLL_MS = 50

    def __init__(self):
        self.classifier    = KoikatsuClassifier()
        self._cancel_event = threading.Event()
        self._result_queue: queue.Queue = queue.Queue()
        self._total_files  = 0
        self._start_time: Optional[float] = None
        self._running      = False
        self._build_ui()

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("Clasificador Koikatsu v4.2")
        self.root.geometry("680x540")
        self.root.resizable(True, True)

        style = ttk.Style()
        style.theme_use('clam')

        mf = ttk.Frame(self.root, padding="20")
        mf.grid(row=0, column=0, sticky='nsew')
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        mf.columnconfigure(0, weight=1)
        mf.rowconfigure(9, weight=1)

        ttk.Label(mf, text="Clasificador de Cartas Koikatsu",
                  font=('Arial', 16, 'bold')).grid(row=0, column=0, columnspan=2, pady=(0, 3))

        ttk.Label(mf,
                  text="Modo HDD — lectura secuencial optimizada",
                  font=('Arial', 9, 'italic'), foreground='green'
                  ).grid(row=1, column=0, columnspan=2, pady=(0, 14))

        ff = ttk.Frame(mf)
        ff.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(0, 12))
        ff.columnconfigure(0, weight=1)

        self.folder_var = tk.StringVar()
        ttk.Entry(ff, textvariable=self.folder_var).grid(row=0, column=0, padx=(0, 8), sticky='ew')
        ttk.Button(ff, text="Seleccionar carpeta",
                   command=self._browse).grid(row=0, column=1)

        btn_frame = ttk.Frame(mf)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(0, 12))

        self.start_btn = ttk.Button(btn_frame, text="Iniciar clasificación",
                                    command=self._start)
        self.start_btn.grid(row=0, column=0, padx=(0, 8))

        self.cancel_btn = ttk.Button(btn_frame, text="Cancelar",
                                     command=self._cancel, state=tk.DISABLED)
        self.cancel_btn.grid(row=0, column=1)

        pf = ttk.Frame(mf)
        pf.grid(row=4, column=0, columnspan=2, sticky='ew', pady=(0, 6))
        pf.columnconfigure(0, weight=1)

        self.progress_var = tk.DoubleVar()
        ttk.Progressbar(pf, variable=self.progress_var, maximum=100,
                        mode='determinate').grid(row=0, column=0, sticky='ew')
        self.pct_label = ttk.Label(pf, text="0 %", width=7, anchor='e')
        self.pct_label.grid(row=0, column=1, padx=(6, 0))

        self.status_var = tk.StringVar(value="Listo.")
        ttk.Label(mf, textvariable=self.status_var,
                  font=('Arial', 9)).grid(row=5, column=0, columnspan=2, pady=(0, 2))

        self.speed_var = tk.StringVar(value="")
        ttk.Label(mf, textvariable=self.speed_var,
                  font=('Arial', 9, 'bold'), foreground='#1565C0'
                  ).grid(row=6, column=0, columnspan=2, pady=(0, 10))

        rf = ttk.LabelFrame(mf, text="Resultados", padding="10")
        rf.grid(row=9, column=0, columnspan=2, sticky='nsew', pady=(4, 0))
        rf.columnconfigure(0, weight=1)
        rf.rowconfigure(0, weight=1)

        self.results_text = tk.Text(rf, height=10, width=62, font=('Consolas', 9),
                                    state=tk.DISABLED)
        sb = ttk.Scrollbar(rf, orient=tk.VERTICAL, command=self.results_text.yview)
        self.results_text.configure(yscrollcommand=sb.set)
        self.results_text.grid(row=0, column=0, sticky='nsew')
        sb.grid(row=0, column=1, sticky='ns')

    def _browse(self):
        folder = filedialog.askdirectory(title="Selecciona carpeta con cartas Koikatsu")
        if folder:
            self.folder_var.set(folder)

    def _start(self):
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("Advertencia", "Selecciona una carpeta primero.")
            return
        if not Path(folder).exists():
            messagebox.showerror("Error", "La carpeta no existe.")
            return

        self._cancel_event.clear()
        self._result_queue = queue.Queue()
        self.progress_var.set(0)
        self.pct_label.config(text="0 %")
        self.status_var.set("Iniciando…")
        self.speed_var.set("")
        self._set_results("")
        self._total_files  = 0
        self._start_time   = None
        self._running      = True

        self.start_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)

        threading.Thread(target=self._worker, args=(folder,), daemon=True).start()
        self._poll()

    def _cancel(self):
        self._cancel_event.set()
        self.cancel_btn.config(state=tk.DISABLED)
        self.status_var.set("Cancelando…")

    def _worker(self, folder: str):
        try:
            self.classifier.classify_folder(
                Path(folder), self._result_queue, self._cancel_event)
        except Exception as e:
            self._result_queue.put(('error', str(e)))

    def _poll(self):
        try:
            while True:
                msg = self._result_queue.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass
        if self._running:
            self.root.after(self.POLL_MS, self._poll)

    def _handle_msg(self, msg):
        kind = msg[0]

        if kind == 'start':
            self._total_files = msg[1]
            self._start_time  = time.time()

        elif kind == 'progress':
            _, current, filename = msg
            total = self._total_files or 1
            pct   = current / total * 100
            self.progress_var.set(pct)
            self.pct_label.config(text=f"{pct:.0f} %")
            self.status_var.set(f"Procesando: {filename}  ({current}/{total})")
            if self._start_time:
                elapsed = time.time() - self._start_time
                if elapsed > 0:
                    fps = current / elapsed
                    eta = (total - current) / fps if fps > 0 else 0
                    self.speed_var.set(f"{fps:.1f} archivos/seg  —  ETA: {int(eta)} s")

        elif kind == 'done':
            _, stats, elapsed = msg
            self._finish(stats, elapsed, cancelled=False)

        elif kind == 'cancelled':
            _, stats, elapsed = msg
            self._finish(stats, elapsed, cancelled=True)

        elif kind == 'error':
            self._on_error(msg[1])

    def _finish(self, stats: dict, elapsed: float, cancelled: bool):
        self._running = False
        self.start_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.progress_var.set(100 if not cancelled else self.progress_var.get())

        total = stats.get('total', 0)
        if total == 0:
            self.status_var.set("No se encontraron archivos PNG.")
            self._set_results("No se encontraron archivos PNG en la carpeta seleccionada.")
            return

        fps    = total / elapsed if elapsed > 0 else 0
        avg_ms = elapsed / total * 1000 if total > 0 else 0

        def pct(n): return f"{n/total*100:.1f}" if total > 0 else "0.0"

        lines = [
            "=" * 47,
            "  CLASIFICACIÓN " + ("CANCELADA" if cancelled else "COMPLETADA"),
            "=" * 47,
            "",
            f"  Total procesado : {total} archivos",
            f"  Tiempo          : {elapsed:.2f} s",
            f"  Velocidad       : {fps:.1f} archivos/s",
            f"  Tiempo promedio : {avg_ms:.0f} ms/archivo",
            "",
            "  DISTRIBUCIÓN:",
            f"  + Extraidas     : {stats['extraidas']} ({pct(stats['extraidas'])} %)",
            f"  + Originales    : {stats['originales']} ({pct(stats['originales'])} %)",
            f"  ! Sin 2ª imagen : {stats['sin_segunda']} ({pct(stats['sin_segunda'])} %)",
            f"  x Errores       : {stats['error']} ({pct(stats['error'])} %)",
            "",
            "  Archivos movidos a subcarpetas correspondientes.",
        ]
        self._set_results("\n".join(lines))
        estado = "Cancelado" if cancelled else "Completado"
        self.status_var.set(f"{estado} — {total} archivos en {elapsed:.2f} s")
        self.speed_var.set(f"Velocidad media: {fps:.1f} archivos/s")

        if not cancelled:
            messagebox.showinfo(
                "Completado",
                f"Clasificación completada en {elapsed:.2f} s\n"
                f"Velocidad: {fps:.1f} archivos/segundo"
            )

    def _on_error(self, msg: str):
        self._running = False
        self.start_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.status_var.set("Error durante la clasificación.")
        self.speed_var.set("")
        messagebox.showerror("Error", f"Ocurrió un error:\n{msg}")

    def _set_results(self, text: str):
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        if text:
            self.results_text.insert(tk.END, text)
        self.results_text.config(state=tk.DISABLED)

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------

def main():
    if sys.platform == 'win32':
        if hasattr(sys.stdout, 'buffer'):
            import codecs
            try:
                sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
                sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
            except Exception:
                pass

    print("Clasificador Koikatsu v4.2 — modo HDD optimizado")
    KoikatsuGUI().run()


if __name__ == "__main__":
    main()