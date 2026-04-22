import os
import re
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path


# ─────────────────────────────────────────────
#  Utilidades
# ─────────────────────────────────────────────

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}

def get_largest_image(folder: Path):
    """Devuelve (Path, tamaño_bytes) de la imagen más grande en la carpeta,
    o (None, 0) si no hay imágenes."""
    best = None
    best_size = -1
    for f in folder.iterdir():
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
            size = f.stat().st_size
            if size > best_size:
                best_size = size
                best = f
    return best, max(best_size, 0)


def strip_existing_prefix(name: str) -> str:
    """Elimina prefijos numéricos existentes como '1_', '23_', etc."""
    return re.sub(r"^\d+_", "", name)


def format_size(size_bytes: int) -> str:
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


# ─────────────────────────────────────────────
#  Lógica principal
# ─────────────────────────────────────────────

def scan_and_sort(root: Path):
    """Escanea subcarpetas y devuelve lista ordenada (mayor a menor tamaño):
    [(carpeta_path, imagen_path_o_None, tamaño_bytes), ...]"""
    entries = []
    for item in root.iterdir():
        if item.is_dir():
            img, size = get_largest_image(item)
            entries.append((item, img, size))
    entries.sort(key=lambda x: x[2], reverse=True)
    return entries


def rename_folders(root: Path, entries, log_callback=None):
    """Renombra las carpetas añadiendo el prefijo numérico."""
    # Primero renombramos a nombres temporales para evitar colisiones
    temp_map = {}
    for i, (folder, _, _) in enumerate(entries, start=1):
        clean_name = strip_existing_prefix(folder.name)
        temp_name = root / f"__temp_{i}_{clean_name}"
        folder.rename(temp_name)
        temp_map[i] = (temp_name, clean_name)

    # Luego renombramos al nombre final
    for i, (temp_path, clean_name) in temp_map.items():
        final_name = root / f"{i}_{clean_name}"
        temp_path.rename(final_name)
        if log_callback:
            log_callback(f"  {i}_ {clean_name}")


# ─────────────────────────────────────────────
#  Interfaz gráfica
# ─────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ordenar Cartas Koikatsu")
        self.resizable(False, False)
        self.configure(bg="#1e1e2e")
        self._build_ui()

    # ── construcción de widgets ──────────────
    def _build_ui(self):
        PAD = 12
        BG = "#1e1e2e"
        FG = "#cdd6f4"
        ACCENT = "#cba6f7"
        BTN_BG = "#313244"
        ENTRY_BG = "#181825"

        # Título
        tk.Label(self, text="🃏  Ordenar Cartas Koikatsu", font=("Segoe UI", 14, "bold"),
                 bg=BG, fg=ACCENT).grid(row=0, column=0, columnspan=3,
                                        padx=PAD*2, pady=(PAD*2, PAD))

        # Selector de carpeta
        tk.Label(self, text="Carpeta raíz:", bg=BG, fg=FG,
                 font=("Segoe UI", 10)).grid(row=1, column=0, padx=(PAD*2, 4), sticky="w")

        self.folder_var = tk.StringVar()
        tk.Entry(self, textvariable=self.folder_var, width=42,
                 bg=ENTRY_BG, fg=FG, insertbackground=FG,
                 relief="flat", font=("Segoe UI", 10)).grid(row=1, column=1, padx=4)

        tk.Button(self, text="📂 Examinar", command=self._browse,
                  bg=BTN_BG, fg=FG, activebackground=ACCENT, relief="flat",
                  font=("Segoe UI", 9), cursor="hand2").grid(row=1, column=2, padx=(4, PAD*2))

        # Botones de acción
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.grid(row=2, column=0, columnspan=3, pady=PAD)

        tk.Button(btn_frame, text="🔍  Vista previa", command=self._preview,
                  bg=BTN_BG, fg=FG, activebackground=ACCENT, relief="flat",
                  font=("Segoe UI", 10), width=16, cursor="hand2").pack(side="left", padx=6)

        tk.Button(btn_frame, text="✅  Renombrar", command=self._rename,
                  bg="#a6e3a1", fg="#1e1e2e", activebackground="#94e2d5", relief="flat",
                  font=("Segoe UI", 10, "bold"), width=16, cursor="hand2").pack(side="left", padx=6)

        # Tabla de vista previa
        cols = ("#", "Carpeta", "Imagen más grande", "Tamaño")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=14)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
                        background="#181825", foreground=FG,
                        fieldbackground="#181825", rowheight=22,
                        font=("Segoe UI", 9))
        style.configure("Treeview.Heading",
                        background="#313244", foreground=ACCENT,
                        font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", "#45475a")])

        widths = [40, 220, 200, 90]
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor="center" if col == "#" else "w")

        self.tree.grid(row=3, column=0, columnspan=3, padx=PAD*2, pady=(0, PAD))

        # Scrollbar
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.grid(row=3, column=3, sticky="ns", pady=(0, PAD))

        # Barra de estado
        self.status_var = tk.StringVar(value="Selecciona una carpeta para comenzar.")
        tk.Label(self, textvariable=self.status_var, bg=BG, fg="#6c7086",
                 font=("Segoe UI", 9), anchor="w").grid(
            row=4, column=0, columnspan=3, padx=PAD*2, pady=(0, PAD*2), sticky="w")

    # ── acciones ────────────────────────────
    def _browse(self):
        folder = filedialog.askdirectory(title="Selecciona la carpeta raíz")
        if folder:
            self.folder_var.set(folder)
            self._preview()

    def _get_root(self) -> Path | None:
        raw = self.folder_var.get().strip()
        if not raw:
            messagebox.showwarning("Sin carpeta", "Por favor selecciona una carpeta primero.")
            return None
        p = Path(raw)
        if not p.is_dir():
            messagebox.showerror("Error", f"La ruta no existe:\n{raw}")
            return None
        return p

    def _preview(self):
        root = self._get_root()
        if not root:
            return

        entries = scan_and_sort(root)
        self.tree.delete(*self.tree.get_children())

        if not entries:
            self.status_var.set("⚠️  No se encontraron subcarpetas.")
            return

        no_img = 0
        for i, (folder, img, size) in enumerate(entries, start=1):
            img_name = img.name if img else "— sin imagen —"
            size_str = format_size(size) if img else "—"
            if not img:
                no_img += 1
            self.tree.insert("", "end", values=(i, folder.name, img_name, size_str))

        msg = f"✔  {len(entries)} carpetas encontradas."
        if no_img:
            msg += f"  ⚠️  {no_img} sin imágenes (quedarán al final)."
        self.status_var.set(msg)

    def _rename(self):
        root = self._get_root()
        if not root:
            return

        entries = scan_and_sort(root)
        if not entries:
            messagebox.showinfo("Sin carpetas", "No hay subcarpetas para renombrar.")
            return

        confirm = messagebox.askyesno(
            "Confirmar",
            f"Se renombrarán {len(entries)} carpetas en:\n{root}\n\n"
            "Las carpetas quedarán como: 1_NombreOriginal, 2_NombreOriginal …\n\n"
            "¿Continuar?"
        )
        if not confirm:
            return

        try:
            rename_folders(root, entries)
            self.status_var.set(f"✅  {len(entries)} carpetas renombradas correctamente.")
            self._preview()          # refrescar tabla
            messagebox.showinfo("¡Listo!", f"Se renombraron {len(entries)} carpetas correctamente.")
        except Exception as e:
            messagebox.showerror("Error al renombrar", str(e))
            self.status_var.set("❌  Error durante el renombrado.")


# ─────────────────────────────────────────────
#  Punto de entrada
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()