import os
import shutil
import logging
import queue
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Dict
from tkinter import Tk, filedialog, messagebox, Button, Label, Frame, StringVar, ttk
from kkloader import KoikatuCharaData


# ---------------------------------------------------------------------------
# Mensajes que el worker envía a la GUI (en lugar de tocar tkinter directo)
# ---------------------------------------------------------------------------
class _Msg:
    """Contenedor simple de mensajes worker → GUI."""
    __slots__ = ("kind", "payload")

    def __init__(self, kind: str, payload=None):
        self.kind = kind
        self.payload = payload


class KoikatsuClassifier:
    """Clasificador de cartas de personajes de Koikatsu por género."""

    SEXO_MASCULINO = 0
    SEXO_FEMENINO = 1
    POLL_MS = 50          # frecuencia de polling de la cola GUI (ms)
    LOG_MAX_BYTES = 5 * 1024 * 1024   # 5 MB por archivo de log
    LOG_BACKUP_COUNT = 3

    def __init__(self):
        self._setup_logging()
        self._setup_ui()
        self._is_processing = False
        self._cancel_event = threading.Event()
        self._gui_queue: queue.Queue = queue.Queue()

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def _setup_logging(self):
        log_file = Path("koikatsu_classifier.log")
        handler_file = RotatingFileHandler(
            log_file,
            maxBytes=self.LOG_MAX_BYTES,
            backupCount=self.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler_file.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

        handler_stream = logging.StreamHandler()
        handler_stream.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

        logging.basicConfig(level=logging.INFO, handlers=[handler_file, handler_stream])
        self.logger = logging.getLogger(__name__)
        self.logger.info("=" * 50)
        self.logger.info("Iniciando Clasificador de Cartas Koikatsu")
        self.logger.info("=" * 50)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self):
        self.ventana = Tk()
        self.ventana.title("Clasificador de Cartas Koikatsu")
        self.ventana.geometry("560x420")
        self.ventana.resizable(False, False)
        self.ventana.configure(bg="#f0f0f0")

        self._estado_var = StringVar(value="Listo para procesar")
        self._progreso_var = StringVar(value="")

        main_frame = Frame(self.ventana, bg="#f0f0f0")
        main_frame.pack(expand=True, fill="both", padx=30, pady=20)

        Label(
            main_frame,
            text="Clasificador de Cartas Koikatsu",
            font=("Arial", 16, "bold"),
            bg="#f0f0f0",
            fg="#333333",
        ).pack(pady=(0, 6))

        Label(
            main_frame,
            text="Organiza tus personajes por género automáticamente",
            font=("Arial", 9),
            bg="#f0f0f0",
            fg="#666666",
        ).pack(pady=(0, 16))

        ttk.Separator(main_frame, orient="horizontal").pack(fill="x", pady=8)

        Label(
            main_frame,
            text="Selecciona la carpeta que contiene las cartas PNG:",
            font=("Arial", 10),
            bg="#f0f0f0",
        ).pack(pady=(10, 12))

        btn_frame = Frame(main_frame, bg="#f0f0f0")
        btn_frame.pack(pady=8)

        self._btn_seleccionar = Button(
            btn_frame,
            text="📁 Seleccionar Carpeta",
            command=self._seleccionar_carpeta,
            font=("Arial", 11, "bold"),
            bg="#4CAF50",
            fg="white",
            activebackground="#45a049",
            activeforeground="white",
            padx=28,
            pady=10,
            cursor="hand2",
            relief="flat",
        )
        self._btn_seleccionar.pack(side="left", padx=4)

        self._btn_cancelar = Button(
            btn_frame,
            text="✖ Cancelar",
            command=self._solicitar_cancelacion,
            font=("Arial", 11, "bold"),
            bg="#e53935",
            fg="white",
            activebackground="#b71c1c",
            activeforeground="white",
            padx=18,
            pady=10,
            cursor="hand2",
            relief="flat",
            state="disabled",
        )
        self._btn_cancelar.pack(side="left", padx=4)

        progress_frame = Frame(main_frame, bg="#f0f0f0")
        progress_frame.pack(pady=12, fill="x")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor="#e0e0e0",
            background="#4CAF50",
            thickness=20,
        )

        self._progress_bar = ttk.Progressbar(
            progress_frame,
            mode="determinate",
            length=500,
            style="Custom.Horizontal.TProgressbar",
        )
        self._progress_bar.pack(pady=4)

        Label(
            progress_frame,
            textvariable=self._estado_var,
            font=("Arial", 9, "bold"),
            bg="#f0f0f0",
            fg="#333333",
        ).pack(pady=2)

        Label(
            progress_frame,
            textvariable=self._progreso_var,
            font=("Arial", 9),
            bg="#f0f0f0",
            fg="#666666",
        ).pack(pady=2)

        ttk.Separator(main_frame, orient="horizontal").pack(fill="x", pady=12)

        info_frame = Frame(main_frame, bg="#f0f0f0")
        info_frame.pack(pady=4, fill="x")

        Label(
            info_frame,
            text="📂 Carpetas que se crearán:",
            font=("Arial", 9, "bold"),
            bg="#f0f0f0",
            fg="#333333",
        ).pack(anchor="w", pady=(0, 4))

        for titulo, desc in [
            ("👨 Masculino", "Personajes masculinos (sex = 0)"),
            ("👩 Femenino", "Personajes femeninos (sex = 1)"),
            ("❓ Sin información", "Archivos con errores o datos inválidos"),
        ]:
            Label(
                info_frame,
                text=f"{titulo}: {desc}",
                font=("Arial", 8),
                bg="#f0f0f0",
                fg="#555555",
            ).pack(anchor="w", padx=10, pady=1)

    # ------------------------------------------------------------------
    # GUI queue polling  (único lugar donde se toca tkinter desde fuera)
    # ------------------------------------------------------------------
    def _poll_queue(self):
        """Consume mensajes pendientes del worker y actualiza la GUI."""
        try:
            while True:
                msg: _Msg = self._gui_queue.get_nowait()

                if msg.kind == "progress":
                    actual, total = msg.payload
                    pct = (actual / total) * 100 if total else 0
                    self._progress_bar["value"] = pct
                    self._progreso_var.set(
                        f"Procesando: {actual}/{total} archivos ({pct:.1f}%)"
                    )

                elif msg.kind == "estado":
                    self._estado_var.set(msg.payload)

                elif msg.kind == "done":
                    self._on_worker_done(msg.payload)
                    return  # no reprogramar

                elif msg.kind == "error":
                    messagebox.showerror("❌ Error", msg.payload)
                    self._restore_ui()
                    return

                elif msg.kind == "warning":
                    messagebox.showwarning("Aviso", msg.payload)

        except queue.Empty:
            pass

        # Reprogramar solo si el worker sigue activo
        if self._is_processing:
            self.ventana.after(self.POLL_MS, self._poll_queue)

    def _on_worker_done(self, stats: Optional[Dict]):
        if stats is None:
            # cancelado
            self._estado_var.set("⚠ Proceso cancelado")
            messagebox.showwarning("Cancelado", "El proceso fue cancelado por el usuario.")
        else:
            total = sum(stats[k] for k in ("masculino", "femenino", "sin_info", "errores_movimiento"))
            messagebox.showinfo("✅ Proceso Completado", self._construir_mensaje_final(total, stats))
        self._restore_ui()

    def _restore_ui(self):
        self._is_processing = False
        self._btn_seleccionar.config(state="normal", bg="#4CAF50")
        self._btn_cancelar.config(state="disabled")
        self._estado_var.set("✓ Listo para procesar")
        self._progreso_var.set("")
        self._progress_bar["value"] = 0

    # ------------------------------------------------------------------
    # Acciones de usuario
    # ------------------------------------------------------------------
    def _seleccionar_carpeta(self):
        if self._is_processing:
            messagebox.showwarning("Proceso en curso", "Espera a que termine el proceso actual.")
            return

        carpeta = filedialog.askdirectory(title="Seleccionar carpeta con cartas PNG", mustexist=True)
        if not carpeta:
            return

        if messagebox.askyesno(
            "Confirmar procesamiento",
            f"¿Clasificar las cartas en:\n\n{carpeta}\n\nLos archivos se moverán a subcarpetas.",
            icon="question",
        ):
            self._cancel_event.clear()
            self._is_processing = True
            self._btn_seleccionar.config(state="disabled", bg="#cccccc")
            self._btn_cancelar.config(state="normal")
            self._estado_var.set("🔄 Iniciando procesamiento...")
            threading.Thread(
                target=self._worker, args=(carpeta,), daemon=True
            ).start()
            self.ventana.after(self.POLL_MS, self._poll_queue)

    def _solicitar_cancelacion(self):
        self._cancel_event.set()
        self._estado_var.set("⏹ Cancelando…")
        self._btn_cancelar.config(state="disabled")

    # ------------------------------------------------------------------
    # Worker (hilo secundario — NO toca tkinter directamente)
    # ------------------------------------------------------------------
    def _worker(self, ruta_str: str):
        q = self._gui_queue
        try:
            ruta = Path(ruta_str)
            self.logger.info(f"Procesando carpeta: {ruta}")

            carpetas = self._crear_carpetas(ruta)
            archivos_png = self._obtener_archivos_png(ruta)
            total = len(archivos_png)

            if total == 0:
                q.put(_Msg("warning", "No se encontraron archivos PNG en la carpeta seleccionada."))
                q.put(_Msg("done", None))
                return

            self.logger.info(f"Iniciando clasificación de {total} archivos")
            q.put(_Msg("estado", f"📊 Clasificando {total} archivos…"))

            stats: Dict[str, int] = {
                "masculino": 0,
                "femenino": 0,
                "sin_info": 0,
                "errores_movimiento": 0,
            }

            for i, archivo in enumerate(archivos_png, 1):
                if self._cancel_event.is_set():
                    self.logger.info("Proceso cancelado por el usuario.")
                    q.put(_Msg("done", None))
                    return

                q.put(_Msg("progress", (i, total)))

                sexo = self._clasificar_carta(archivo)

                if sexo == self.SEXO_FEMENINO:
                    destino = carpetas["femenino"] / archivo.name
                    categoria = "femenino"
                elif sexo == self.SEXO_MASCULINO:
                    destino = carpetas["masculino"] / archivo.name
                    categoria = "masculino"
                else:
                    destino = carpetas["sin_info"] / archivo.name
                    categoria = "sin_info"

                if self._mover_archivo_seguro(archivo, destino):
                    stats[categoria] += 1
                else:
                    stats["errores_movimiento"] += 1

            q.put(_Msg("progress", (total, total)))
            self.logger.info(
                f"RESUMEN — Masculino: {stats['masculino']} | "
                f"Femenino: {stats['femenino']} | "
                f"Sin info: {stats['sin_info']} | "
                f"Errores: {stats['errores_movimiento']}"
            )
            q.put(_Msg("done", stats))

        except Exception as e:
            error_msg = f"Error durante el procesamiento:\n\n{type(e).__name__}: {e}"
            self.logger.exception("Error crítico en el worker")
            q.put(_Msg("error", error_msg))

    # ------------------------------------------------------------------
    # Lógica de negocio
    # ------------------------------------------------------------------
    def _crear_carpetas(self, ruta_base: Path) -> Dict[str, Path]:
        carpetas = {
            "masculino": ruta_base / "Masculino",
            "femenino": ruta_base / "Femenino",
            "sin_info": ruta_base / "Sin información",
        }
        for nombre, carpeta in carpetas.items():
            carpeta.mkdir(exist_ok=True)
            self.logger.info(f"Carpeta '{nombre}' lista: {carpeta}")
        return carpetas

    def _obtener_archivos_png(self, ruta: Path) -> list:
        try:
            archivos = [f for f in ruta.iterdir() if f.is_file() and f.suffix.lower() == ".png"]
            self.logger.info(f"Encontrados {len(archivos)} archivos PNG en {ruta}")
            return archivos
        except Exception:
            self.logger.exception("Error listando archivos")
            return []

    def _clasificar_carta(self, archivo: Path) -> Optional[int]:
        try:
            kc = KoikatuCharaData.load(str(archivo))

            # Verificar que el bloque Parameter existe en esta carta
            if "Parameter" not in kc.blockdata:
                self.logger.warning(f"⚠ {archivo.name} - Bloque 'Parameter' ausente (blocks={kc.blockdata})")
                return None

            sexo = kc["Parameter"]["sex"]

            if sexo == self.SEXO_MASCULINO:
                self.logger.debug(f"✓ {archivo.name} - Masculino")
                return self.SEXO_MASCULINO
            elif sexo == self.SEXO_FEMENINO:
                self.logger.debug(f"✓ {archivo.name} - Femenino")
                return self.SEXO_FEMENINO
            else:
                self.logger.warning(f"⚠ {archivo.name} - Valor de sexo desconocido: {sexo!r}")
                return None

        except FileNotFoundError:
            self.logger.error(f"✗ {archivo.name} - Archivo no encontrado")
        except PermissionError:
            self.logger.error(f"✗ {archivo.name} - Sin permisos de acceso")
        except KeyError as e:
            self.logger.error(f"✗ {archivo.name} - Clave faltante en los datos: {e}")
        except Exception as e:
            self.logger.error(f"✗ {archivo.name} - {type(e).__name__}: {e}")
        return None

    def _mover_archivo_seguro(self, origen: Path, destino: Path) -> bool:
        try:
            if not origen.exists():
                self.logger.error(f"Origen no existe: {origen}")
                return False
            destino_final = destino
            contador = 1
            while destino_final.exists():
                destino_final = destino.parent / f"{destino.stem}_({contador}){destino.suffix}"
                contador += 1
            if destino_final != destino:
                self.logger.info(f"Renombrado para evitar duplicado: {destino_final.name}")
            shutil.move(str(origen), str(destino_final))
            return True
        except PermissionError:
            self.logger.error(f"Sin permisos para mover {origen.name}")
        except Exception as e:
            self.logger.error(f"Error moviendo {origen.name}: {type(e).__name__}: {e}")
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _construir_mensaje_final(self, total: int, stats: Dict[str, int]) -> str:
        ok = stats["masculino"] + stats["femenino"]
        sep = "─" * 40
        return (
            f"✅ Proceso completado exitosamente\n\n"
            f"📊 ESTADÍSTICAS:\n{sep}\n"
            f"Total de archivos procesados: {total}\n"
            f"Clasificados correctamente:   {ok}\n"
            f"Sin información / errores:    {stats['sin_info']}\n"
            f"Errores al mover archivos:    {stats['errores_movimiento']}\n\n"
            f"📁 DISTRIBUCIÓN POR GÉNERO:\n{sep}\n"
            f"👨 Masculino:       {stats['masculino']} archivo(s)\n"
            f"👩 Femenino:        {stats['femenino']} archivo(s)\n"
            f"❓ Sin información: {stats['sin_info']} archivo(s)\n\n"
            f"{sep}\n"
            f"Los archivos han sido organizados en subcarpetas."
        )

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def ejecutar(self):
        self.ventana.protocol("WM_DELETE_WINDOW", self._cerrar_aplicacion)
        self.ventana.mainloop()

    def _cerrar_aplicacion(self):
        if self._is_processing:
            if not messagebox.askyesno(
                "Proceso en curso",
                "Hay un proceso en curso.\n¿Salir de todas formas?",
                icon="warning",
            ):
                return
            self._cancel_event.set()
        self.logger.info("Cerrando aplicación")
        self.ventana.destroy()


# ---------------------------------------------------------------------------
def main():
    try:
        KoikatsuClassifier().ejecutar()
    except Exception as e:
        logging.exception("Error fatal al iniciar la aplicación")
        messagebox.showerror("Error Fatal", f"No se pudo iniciar la aplicación:\n\n{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()