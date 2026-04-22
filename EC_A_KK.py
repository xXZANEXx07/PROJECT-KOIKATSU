import os
import queue
import shutil
import copy
import threading
from pathlib import Path
from typing import Tuple, List
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from kkloader.EmocreCharaData import EmocreCharaData
from kkloader.KoikatuCharaData import Coordinate, KoikatuCharaData


# ---------------------------------------------------------------------------
# Mensajes que el worker envía al hilo principal vía queue
# ---------------------------------------------------------------------------
class _Msg:
    """Mensaje genérico worker → GUI."""
    __slots__ = ("kind", "payload")

    def __init__(self, kind: str, **payload):
        self.kind = kind
        self.payload = payload


class EmocreConverterGUI:
    """Interfaz gráfica para convertir personajes de Emotion Creators a Koikatsu."""

    _POLL_MS = 50  # intervalo de sondeo de la queue (ms)

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Convertidor Emocre → Koikatsu")
        self.root.geometry("800x650")
        self.root.resizable(True, True)

        # Estado de conversión
        self._cancel_event = threading.Event()
        self._gui_queue: queue.Queue[_Msg] = queue.Queue()
        self._conversion_thread: threading.Thread | None = None

        # Variables tkinter
        self.selected_folder = tk.StringVar()

        self._setup_styles()
        self._setup_ui()

    # ------------------------------------------------------------------
    # Configuración UI
    # ------------------------------------------------------------------

    def _setup_styles(self):
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Arial", 16, "bold"))
        style.configure("Accent.TButton", font=("Arial", 10, "bold"))

    def _setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.grid(row=0, column=0, sticky="nsew")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1)

        ttk.Label(
            main_frame,
            text="Convertidor Emocre → Koikatsu",
            style="Title.TLabel",
        ).grid(row=0, column=0, pady=(0, 20), sticky="w")

        ttk.Label(
            main_frame,
            text="Convierte personajes de Emotion Creators a formato Koikatsu en lote",
            foreground="gray",
        ).grid(row=1, column=0, pady=(0, 15), sticky="w")

        self._create_folder_selection(main_frame)
        self._create_action_buttons(main_frame)
        self._create_progress_section(main_frame)
        self._create_stats_section(main_frame)

    def _create_folder_selection(self, parent):
        folder_frame = ttk.LabelFrame(parent, text="Carpeta de origen", padding="10")
        folder_frame.grid(row=2, column=0, sticky="ew", pady=(0, 15))
        folder_frame.columnconfigure(0, weight=1)

        entry_frame = ttk.Frame(folder_frame)
        entry_frame.grid(row=0, column=0, sticky="ew")
        entry_frame.columnconfigure(0, weight=1)

        self.folder_entry = ttk.Entry(
            entry_frame, textvariable=self.selected_folder, state="readonly"
        )
        self.folder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.browse_button = ttk.Button(
            entry_frame, text="📁 Explorar", command=self._browse_folder
        )
        self.browse_button.grid(row=0, column=1)

        ttk.Label(
            folder_frame,
            text="Selecciona la carpeta con archivos PNG/JPG de Emotion Creators",
            foreground="gray",
            font=("Arial", 8),
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))

    def _create_action_buttons(self, parent):
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=3, column=0, pady=10)

        self.convert_button = ttk.Button(
            button_frame,
            text="🚀 Iniciar Conversión",
            command=self._start_conversion,
            style="Accent.TButton",
            width=20,
        )
        self.convert_button.pack(side="left", padx=5)

        self.cancel_button = ttk.Button(
            button_frame,
            text="⏹️ Cancelar",
            command=self._cancel_conversion,
            state="disabled",
            width=15,
        )
        self.cancel_button.pack(side="left", padx=5)

        self.clear_button = ttk.Button(
            button_frame,
            text="🗑️ Limpiar Log",
            command=self._clear_log,
            width=15,
        )
        self.clear_button.pack(side="left", padx=5)

    def _create_progress_section(self, parent):
        progress_frame = ttk.LabelFrame(parent, text="Progreso y Registro", padding="10")
        progress_frame.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)
        progress_frame.rowconfigure(2, weight=1)

        self.progress_var = tk.StringVar(value="Listo para iniciar")
        ttk.Label(progress_frame, textvariable=self.progress_var).grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )

        self.progress_bar = ttk.Progressbar(
            progress_frame, mode="determinate", length=400
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        log_frame = ttk.Frame(progress_frame)
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=12, wrap="word", font=("Consolas", 9)
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        self.log_text.tag_config("success", foreground="#28a745")
        self.log_text.tag_config("error",   foreground="#dc3545")
        self.log_text.tag_config("info",    foreground="#007bff")
        self.log_text.tag_config("warning", foreground="#ffc107")

    def _create_stats_section(self, parent):
        stats_frame = ttk.LabelFrame(parent, text="Estadísticas", padding="10")
        stats_frame.grid(row=5, column=0, sticky="ew")

        self.stats_var = tk.StringVar(value="✅ Exitosos: 0  |  ❌ Errores: 0  |  📊 Total: 0")
        ttk.Label(stats_frame, textvariable=self.stats_var, font=("Arial", 10)).pack()

    # ------------------------------------------------------------------
    # Helpers GUI (sólo llamar desde el hilo principal)
    # ------------------------------------------------------------------

    def _log(self, message: str, tag: str | None = None):
        """Escribe una línea en el log. Debe ejecutarse en el hilo principal."""
        self.log_text.insert("end", message + "\n", tag or "")
        self.log_text.see("end")

    def _clear_log(self):
        self.log_text.delete("1.0", "end")
        self._log("Log limpiado", "info")

    def _browse_folder(self):
        folder = filedialog.askdirectory(
            title="Seleccionar carpeta con archivos de Emotion Creators"
        )
        if folder:
            self.selected_folder.set(folder)
            self._log(f"Carpeta seleccionada: {folder}", "info")

    def _set_busy(self, busy: bool):
        """Habilita/deshabilita controles según si hay una conversión en curso."""
        if busy:
            self.convert_button.configure(state="disabled")
            self.cancel_button.configure(state="normal")
            self.browse_button.configure(state="disabled")
            self.clear_button.configure(state="disabled")
        else:
            self.convert_button.configure(state="normal")
            self.cancel_button.configure(state="disabled")
            self.browse_button.configure(state="normal")
            self.clear_button.configure(state="normal")

    # ------------------------------------------------------------------
    # Sondeo de la queue (hilo principal)
    # ------------------------------------------------------------------

    def _poll_queue(self):
        """Procesa todos los mensajes pendientes del worker y reprograma el sondeo."""
        try:
            while True:
                msg = self._gui_queue.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass

        # Seguir sondeando mientras haya un worker activo
        if self._conversion_thread and self._conversion_thread.is_alive():
            self.root.after(self._POLL_MS, self._poll_queue)

    def _handle_msg(self, msg: _Msg):
        p = msg.payload
        match msg.kind:
            case "log":
                self._log(p["text"], p.get("tag"))
            case "progress":
                self.progress_var.set(p["label"])
                self.progress_bar.configure(value=p["value"])
            case "progress_max":
                self.progress_bar.configure(maximum=p["maximum"])
            case "stats":
                self.stats_var.set(
                    f"✅ Exitosos: {p['ok']}  |  ❌ Errores: {p['fail']}  |  📊 Total: {p['total']}"
                )
            case "done":
                self._set_busy(False)
                if not p["cancelled"]:
                    messagebox.showinfo(
                        "Conversión Completada",
                        f"¡Conversión finalizada!\n\n"
                        f"✅ Exitosos: {p['ok']}\n"
                        f"❌ Errores: {p['fail']}\n\n"
                        f"Los archivos han sido organizados en las carpetas correspondientes.",
                    )

    # ------------------------------------------------------------------
    # Control de conversión
    # ------------------------------------------------------------------

    def _start_conversion(self):
        folder_str = self.selected_folder.get()
        if not folder_str:
            messagebox.showerror("Error", "Por favor selecciona una carpeta primero")
            return

        folder_path = Path(folder_str)
        if not folder_path.exists():
            messagebox.showerror("Error", "La carpeta seleccionada no existe")
            return

        files = _get_files(folder_path)
        if not files:
            messagebox.showwarning(
                "Sin archivos",
                "No se encontraron archivos de imagen (PNG/JPG) en la carpeta seleccionada",
            )
            return

        self.log_text.delete("1.0", "end")
        self.stats_var.set("✅ Exitosos: 0  |  ❌ Errores: 0  |  📊 Total: 0")
        self._cancel_event.clear()
        self._set_busy(True)

        self._log("🚀 Iniciando conversión por lotes...", "info")
        self._log(f"📂 Procesando archivos de: {folder_str}\n", "info")

        self._conversion_thread = threading.Thread(
            target=self._conversion_worker,
            args=(folder_path, files),
            daemon=True,
        )
        self._conversion_thread.start()
        self.root.after(self._POLL_MS, self._poll_queue)

    def _cancel_conversion(self):
        if self._cancel_event.is_set():
            return
        if messagebox.askyesno(
            "Cancelar conversión",
            "¿Estás seguro de que deseas cancelar la conversión?\n\n"
            "Los archivos ya procesados se mantendrán.",
        ):
            self._cancel_event.set()
            self._q_log("\n⚠️ Cancelando conversión...", "warning")

    # ------------------------------------------------------------------
    # Helpers para enviar mensajes a la queue (seguros desde cualquier hilo)
    # ------------------------------------------------------------------

    def _q_log(self, text: str, tag: str | None = None):
        self._gui_queue.put(_Msg("log", text=text, tag=tag))

    def _q_progress(self, label: str, value: int):
        self._gui_queue.put(_Msg("progress", label=label, value=value))

    def _q_stats(self, ok: int, fail: int, total: int):
        self._gui_queue.put(_Msg("stats", ok=ok, fail=fail, total=total))

    # ------------------------------------------------------------------
    # Worker (hilo secundario — NO toca widgets directamente)
    # ------------------------------------------------------------------

    def _conversion_worker(self, input_path: Path, files: List[Path]):
        converted_folder = input_path / "converted_success"
        error_folder = input_path / "conversion_errors"
        converted_folder.mkdir(exist_ok=True)
        error_folder.mkdir(exist_ok=True)

        sep = "=" * 70
        self._q_log(sep, "info")
        self._q_log(f"📁 Carpeta de archivos exitosos: {converted_folder}", "info")
        self._q_log(f"📁 Carpeta de archivos con error: {error_folder}", "warning")
        self._q_log(sep, "info")

        total = len(files)
        self._gui_queue.put(_Msg("progress_max", maximum=total))
        self._q_log(f"\n🔍 Se encontraron {total} archivo(s) para procesar\n", "info")

        ok = fail = 0

        for i, file_path in enumerate(files):
            if self._cancel_event.is_set():
                self._q_log("\n⚠️ Conversión cancelada por el usuario", "warning")
                break

            self._q_progress(f"Procesando {i + 1}/{total}: {file_path.name}", i)

            temp_output = input_path / f"_tmp_{file_path.name}"
            try:
                success, result = _convert_file(file_path, temp_output)

                if success:
                    shutil.move(str(temp_output), str(converted_folder / file_path.name))
                    shutil.move(str(file_path), str(converted_folder / f"original_{file_path.name}"))
                    self._q_log(f"✅ {result} → {file_path.name}", "success")
                    ok += 1
                else:
                    _safe_unlink(temp_output)
                    shutil.move(str(file_path), str(error_folder / file_path.name))
                    self._q_log(f"❌ {file_path.name} → Error: {result}", "error")
                    fail += 1

            except Exception as exc:
                _safe_unlink(temp_output)
                try:
                    shutil.move(str(file_path), str(error_folder / file_path.name))
                except OSError:
                    pass
                self._q_log(f"❌ {file_path.name} → Error inesperado: {exc}", "error")
                fail += 1

            self._q_stats(ok, fail, i + 1)

        # Progreso final
        self._q_progress("✅ Conversión completada", total)

        self._q_log(f"\n{sep}", "info")
        self._q_log("📊 RESUMEN DE CONVERSIÓN", "info")
        self._q_log(sep, "info")
        self._q_log(f"✅ Archivos exitosos: {ok}", "success")
        self._q_log(f"❌ Archivos fallidos: {fail}", "error")
        self._q_log(f"📁 Convertidos guardados en: {converted_folder}", "info")
        self._q_log(f"📁 Errores movidos a: {error_folder}", "warning")
        self._q_log(sep, "info")

        self._gui_queue.put(_Msg("done", ok=ok, fail=fail, cancelled=self._cancel_event.is_set()))


# ---------------------------------------------------------------------------
# Lógica de conversión — funciones puras, sin dependencias de GUI
# ---------------------------------------------------------------------------

def _get_files(input_path: Path) -> List[Path]:
    """Devuelve archivos PNG/JPG de *input_path* sin duplicados."""
    seen: set[Path] = set()
    result: List[Path] = []
    for ext in ("png", "jpg", "jpeg"):
        for p in input_path.glob(f"*.{ext}"):
            if p not in seen:
                seen.add(p)
                result.append(p)
        # glob no es case-sensitive en Windows, pero sí en Linux → cubrir ambos
        for p in input_path.glob(f"*.{ext.upper()}"):
            if p not in seen:
                seen.add(p)
                result.append(p)
    return result


def _safe_unlink(path: Path):
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def _convert_file(
    input_file_path: Path, output_file_path: Path
) -> Tuple[bool, str]:
    """
    Convierte un archivo Emocre a Koikatsu.

    Returns:
        (True, nombre_personaje) si tuvo éxito, (False, mensaje_error) si falló.
    """
    try:
        with open(input_file_path, "rb") as f:
            file_data = f.read()

        ec = EmocreCharaData.load(file_data)
        kk = KoikatuCharaData()

        # — Cabecera / metadatos —
        kk.image = ec.image
        kk.face_image = ec.image
        kk.product_no = 100
        kk.header = "【KoiKatuChara】".encode("utf-8")
        kk.version = "0.0.0".encode("ascii")
        kk.blockdata = copy.deepcopy(ec.blockdata)
        kk.serialized_lstinfo_order = copy.deepcopy(kk.blockdata)
        kk.original_lstinfo_order = copy.deepcopy(kk.blockdata)

        # — Bloques principales —
        kk.Custom = copy.deepcopy(ec.Custom)
        kk.Coordinate = Coordinate(data=None, version="0.0.0")
        kk.Parameter = copy.deepcopy(ec.Parameter)
        kk.Status = copy.deepcopy(ec.Status)

        if "KKEx" in ec.blockdata:
            kk.KKEx = copy.deepcopy(ec.KKEx)

        # — Ajustes por sección —
        _adjust_face(kk)
        kk.Custom["body"]["version"] = "0.0.2"
        kk.Custom["hair"]["version"] = "0.0.4"
        _adjust_clothing_and_accessories(ec, kk)
        _configure_parameters(kk, ec)
        _configure_status(kk)

        with open(output_file_path, "wb") as f:
            f.write(bytes(kk))

        return True, ec["Parameter"].get("fullname", "Sin nombre")

    except Exception as exc:
        return False, str(exc)


def _adjust_face(kk):
    face = kk.Custom["face"]
    face["version"] = "0.0.2"
    face["pupilHeight"] *= 1.08
    face["hlUpY"] = (face["hlUpY"] - 0.25) * 2
    for key in ("hlUpX", "hlDownX", "hlUpScale", "hlDownScale"):
        face.pop(key, None)


def _adjust_clothing_and_accessories(ec, kk):
    clothes = ec.Coordinate["clothes"]
    clothes["hideBraOpt"] = [False, False]
    clothes["hideShortsOpt"] = [False, False]

    for i, part in enumerate(clothes["parts"]):
        clothes["parts"][i].update(
            {
                "emblemeId":  part["emblemeId"][0],
                "emblemeId2": part["emblemeId"][1],
            }
        )

    # Duplicar última parte
    clothes["parts"].append(copy.deepcopy(clothes["parts"][-1]))

    for i in range(len(ec.Coordinate["accessory"]["parts"])):
        ec.Coordinate["accessory"]["parts"][i].pop("hideTiming", None)

    makeup = copy.deepcopy(ec.Custom["face"]["baseMakeup"])
    slot = {
        "clothes":       clothes,
        "accessory":     ec.Coordinate["accessory"],
        "enableMakeup":  False,
        "makeup":        makeup,
    }
    kk.Coordinate.data = [copy.deepcopy(slot) for _ in range(7)]


def _configure_parameters(kk, ec):
    p = kk.Parameter
    p["version"]        = "0.0.5"
    p["lastname"]       = " "
    p["firstname"]      = ec.Parameter.get("fullname", "Sin nombre")
    p["nickname"]       = " "
    p["callType"]       = -1
    p["clubActivities"] = 0
    p["weakPoint"]      = 0
    p["aggressive"]     = 0
    p["diligence"]      = 0
    p["kindness"]       = 0
    p["personality"]    = 0
    p.pop("fullname", None)

    p["awnser"] = dict.fromkeys(
        ["animal", "eat", "cook", "exercise", "study",
         "fashionable", "blackCoffee", "spicy", "sweet"],
        True,
    )
    p["denial"] = dict.fromkeys(
        ["kiss", "aibu", "anal", "massage", "notCondom"],
        False,
    )
    p["attribute"] = dict.fromkeys(
        ["hinnyo", "harapeko", "donkan", "choroi", "bitch", "mutturi",
         "dokusyo", "ongaku", "kappatu", "ukemi", "friendly", "kireizuki",
         "taida", "sinsyutu", "hitori", "undo", "majime", "likeGirls"],
        True,
    )


def _configure_status(kk):
    s = kk.Status
    s["version"]           = "0.0.0"
    s["clothesState"]      = b"\x00" * 9
    s["eyesBlink"]         = False
    s["mouthPtn"]          = 1
    s["mouthOpenMax"]      = 0
    s["mouthFixed"]        = True
    s["eyesLookPtn"]       = 1
    s["neckLookPtn"]       = 3
    s["visibleSonAlways"]  = False
    s["coordinateType"]    = 4
    s["backCoordinateType"] = 0
    s["shoesType"]         = 1
    for key in ("mouthOpenMin", "enableSonDirection", "sonDirectionX", "sonDirectionY"):
        s.pop(key, None)


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

def main():
    root = tk.Tk()

    try:
        root.tk.call("source", "azure.tcl")
        root.tk.call("set_theme", "light")
    except Exception:
        pass

    EmocreConverterGUI(root)

    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth()  // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    root.mainloop()


if __name__ == "__main__":
    main()