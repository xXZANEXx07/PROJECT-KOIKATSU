import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import shutil
import threading
from collections import defaultdict


# ──────────────────────────────────────────────
#  Colores y fuentes
# ──────────────────────────────────────────────
BG       = "#1a1a2e"
PANEL    = "#16213e"
ACCENT   = "#0f3460"
BLUE     = "#4cc9f0"
GREEN    = "#06d6a0"
YELLOW   = "#ffd166"
RED      = "#ef233c"
FG       = "#e0e0e0"
FG_DIM   = "#8892a4"
FONT     = ("Consolas", 10)
FONT_B   = ("Consolas", 10, "bold")
FONT_LG  = ("Consolas", 13, "bold")
FONT_XL  = ("Consolas", 16, "bold")


class ImageClassifierApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Clasificador de Imágenes")
        self.root.geometry("780x600")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        self.folder_var   = tk.StringVar()
        self.status_var   = tk.StringVar(value="Esperando carpeta…")
        self.progress_var = tk.DoubleVar(value=0)
        self.copy_var     = tk.BooleanVar(value=False)   # False = mover, True = copiar

        self._build_ui()

    # ──────────────────────────────────────────
    #  UI
    # ──────────────────────────────────────────
    def _build_ui(self):
        # ── Título ──
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=24, pady=(20, 6))

        tk.Label(hdr, text="🗂  CLASIFICADOR DE IMÁGENES",
                 font=FONT_XL, bg=BG, fg=BLUE).pack(side="left")
        tk.Label(hdr, text="por extensión de archivo",
                 font=FONT, bg=BG, fg=FG_DIM).pack(side="left", padx=10, pady=4)

        sep = tk.Frame(self.root, bg=ACCENT, height=2)
        sep.pack(fill="x", padx=24, pady=(0, 16))

        # ── Selector de carpeta ──
        sel_frame = tk.Frame(self.root, bg=PANEL, bd=0, relief="flat")
        sel_frame.pack(fill="x", padx=24, pady=(0, 12))

        tk.Label(sel_frame, text="  Carpeta raíz:", font=FONT_B,
                 bg=PANEL, fg=FG_DIM).pack(side="left", padx=(10, 4), pady=10)

        self.folder_entry = tk.Entry(
            sel_frame, textvariable=self.folder_var,
            font=FONT, bg=ACCENT, fg=FG, relief="flat",
            insertbackground=BLUE, bd=0
        )
        self.folder_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=4)

        tk.Button(
            sel_frame, text="Examinar", font=FONT_B,
            bg=BLUE, fg=BG, activebackground=GREEN, activeforeground=BG,
            relief="flat", cursor="hand2", bd=0,
            command=self._browse_folder
        ).pack(side="left", padx=(4, 10), pady=8, ipadx=8, ipady=4)

        # ── Opciones ──
        opt_frame = tk.Frame(self.root, bg=BG)
        opt_frame.pack(fill="x", padx=24, pady=(0, 10))

        tk.Checkbutton(
            opt_frame, text="Copiar archivos (en vez de moverlos)",
            variable=self.copy_var, font=FONT,
            bg=BG, fg=FG, selectcolor=ACCENT,
            activebackground=BG, activeforeground=BLUE
        ).pack(side="left")

        # ── Botón Clasificar ──
        self.btn_run = tk.Button(
            self.root, text="▶  CLASIFICAR",
            font=FONT_LG, bg=GREEN, fg=BG,
            activebackground=BLUE, activeforeground=BG,
            relief="flat", cursor="hand2", bd=0,
            command=self._start_classification
        )
        self.btn_run.pack(pady=(4, 14), ipadx=20, ipady=8)

        # ── Progreso ──
        prog_frame = tk.Frame(self.root, bg=BG)
        prog_frame.pack(fill="x", padx=24, pady=(0, 6))

        self.status_lbl = tk.Label(
            prog_frame, textvariable=self.status_var,
            font=FONT, bg=BG, fg=FG_DIM, anchor="w"
        )
        self.status_lbl.pack(fill="x")

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Custom.Horizontal.TProgressbar",
                         troughcolor=ACCENT, background=BLUE,
                         thickness=10, bordercolor=BG, lightcolor=BLUE, darkcolor=BLUE)

        self.progress_bar = ttk.Progressbar(
            self.root, variable=self.progress_var,
            maximum=100, style="Custom.Horizontal.TProgressbar"
        )
        self.progress_bar.pack(fill="x", padx=24, pady=(0, 14))

        # ── Log ──
        log_frame = tk.Frame(self.root, bg=PANEL, bd=0)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(0, 8))

        tk.Label(log_frame, text="  Registro de operaciones",
                 font=FONT_B, bg=PANEL, fg=FG_DIM, anchor="w").pack(fill="x", pady=(6, 0))

        text_scroll = tk.Frame(log_frame, bg=PANEL)
        text_scroll.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        self.log_text = tk.Text(
            text_scroll, font=("Consolas", 9),
            bg=BG, fg=FG, relief="flat", bd=0,
            state="disabled", wrap="none",
            insertbackground=BLUE
        )
        scrollbar = tk.Scrollbar(text_scroll, command=self.log_text.yview,
                                  bg=ACCENT, troughcolor=PANEL, relief="flat")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

        # colores de etiquetas en el log
        self.log_text.tag_configure("ok",    foreground=GREEN)
        self.log_text.tag_configure("warn",  foreground=YELLOW)
        self.log_text.tag_configure("err",   foreground=RED)
        self.log_text.tag_configure("info",  foreground=BLUE)
        self.log_text.tag_configure("dim",   foreground=FG_DIM)

        # ── Footer ──
        tk.Label(self.root, text="Se crea PNG/, JPG/, etc. dentro de cada carpeta que contenga imágenes.",
                 font=("Consolas", 8), bg=BG, fg=FG_DIM).pack(pady=(0, 8))

    # ──────────────────────────────────────────
    #  Helpers UI
    # ──────────────────────────────────────────
    def _browse_folder(self):
        path = filedialog.askdirectory(title="Selecciona la carpeta raíz")
        if path:
            self.folder_var.set(path)
            self._log(f"Carpeta seleccionada: {path}", "info")

    def _log(self, msg: str, tag: str = ""):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_status(self, msg: str):
        self.status_var.set(msg)

    def _set_progress(self, val: float):
        self.progress_var.set(val)

    # ──────────────────────────────────────────
    #  Lógica de clasificación
    # ──────────────────────────────────────────
    def _start_classification(self):
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("Sin carpeta", "Por favor selecciona una carpeta primero.")
            return
        if not os.path.isdir(folder):
            messagebox.showerror("Error", "La ruta seleccionada no existe.")
            return

        self.btn_run.configure(state="disabled", bg=FG_DIM)
        self._log("─" * 60, "dim")
        self._log("Iniciando clasificación…", "info")

        thread = threading.Thread(
            target=self._classify_thread,
            args=(folder, self.copy_var.get()),
            daemon=True
        )
        thread.start()

    def _classify_thread(self, root_folder: str, copy_mode: bool):
        try:
            IMAGE_EXTS = {
                ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
                ".webp", ".svg", ".ico", ".heic", ".heif", ".raw", ".cr2",
                ".nef", ".arw", ".dng", ".psd", ".xcf", ".avif"
            }

            # 1. Escanear: agrupar imágenes por (carpeta_contenedora, extensión)
            # Estructura: { dirpath: { ext: [filepath, ...] } }
            tree = defaultdict(lambda: defaultdict(list))
            all_files = []

            self.root.after(0, self._set_status, "Escaneando archivos…")

            for dirpath, dirnames, filenames in os.walk(root_folder):
                # Saltar carpetas de tipo que ya creamos (nombre en mayúsculas sin punto)
                dirnames[:] = [
                    d for d in dirnames
                    if not (d.upper() == d and len(d) <= 5 and "." not in d)
                ]
                for fname in filenames:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in IMAGE_EXTS:
                        full = os.path.join(dirpath, fname)
                        tree[dirpath][ext].append(full)
                        all_files.append(full)

            total = len(all_files)
            if total == 0:
                self.root.after(0, self._log, "No se encontraron imágenes.", "warn")
                self.root.after(0, self._set_status, "Sin imágenes encontradas.")
                self.root.after(0, self._reset_btn)
                return

            unique_exts = {ext for exts in tree.values() for ext in exts}
            self.root.after(0, self._log,
                            f"Encontradas {total} imagen(es) · "
                            f"{len(tree)} carpeta(s) · "
                            f"{len(unique_exts)} tipo(s).", "info")

            # 2. Mover/copiar: crear subcarpeta de tipo DENTRO de cada carpeta original
            action      = shutil.copy2 if copy_mode else shutil.move
            action_name = "Copiado" if copy_mode else "Movido"
            processed   = 0
            errors      = 0

            for dirpath, ext_map in sorted(tree.items()):
                rel = os.path.relpath(dirpath, root_folder)
                self.root.after(0, self._log, f"\n📂  {rel}", "info")

                for ext, paths in sorted(ext_map.items()):
                    type_name   = ext.lstrip(".").upper()          # "PNG", "JPG"…
                    dest_folder = os.path.join(dirpath, type_name)
                    os.makedirs(dest_folder, exist_ok=True)
                    self.root.after(0, self._log,
                                    f"  📁 {type_name}/  ({len(paths)} archivo[s])", "info")

                    for src in paths:
                        fname = os.path.basename(src)
                        dest  = os.path.join(dest_folder, fname)

                        # Resolver colisiones
                        if os.path.exists(dest):
                            base, ex = os.path.splitext(fname)
                            counter  = 1
                            while os.path.exists(dest):
                                dest = os.path.join(dest_folder, f"{base}_{counter}{ex}")
                                counter += 1

                        try:
                            action(src, dest)
                            processed += 1
                            self.root.after(0, self._log,
                                            f"    {action_name}: {fname}", "ok")
                        except Exception as e:
                            errors += 1
                            self.root.after(0, self._log,
                                            f"    ERROR con {fname}: {e}", "err")

                        pct = (processed + errors) / total * 100
                        self.root.after(0, self._set_progress, pct)
                        self.root.after(0, self._set_status,
                                        f"Procesando… {processed + errors}/{total}")

            # 3. Resumen
            self.root.after(0, self._log, "─" * 60, "dim")
            self.root.after(0, self._log,
                            f"✔  Completado: {processed} procesado(s), {errors} error(es).", "ok")
            self.root.after(0, self._set_status,
                            f"✔  Listo — {processed} archivo(s) procesado(s).")
            self.root.after(0, self._set_progress, 100)

            if errors == 0:
                self.root.after(0, messagebox.showinfo,
                                "Completado",
                                f"Clasificación terminada.\n{processed} imagen(es) procesada(s) sin errores.")
            else:
                self.root.after(0, messagebox.showwarning,
                                "Completado con errores",
                                f"{processed} imagen(es) procesada(s).\n{errors} error(es). Revisa el registro.")

        except Exception as e:
            self.root.after(0, self._log, f"Error inesperado: {e}", "err")
            self.root.after(0, self._set_status, "Error inesperado.")
        finally:
            self.root.after(0, self._reset_btn)

    def _reset_btn(self):
        self.btn_run.configure(state="normal", bg=GREEN)


# ──────────────────────────────────────────────
#  Entrada principal
# ──────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = ImageClassifierApp(root)
    root.mainloop()