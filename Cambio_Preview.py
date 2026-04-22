import os
import re
import subprocess
import threading
import time
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image
from io import BytesIO
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List
from dataclasses import dataclass, asdict


@dataclass
class Config:
    last_folder: str = ""
    last_exe: str = ""
    window_width: int = 860
    window_height: int = 580
    backup_enabled: bool = True
    keep_preview_files: bool = False
    timeout_seconds: int = 10
    max_workers: int = 6


@dataclass
class ProcessResult:
    file_path: str
    status: str  # 'success', 'failed', 'no_images', 'invalid'
    error_message: str = ""


@dataclass
class Stats:
    total: int = 0
    processed: int = 0
    successful: int = 0
    failed: int = 0
    no_images: int = 0
    invalid: int = 0
    start_time: float = 0.0

    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time if self.start_time else 0

    @property
    def success_rate(self) -> float:
        return (self.successful / self.total * 100) if self.total > 0 else 0


class CardProcessor:
    CONFIG_FILE = "config.json"
    PNG_PATTERN = re.compile(b'\x89PNG\r\n\x1a\n.*?\x49\x45\x4e\x44\xae\x42\x60\x82', re.DOTALL)

    def __init__(self):
        self.config = Config()
        self.stats = Stats()
        self.processing = False
        self.cancel_requested = False
        self.load_config()
        self.setup_ui()

    def load_config(self):
        if not os.path.exists(self.CONFIG_FILE):
            return
        try:
            with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for k, v in data.items():
                    if hasattr(self.config, k):
                        setattr(self.config, k, v)
        except Exception as e:
            print(f"Error cargando config: {e}")

    def save_config(self):
        try:
            self.config.last_folder = self.folder_var.get()
            self.config.last_exe = self.exe_var.get()
            self.config.backup_enabled = self.backup_var.get()
            self.config.keep_preview_files = self.keep_preview_var.get()
            self.config.window_width = self.root.winfo_width()
            self.config.window_height = self.root.winfo_height()
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(asdict(self.config), f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Error guardando config: {e}")

    def setup_ui(self):
        self.root = tk.Tk()
        self.root.title("Koikatsu Card Preview Replacer v3.1")
        self.root.geometry(f"{self.config.window_width}x{self.config.window_height}")

        self.folder_var = tk.StringVar(value=self.config.last_folder)
        self.exe_var = tk.StringVar(value=self.config.last_exe)
        self.backup_var = tk.BooleanVar(value=self.config.backup_enabled)
        self.keep_preview_var = tk.BooleanVar(value=self.config.keep_preview_files)
        self.progress_var = tk.DoubleVar()
        self.threads_var = tk.IntVar(value=self.config.max_workers)
        self.timeout_var = tk.IntVar(value=self.config.timeout_seconds)

        self.create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.bind('<F5>', lambda e: self.start_processing())
        self.root.bind('<Escape>', lambda e: self.cancel_processing())

    def create_widgets(self):
        main = ttk.Frame(self.root, padding="15")
        main.pack(fill=tk.BOTH, expand=True)

        # --- Archivos ---
        files = ttk.LabelFrame(main, text="Archivos", padding="12")
        files.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(files, text="Carpeta de cartas:").pack(anchor=tk.W)
        row1 = ttk.Frame(files)
        row1.pack(fill=tk.X, pady=(3, 10))
        ttk.Entry(row1, textvariable=self.folder_var, font=('Consolas', 9)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(row1, text="Explorar", command=self.select_folder).pack(side=tk.RIGHT)

        ttk.Label(files, text="CardImageReplacer.exe:").pack(anchor=tk.W)
        row2 = ttk.Frame(files)
        row2.pack(fill=tk.X, pady=(3, 0))
        ttk.Entry(row2, textvariable=self.exe_var, font=('Consolas', 9)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(row2, text="Explorar", command=self.select_exe).pack(side=tk.RIGHT)

        # --- Opciones ---
        opts = ttk.LabelFrame(main, text="Opciones", padding="12")
        opts.pack(fill=tk.X, pady=(0, 12))

        opt_row = ttk.Frame(opts)
        opt_row.pack(fill=tk.X)
        ttk.Checkbutton(opt_row, text="Crear respaldo", variable=self.backup_var).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Checkbutton(opt_row, text="Mantener previews temporales", variable=self.keep_preview_var).pack(side=tk.LEFT, padx=(0, 20))

        cfg_row = ttk.Frame(opts)
        cfg_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(cfg_row, text="Hilos:").pack(side=tk.LEFT)
        ttk.Spinbox(cfg_row, from_=1, to=12, width=4, textvariable=self.threads_var).pack(side=tk.LEFT, padx=(4, 20))
        ttk.Label(cfg_row, text="Timeout (s):").pack(side=tk.LEFT)
        ttk.Spinbox(cfg_row, from_=5, to=60, width=5, textvariable=self.timeout_var).pack(side=tk.LEFT, padx=(4, 0))

        # --- Controles ---
        ctrl = ttk.Frame(main)
        ctrl.pack(fill=tk.X, pady=(0, 12))

        self.process_btn = ttk.Button(ctrl, text="PROCESAR (F5)", command=self.start_processing)
        self.process_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.cancel_btn = ttk.Button(ctrl, text="CANCELAR (Esc)", command=self.cancel_processing, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(ctrl, text="Abrir carpeta", command=self.open_folder).pack(side=tk.LEFT)

        # --- Progreso ---
        prog = ttk.LabelFrame(main, text="Progreso", padding="12")
        prog.pack(fill=tk.X, pady=(0, 12))

        self.progress_label = ttk.Label(prog, text="Listo")
        self.progress_label.pack(anchor=tk.W)
        self.progress_bar = ttk.Progressbar(prog, variable=self.progress_var, maximum=100, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(6, 0))

        # Fila de stats simples
        stats_row = ttk.Frame(prog)
        stats_row.pack(fill=tk.X, pady=(8, 0))
        self.stats_labels = {}
        for label, key in [("Total:", "total"), ("OK:", "successful"), ("Fallo:", "failed"),
                           ("Sin img:", "no_images"), ("Tiempo:", "time"), ("Vel:", "rate")]:
            ttk.Label(stats_row, text=label, font=('Segoe UI', 9, 'bold')).pack(side=tk.LEFT)
            lbl = ttk.Label(stats_row, text="0", font=('Consolas', 9))
            lbl.pack(side=tk.LEFT, padx=(2, 14))
            self.stats_labels[key] = lbl

        # --- Log ---
        log_frame = ttk.LabelFrame(main, text="Log", padding="8")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, height=8, wrap=tk.WORD, font=('Consolas', 9))
        sb = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    def log(self, message: str):
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] {message}\n")
        self.log_text.see(tk.END)
        lines = int(self.log_text.index('end-1c').split('.')[0])
        if lines > 300:
            self.log_text.delete(1.0, "100.0")

    def update_stats(self):
        self.stats_labels["total"].config(text=str(self.stats.total))
        self.stats_labels["successful"].config(text=str(self.stats.successful))
        self.stats_labels["failed"].config(text=str(self.stats.failed))
        self.stats_labels["no_images"].config(text=str(self.stats.no_images))
        elapsed = self.stats.elapsed_time
        self.stats_labels["time"].config(text=f"{elapsed:.1f}s")
        if elapsed > 0:
            self.stats_labels["rate"].config(text=f"{self.stats.processed / elapsed:.1f}/s")

    def update_progress(self, current: int, total: int):
        if total > 0:
            self.progress_var.set((current / total) * 100)
            if current % 10 == 0 or current == total:
                self.progress_label.config(text=f"Procesando {current}/{total}...")
                self.root.update_idletasks()

    def select_folder(self):
        folder = filedialog.askdirectory(title="Carpeta de cartas", initialdir=self.config.last_folder)
        if folder:
            self.folder_var.set(folder)
            self.log(f"Carpeta: {folder}")

    def select_exe(self):
        exe = filedialog.askopenfilename(
            title="CardImageReplacer.exe",
            filetypes=[("Ejecutable", "*.exe")],
            initialdir=os.path.dirname(self.config.last_exe) if self.config.last_exe else ""
        )
        if exe:
            self.exe_var.set(exe)
            self.log(f"Exe: {os.path.basename(exe)}")

    def open_folder(self):
        path = self.folder_var.get().strip()
        if path and os.path.isdir(path):
            try:
                os.startfile(path)
            except Exception:
                pass

    def validate_config(self) -> bool:
        folder = self.folder_var.get().strip()
        exe = self.exe_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Error", "Selecciona una carpeta válida")
            return False
        if not exe or not os.path.isfile(exe):
            messagebox.showerror("Error", "Selecciona un ejecutable válido")
            return False
        if not self.get_png_files(folder):
            messagebox.showerror("Error", "No se encontraron archivos PNG")
            return False
        return True

    def get_png_files(self, folder: str) -> List[str]:
        try:
            skip = ('_preview', '.backup', '_temp', '_bak')
            return [
                str(p) for p in Path(folder).glob("*.png")
                if not any(s in p.name.lower() for s in skip)
            ]
        except Exception:
            return []

    def extract_embedded_pngs(self, file_path: str) -> List[bytes]:
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            return [m.group() for m in self.PNG_PATTERN.finditer(data) if len(m.group()) > 1000]
        except Exception:
            return []

    def save_preview_image(self, image_data: bytes, output_path: str) -> bool:
        try:
            with Image.open(BytesIO(image_data)) as img:
                if img.mode not in ('RGBA', 'RGB'):
                    img = img.convert('RGBA')
                img.save(output_path, "PNG")
            return True
        except Exception:
            return False

    def create_backup(self, file_path: str) -> bool:
        backup = f"{file_path}.backup"
        if os.path.exists(backup):
            return True
        try:
            shutil.copy2(file_path, backup)
            return True
        except Exception as e:
            self.log(f"Error backup {os.path.basename(file_path)}: {e}")
            return False

    def replace_preview(self, card_path: str, preview_path: str) -> bool:
        try:
            exe = self.exe_var.get()
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            result = subprocess.run(
                [exe, card_path, preview_path, card_path],
                capture_output=True,
                timeout=self.timeout_var.get(),
                cwd=os.path.dirname(exe),
                startupinfo=si
            )
            return result.returncode == 0
        except Exception:
            return False

    def process_single_card(self, card_path: str) -> ProcessResult:
        if not os.path.exists(card_path):
            return ProcessResult(card_path, 'failed', 'Archivo no encontrado')
        if os.path.getsize(card_path) < 1024:
            return ProcessResult(card_path, 'invalid', 'Archivo muy pequeño')

        images = self.extract_embedded_pngs(card_path)
        if len(images) < 2:
            return ProcessResult(card_path, 'no_images', f'Solo {len(images)} imagen(es) embebida(s)')

        preview_path = card_path.replace('.png', f'_preview_{int(time.time()*1000)}.png')

        # Intentar imagen [1] primero, luego [0] como fallback
        saved = self.save_preview_image(images[1], preview_path) or \
                self.save_preview_image(images[0], preview_path)
        if not saved:
            return ProcessResult(card_path, 'failed', 'Error guardando preview')

        if self.backup_var.get() and not self.create_backup(card_path):
            try: os.remove(preview_path)
            except Exception: pass
            return ProcessResult(card_path, 'failed', 'Error creando backup')

        success = self.replace_preview(card_path, preview_path)

        if not self.keep_preview_var.get():
            try: os.remove(preview_path)
            except Exception: pass

        if not success:
            return ProcessResult(card_path, 'failed', 'Error en CardImageReplacer')

        return ProcessResult(card_path, 'success')

    def process_cards(self):
        try:
            folder = self.folder_var.get()
            png_files = self.get_png_files(folder)
            if not png_files:
                self.log("No se encontraron PNGs")
                return

            self.stats = Stats()
            self.stats.total = len(png_files)
            self.stats.start_time = time.time()

            workers = self.threads_var.get()
            self.log(f"Iniciando: {len(png_files)} archivos, {workers} hilos")

            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(self.process_single_card, p): p for p in png_files}

                for future in as_completed(futures):
                    if self.cancel_requested:
                        break
                    try:
                        result = future.result()
                        self.stats.processed += 1
                        if result.status == 'success':
                            self.stats.successful += 1
                        elif result.status == 'failed':
                            self.stats.failed += 1
                            self.log(f"FALLO: {os.path.basename(result.file_path)} — {result.error_message}")
                        elif result.status == 'no_images':
                            self.stats.no_images += 1
                            self.log(f"SIN IMG: {os.path.basename(result.file_path)}")
                        elif result.status == 'invalid':
                            self.stats.invalid += 1
                    except Exception as e:
                        self.stats.failed += 1
                        self.log(f"Error inesperado: {e}")

                    self.update_progress(self.stats.processed, self.stats.total)
                    self.update_stats()

            elapsed = self.stats.elapsed_time
            fps = self.stats.total / elapsed if elapsed > 0 else 0

            if self.cancel_requested:
                self.log("Procesamiento cancelado.")
            else:
                summary = (
                    f"Completado — OK: {self.stats.successful}  "
                    f"Fallo: {self.stats.failed}  "
                    f"Sin img: {self.stats.no_images}  "
                    f"Inválidos: {self.stats.invalid}  "
                    f"Tiempo: {elapsed:.1f}s  "
                    f"Vel: {fps:.1f}/s  "
                    f"Éxito: {self.stats.success_rate:.1f}%"
                )
                self.log(summary)
                self.progress_var.set(100)
                self.progress_label.config(text="Completado")
                messagebox.showinfo("Completado", summary)

        except Exception as e:
            self.log(f"Error crítico: {e}")
            messagebox.showerror("Error crítico", str(e))
        finally:
            self.processing = False
            self.cancel_requested = False
            self.process_btn.config(state=tk.NORMAL, text="PROCESAR (F5)")
            self.cancel_btn.config(state=tk.DISABLED)

    def start_processing(self):
        if self.processing:
            return
        if not self.validate_config():
            return

        png_files = self.get_png_files(self.folder_var.get())
        if len(png_files) > 100:
            if not messagebox.askyesno("Confirmación", f"Se procesarán {len(png_files)} archivos.\n¿Continuar?", icon='warning'):
                return

        self.processing = True
        self.cancel_requested = False
        self.process_btn.config(state=tk.DISABLED, text="Procesando...")
        self.cancel_btn.config(state=tk.NORMAL)
        self.progress_var.set(0)
        self.config.max_workers = self.threads_var.get()
        self.config.timeout_seconds = self.timeout_var.get()
        self.save_config()
        threading.Thread(target=self.process_cards, daemon=True).start()

    def cancel_processing(self):
        if self.processing:
            self.cancel_requested = True
            self.cancel_btn.config(state=tk.DISABLED, text="Cancelando...")

    def on_closing(self):
        if self.processing:
            if messagebox.askyesno("Salir", "Hay un proceso en curso. ¿Cancelar y salir?"):
                self.cancel_requested = True
                self.save_config()
                self.root.destroy()
        else:
            self.save_config()
            self.root.destroy()

    def run(self):
        self.log("Card Preview Replacer v3.1 — F5 procesar, Esc cancelar")
        self.root.mainloop()


def main():
    try:
        CardProcessor().run()
    except Exception as e:
        messagebox.showerror("Error fatal", str(e))


if __name__ == "__main__":
    main()