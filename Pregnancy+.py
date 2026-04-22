"""
koikatsu_pregnancy_reset.py
----------------------------
Interfaz gráfica para resetear el inflationSize de KK_PregnancyPlus
en cartas PNG de Koikatu.

Requiere:
    pip install kkloader
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import glob


# ─────────────────────────────────────────────────────────────
# Lógica de acceso a KK_PregnancyPlus
# ─────────────────────────────────────────────────────────────

def get_inflation(k):
    """
    Devuelve el inflationSize actual o None si no existe.
    Estructura: KKEx["KK_PregnancyPlus"] = [flag, {inflationSize: x, ...}]
    """
    try:
        data = k["KKEx"].data.get("KK_PregnancyPlus")
        if data and isinstance(data, list) and len(data) >= 2:
            inner = data[1]
            if isinstance(inner, dict):
                return inner.get("inflationSize")
    except Exception:
        pass
    return None


def set_inflation(k, value=0.0):
    """Pone inflationSize al valor indicado y escribe de vuelta."""
    data = k["KKEx"].data["KK_PregnancyPlus"]
    data[1]["inflationSize"] = value
    k["KKEx"]["KK_PregnancyPlus"] = data


# ─────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Koikatsu – Pregnancy+ Resetter")
        self.geometry("820x700")
        self.resizable(True, True)
        self.configure(bg="#1e1e2e")

        self.C = {
            "bg":      "#1e1e2e",
            "panel":   "#2a2a3e",
            "accent":  "#7c6af7",
            "accent2": "#f28fad",
            "fg":      "#cdd6f4",
            "fg2":     "#a6adc8",
            "green":   "#a6e3a1",
            "red":     "#f38ba8",
            "yellow":  "#f9e2af",
            "entry":   "#313244",
        }

        self._check_kkloader()
        self._build_ui()

    def _check_kkloader(self):
        try:
            import kkloader  # noqa
            self.kkloader_ok = True
        except ImportError:
            self.kkloader_ok = False

    # ── UI ──────────────────────────────────────────────────

    def _build_ui(self):
        C = self.C

        tk.Label(self, text="✦  Koikatsu Pregnancy+ Resetter  ✦",
                 bg=C["bg"], fg=C["accent"], font=("Segoe UI", 15, "bold")
                 ).pack(pady=(18, 2))

        tk.Label(self, text="KKEx → KK_PregnancyPlus → inflationSize",
                 bg=C["bg"], fg=C["fg2"], font=("Segoe UI", 9)
                 ).pack(pady=(0, 6))

        if not self.kkloader_ok:
            tk.Label(self,
                     text="⚠  kkloader no instalado  →  pip install kkloader",
                     bg=C["bg"], fg=C["red"], font=("Segoe UI", 10, "bold")
                     ).pack(pady=4)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=16, pady=10)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook",      background=C["bg"], borderwidth=0)
        style.configure("TNotebook.Tab",  background=C["panel"], foreground=C["fg2"],
                        padding=[14, 6],  font=("Segoe UI", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", C["accent"])],
                  foreground=[("selected", "#ffffff")])
        style.configure("green.Horizontal.TProgressbar",
                        troughcolor=C["panel"], background=C["green"])

        tab1 = tk.Frame(nb, bg=C["bg"])
        nb.add(tab1, text="🔍  Explorar carta")
        self._build_tab_explorer(tab1)

        tab2 = tk.Frame(nb, bg=C["bg"])
        nb.add(tab2, text="♻  Reset masivo")
        self._build_tab_reset(tab2)

    # ── Pestaña Explorador ───────────────────────────────────

    def _build_tab_explorer(self, parent):
        C = self.C

        top = tk.Frame(parent, bg=C["bg"])
        top.pack(fill="x", padx=16, pady=12)

        tk.Label(top, text="Carta PNG:", bg=C["bg"],
                 fg=C["fg"], font=("Segoe UI", 10)
                 ).grid(row=0, column=0, sticky="w")

        self.exp_path = tk.StringVar()
        tk.Entry(top, textvariable=self.exp_path, width=52,
                 bg=C["entry"], fg=C["fg"], insertbackground=C["fg"],
                 relief="flat", font=("Segoe UI", 10)
                 ).grid(row=0, column=1, padx=8)

        tk.Button(top, text="Seleccionar…",
                  bg=C["accent"], fg="#fff", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  command=self._exp_browse
                  ).grid(row=0, column=2)

        tk.Button(top, text="▶  Analizar",
                  bg=C["accent2"], fg="#1e1e2e", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  command=self._exp_run
                  ).grid(row=0, column=3, padx=(8, 0))

        # Panel de resultado
        res_frame = tk.Frame(parent, bg=C["panel"])
        res_frame.pack(fill="x", padx=16, pady=(0, 6))

        self.exp_result = tk.Label(
            res_frame, text="Selecciona una carta para analizarla.",
            bg=C["panel"], fg=C["fg2"], font=("Segoe UI", 11), pady=10
        )
        self.exp_result.pack()

        # Botón reset carta individual
        self.exp_reset_btn = tk.Button(
            parent, text="⬇  Resetear esta carta  (inflationSize → 0)",
            bg=C["red"], fg="#fff", relief="flat",
            font=("Segoe UI", 10, "bold"), cursor="hand2",
            command=self._exp_reset_single, state="disabled"
        )
        self.exp_reset_btn.pack(padx=16, pady=(0, 8), fill="x")

        # Log
        self.exp_log = scrolledtext.ScrolledText(
            parent, bg=C["panel"], fg=C["fg"], font=("Consolas", 10),
            relief="flat", wrap="word", state="disabled"
        )
        self.exp_log.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        for tag, fg, bold in [
            ("header", C["accent"],  True),
            ("found",  C["green"],   True),
            ("info",   C["fg2"],     False),
            ("warn",   C["yellow"],  False),
            ("error",  C["red"],     False),
            ("value",  C["accent2"], False),
        ]:
            self.exp_log.tag_config(
                tag, foreground=fg,
                font=("Consolas", 10, "bold" if bold else "normal")
            )

    def _exp_browse(self):
        path = filedialog.askopenfilename(
            title="Selecciona una carta PNG",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")]
        )
        if path:
            self.exp_path.set(path)

    def _exp_run(self):
        if not self.kkloader_ok:
            messagebox.showerror("Error", "Instala kkloader:\npip install kkloader")
            return
        path = self.exp_path.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning("Aviso", "Selecciona un archivo PNG válido.")
            return
        threading.Thread(target=self._exp_analyze, args=(path,), daemon=True).start()

    def _exp_analyze(self, path):
        from kkloader import KoikatuCharaData

        self._exp_clear()
        self.exp_reset_btn.configure(state="disabled")
        self.exp_result.configure(text="Analizando...", fg=self.C["fg2"])
        self._current_path = None

        self._exp_write(f"Archivo : {path}\n", "header")

        try:
            k = KoikatuCharaData.load(path)
        except Exception as e:
            self._exp_write(f"Error al cargar: {e}\n", "error")
            self.exp_result.configure(text="Error al cargar la carta.", fg=self.C["red"])
            return

        # Nombre del personaje
        try:
            nombre = k["Parameter"]["firstname"] + " " + k["Parameter"]["lastname"]
        except Exception:
            nombre = os.path.basename(path)

        self._exp_write(f"Nombre  : {nombre}\n", "info")
        self._exp_write(f"Bloques : {k.blockdata}\n\n", "info")

        inflation = get_inflation(k)

        if inflation is None:
            self._exp_write("Esta carta no tiene datos de KK_PregnancyPlus.\n", "warn")
            self.exp_result.configure(
                text="Sin datos de Pregnancy+",
                fg=self.C["fg2"]
            )
        elif inflation > 0:
            self._exp_write("▸ KKEx → KK_PregnancyPlus → inflationSize\n", "found")
            self._exp_write(f"  Valor actual: ", "info")
            self._exp_write(f"{inflation}\n", "value")
            self._exp_write("\n⚠  Esta carta tiene Pregnancy+ activo.\n", "warn")
            self.exp_result.configure(
                text=f"⚠  inflationSize = {inflation}   (Pregnancy+ activo)",
                fg=self.C["yellow"]
            )
            self.exp_reset_btn.configure(state="normal")
            self._current_path = path
        else:
            self._exp_write("▸ KKEx → KK_PregnancyPlus → inflationSize\n", "found")
            self._exp_write(f"  Valor actual: {inflation}  (ya está en 0)\n", "info")
            self.exp_result.configure(
                text=f"✔  inflationSize = {inflation}   (ya está en 0)",
                fg=self.C["green"]
            )

    def _exp_reset_single(self):
        path = getattr(self, "_current_path", None)
        if not path:
            return
        from kkloader import KoikatuCharaData
        try:
            k = KoikatuCharaData.load(path)
            set_inflation(k, 0.0)
            k.save(path)
            self._exp_write(f"\n✔  Guardado con inflationSize = 0:\n   {path}\n", "found")
            self.exp_result.configure(
                text="✔  inflationSize = 0   (guardado correctamente)",
                fg=self.C["green"]
            )
            self.exp_reset_btn.configure(state="disabled")
            self._current_path = None
        except Exception as e:
            self._exp_write(f"\nError al guardar: {e}\n", "error")

    def _exp_write(self, text, tag="info"):
        self.exp_log.configure(state="normal")
        self.exp_log.insert("end", text, tag)
        self.exp_log.see("end")
        self.exp_log.configure(state="disabled")

    def _exp_clear(self):
        self.exp_log.configure(state="normal")
        self.exp_log.delete("1.0", "end")
        self.exp_log.configure(state="disabled")

    # ── Pestaña Reset masivo ─────────────────────────────────

    def _build_tab_reset(self, parent):
        C = self.C

        cfg = tk.LabelFrame(parent, text="  Configuración  ",
                            bg=C["panel"], fg=C["accent"],
                            font=("Segoe UI", 10, "bold"),
                            relief="flat", bd=2)
        cfg.pack(fill="x", padx=16, pady=12)

        def lbl(text, r):
            tk.Label(cfg, text=text, bg=C["panel"], fg=C["fg"],
                     font=("Segoe UI", 10), width=22, anchor="w"
                     ).grid(row=r, column=0, padx=10, pady=6, sticky="w")

        def ent(var, r):
            e = tk.Entry(cfg, textvariable=var, width=44,
                         bg=C["entry"], fg=C["fg"], insertbackground=C["fg"],
                         relief="flat", font=("Segoe UI", 10))
            e.grid(row=r, column=1, padx=6)
            return e

        def browse_btn(r, cmd):
            tk.Button(cfg, text="…", bg=C["accent"], fg="#fff",
                      relief="flat", font=("Segoe UI", 10, "bold"),
                      cursor="hand2", command=cmd, width=3
                      ).grid(row=r, column=2, padx=(0, 10))

        self.rst_input      = tk.StringVar()
        self.rst_output     = tk.StringVar()
        self.rst_inplace    = tk.BooleanVar(value=False)
        self.rst_min        = tk.DoubleVar(value=1.0)
        self.rst_recursive  = tk.BooleanVar(value=False)

        lbl("Carpeta de cartas:", 0);  ent(self.rst_input, 0);  browse_btn(0, self._rst_browse_in)
        lbl("Carpeta de salida:", 1);  self.out_ent = ent(self.rst_output, 1); browse_btn(1, self._rst_browse_out)

        tk.Checkbutton(
            cfg,
            text="Sobreescribir originales  (ignorar carpeta de salida)",
            variable=self.rst_inplace,
            bg=C["panel"], fg=C["yellow"],
            selectcolor=C["entry"], activebackground=C["panel"],
            font=("Segoe UI", 9), command=self._toggle_out
        ).grid(row=2, column=0, columnspan=3, padx=10, pady=(0, 4), sticky="w")

        tk.Checkbutton(
            cfg,
            text="Buscar también en subcarpetas  (recursivo)",
            variable=self.rst_recursive,
            bg=C["panel"], fg=C["accent2"],
            selectcolor=C["entry"], activebackground=C["panel"],
            font=("Segoe UI", 9)
        ).grid(row=3, column=0, columnspan=3, padx=10, pady=(0, 4), sticky="w")

        lbl("Resetear si inflationSize ≥", 4)
        tk.Spinbox(cfg, from_=0.0, to=200.0, increment=0.5,
                   textvariable=self.rst_min, width=8,
                   bg=C["entry"], fg=C["fg"], insertbackground=C["fg"],
                   relief="flat", font=("Segoe UI", 10),
                   buttonbackground=C["accent"]
                   ).grid(row=4, column=1, sticky="w", padx=6, pady=(0, 10))

        # Contadores
        counts = tk.Frame(parent, bg=C["bg"])
        counts.pack(fill="x", padx=16, pady=(0, 6))

        def counter(label, fg, col):
            f = tk.Frame(counts, bg=C["panel"])
            f.grid(row=0, column=col, padx=4, sticky="ew")
            counts.columnconfigure(col, weight=1)
            tk.Label(f, text=label, bg=C["panel"], fg=C["fg2"],
                     font=("Segoe UI", 8)).pack(pady=(4, 0))
            v = tk.StringVar(value="0")
            tk.Label(f, textvariable=v, bg=C["panel"], fg=fg,
                     font=("Segoe UI", 16, "bold")).pack(pady=(0, 4))
            return v

        self.cnt_mod  = counter("Modificadas", C["green"], 0)
        self.cnt_skip = counter("Sin cambios", C["fg2"],   1)
        self.cnt_err  = counter("Errores",     C["red"],   2)

        # Barra de progreso
        self.rst_progress = ttk.Progressbar(
            parent, style="green.Horizontal.TProgressbar", mode="determinate"
        )
        self.rst_progress.pack(fill="x", padx=16, pady=(0, 6))

        # Botón iniciar
        self.rst_btn = tk.Button(
            parent, text="▶  Iniciar Reset masivo",
            bg=C["accent2"], fg="#1e1e2e", relief="flat",
            font=("Segoe UI", 11, "bold"), cursor="hand2",
            pady=6, command=self._rst_run
        )
        self.rst_btn.pack(padx=16, pady=(0, 8), fill="x")

        # Log
        self.rst_log = scrolledtext.ScrolledText(
            parent, bg=C["panel"], fg=C["fg"], font=("Consolas", 10),
            relief="flat", wrap="word", state="disabled", height=10
        )
        self.rst_log.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        for tag, fg, bold in [
            ("header", C["accent"],  True),
            ("found",  C["green"],   True),
            ("info",   C["fg2"],     False),
            ("mod",    C["accent2"], False),
            ("warn",   C["yellow"],  False),
            ("error",  C["red"],     False),
        ]:
            self.rst_log.tag_config(
                tag, foreground=fg,
                font=("Consolas", 10, "bold" if bold else "normal")
            )

    def _toggle_out(self):
        if self.rst_inplace.get():
            self.out_ent.configure(state="disabled")
        else:
            self.out_ent.configure(state="normal")

    def _rst_browse_in(self):
        p = filedialog.askdirectory(title="Carpeta de cartas")
        if p:
            self.rst_input.set(p)

    def _rst_browse_out(self):
        p = filedialog.askdirectory(title="Carpeta de salida")
        if p:
            self.rst_output.set(p)

    def _rst_run(self):
        if not self.kkloader_ok:
            messagebox.showerror("Error", "Instala kkloader:\npip install kkloader")
            return

        input_dir  = self.rst_input.get().strip()
        output_dir = self.rst_output.get().strip()
        inplace    = self.rst_inplace.get()
        min_val    = self.rst_min.get()

        if not input_dir or not os.path.isdir(input_dir):
            messagebox.showwarning("Aviso", "Selecciona una carpeta de cartas válida.")
            return
        if not inplace and not output_dir:
            messagebox.showwarning("Aviso", "Selecciona carpeta de salida o activa 'Sobreescribir originales'.")
            return

        if not messagebox.askyesno(
            "Confirmar",
            f"Carpeta: {input_dir}\n\n"
            f"Se pondrá inflationSize = 0 en todas las cartas\n"
            f"donde inflationSize ≥ {min_val}\n\n"
            f"{'⚠ Se sobreescribirán los ORIGINALES.' if inplace else f'Salida: {output_dir}'}\n\n"
            "¿Continuar?"
        ):
            return

        self.rst_btn.configure(state="disabled")
        self.cnt_mod.set("0")
        self.cnt_skip.set("0")
        self.cnt_err.set("0")

        recursive = self.rst_recursive.get()

        threading.Thread(
            target=self._rst_process,
            args=(input_dir, output_dir, inplace, min_val, recursive),
            daemon=True
        ).start()

    def _rst_process(self, input_dir, output_dir, inplace, min_val, recursive):
        from kkloader import KoikatuCharaData

        if not inplace:
            os.makedirs(output_dir, exist_ok=True)

        if recursive:
            cartas = glob.glob(os.path.join(input_dir, "**", "*.png"), recursive=True)
        else:
            cartas = glob.glob(os.path.join(input_dir, "*.png"))

        total = len(cartas)

        self._rst_clear()
        modo_txt = "(incluyendo subcarpetas)" if recursive else "(solo carpeta raíz)"
        self._rst_write(f"Procesando {total} cartas {modo_txt}\n", "header")
        self._rst_write(f"Carpeta: {input_dir}\n\n", "info")
        self.rst_progress["maximum"] = max(total, 1)
        self.rst_progress["value"]   = 0

        mod = skip = err = 0

        for i, filepath in enumerate(cartas, 1):
            nombre = os.path.basename(filepath)
            try:
                k = KoikatuCharaData.load(filepath)
                inflation = get_inflation(k)

                if inflation is None:
                    skip += 1
                elif inflation >= min_val:
                    # Mostrar ruta relativa si es recursivo para más claridad
                    rel = os.path.relpath(filepath, input_dir)
                    self._rst_write(f"  ✔  {rel}\n     inflationSize: ", "found")
                    self._rst_write(f"{inflation}", "mod")
                    self._rst_write("  →  0\n", "found")
                    set_inflation(k, 0.0)
                    if inplace:
                        dest = filepath
                    else:
                        # Preservar estructura de subcarpetas en la salida
                        rel_path = os.path.relpath(filepath, input_dir)
                        dest = os.path.join(output_dir, rel_path)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                    k.save(dest)
                    mod += 1
                else:
                    skip += 1

            except Exception as e:
                self._rst_write(f"  ✘  {nombre}: {e}\n", "error")
                err += 1

            self.rst_progress["value"] = i
            self.cnt_mod.set(str(mod))
            self.cnt_skip.set(str(skip))
            self.cnt_err.set(str(err))

        self._rst_write(f"\n{'═'*52}\n", "header")
        self._rst_write(f"  Modificadas : {mod}\n", "found")
        self._rst_write(f"  Sin cambios : {skip}\n", "info")
        self._rst_write(f"  Errores     : {err}\n", "error" if err else "info")
        if not inplace:
            self._rst_write(f"  Guardadas en: {output_dir}\n", "info")
        self._rst_write(f"{'═'*52}\n", "header")

        self.rst_btn.configure(state="normal")

    def _rst_write(self, text, tag="info"):
        self.rst_log.configure(state="normal")
        self.rst_log.insert("end", text, tag)
        self.rst_log.see("end")
        self.rst_log.configure(state="disabled")

    def _rst_clear(self):
        self.rst_log.configure(state="normal")
        self.rst_log.delete("1.0", "end")
        self.rst_log.configure(state="disabled")


# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()