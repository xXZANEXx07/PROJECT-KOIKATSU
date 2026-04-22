import os
import shutil
import math
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, ProcessPoolExecutor
import multiprocessing
import time

class OrganizadorArchivos:
    def __init__(self):
        self.window = tk.Tk()
        self.progreso_cancelado = False
        # Extremadamente agresivo para archivos pequeños
        self.max_workers = min(256, (multiprocessing.cpu_count() or 1) * 32)
        self.setup_window()
        self.create_widgets()
    
    @staticmethod
    def ordenamiento_natural_key(texto):
        """
        Convierte un string en una lista de elementos para ordenamiento natural.
        Los números se convierten a int para que se ordenen correctamente.
        
        Ejemplos:
        "1(1).png" -> [1, '(', 1, ').png']
        "1(10).png" -> [1, '(', 10, ').png']
        "archivo_10.jpg" -> ['archivo_', 10, '.jpg']
        """
        def convertir(texto):
            return int(texto) if texto.isdigit() else texto.lower()
        
        return [convertir(c) for c in re.split(r'(\d+)', texto)]
        
    def setup_window(self):
        """Configurar la ventana principal"""
        self.window.title("Organizador de Archivos v4.2 (Ordenamiento Natural)")
        self.window.geometry("750x750")
        self.window.resizable(True, True)  # Permitir redimensionar
        
        # Centrar la ventana
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (750 // 2)
        y = (self.window.winfo_screenheight() // 2) - (750 // 2)
        self.window.geometry(f"750x750+{x}+{y}")
        
    def create_widgets(self):
        """Crear y configurar todos los widgets"""
        # Frame principal
        main_frame = ttk.Frame(self.window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Selección de carpeta
        carpeta_frame = ttk.LabelFrame(main_frame, text="Carpeta a organizar", padding="10")
        carpeta_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.entry_carpeta = ttk.Entry(carpeta_frame, width=50)
        self.entry_carpeta.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)
        
        self.btn_carpeta = ttk.Button(carpeta_frame, text="Seleccionar", command=self.seleccionar_carpeta)
        self.btn_carpeta.pack(side=tk.RIGHT)
        
        # Configuración
        config_frame = ttk.LabelFrame(main_frame, text="Configuración", padding="10")
        config_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Cantidad por lote
        cantidad_frame = ttk.Frame(config_frame)
        cantidad_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(cantidad_frame, text="Archivos por lote:").pack(side=tk.LEFT)
        self.entry_cantidad = ttk.Entry(cantidad_frame, width=10)
        self.entry_cantidad.insert(0, "1000")
        self.entry_cantidad.pack(side=tk.LEFT, padx=(10, 0))
        
        # Método de ordenamiento
        metodo_frame = ttk.Frame(config_frame)
        metodo_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(metodo_frame, text="Ordenar archivos por:").pack(side=tk.LEFT)
        self.metodo_ordenamiento = tk.StringVar(value="fecha")
        
        metodos = [
            ("Ninguno (más rápido)", "ninguno"),
            ("Fecha de creación (más viejo primero)", "fecha"),
            ("Nombre (A-Z con orden natural)", "nombre"),
            ("Tamaño (menor a mayor)", "tamanio"),
            ("Tipo de archivo", "tipo"),
            ("Aleatorio", "aleatorio")
        ]
        
        combo_metodo = ttk.Combobox(metodo_frame, textvariable=self.metodo_ordenamiento, 
                                    values=[m[0] for m in metodos], state="readonly", width=35)
        combo_metodo.pack(side=tk.LEFT, padx=(10, 0))
        combo_metodo.current(0)
        
        # Hilos paralelos
        hilos_frame = ttk.Frame(config_frame)
        hilos_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(hilos_frame, text="Hilos paralelos:").pack(side=tk.LEFT)
        self.entry_hilos = ttk.Entry(hilos_frame, width=10)
        self.entry_hilos.insert(0, str(self.max_workers))
        self.entry_hilos.pack(side=tk.LEFT, padx=(10, 0))
        ttk.Label(hilos_frame, text=f"(Óptimo: {self.max_workers})").pack(side=tk.LEFT, padx=(10, 0))
        
        # Tamaño de batch - optimizado para imágenes
        batch_frame = ttk.Frame(config_frame)
        batch_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(batch_frame, text="Batch size:").pack(side=tk.LEFT)
        self.entry_batch = ttk.Entry(batch_frame, width=10)
        self.entry_batch.insert(0, "200")  # Más grande para imágenes
        self.entry_batch.pack(side=tk.LEFT, padx=(10, 0))
        ttk.Label(batch_frame, text="(archivos por hilo - 200 óptimo para imágenes)").pack(side=tk.LEFT, padx=(10, 0))
        
        # Opción para crear subcarpetas por fecha
        self.crear_subcarpetas_fecha = tk.BooleanVar()
        check_fecha = ttk.Checkbutton(config_frame, text="Crear subcarpetas por fecha de creación (YYYY-MM)", 
                       variable=self.crear_subcarpetas_fecha)
        check_fecha.pack(anchor=tk.W)
        
        # Warning sobre subcarpetas
        warning_label = ttk.Label(config_frame, text="⚠️  Subcarpetas reducen velocidad 10x", 
                                 foreground="red", font=("TkDefaultFont", 9, "bold"))
        warning_label.pack(anchor=tk.W, padx=(20, 0))
        
        # Opción para copiar en lugar de mover
        self.copiar_archivos = tk.BooleanVar()
        check_copiar = ttk.Checkbutton(config_frame, text="Copiar archivos (en lugar de mover)", 
                       variable=self.copiar_archivos)
        check_copiar.pack(anchor=tk.W)
        
        # Warning sobre copiar
        warning_label2 = ttk.Label(config_frame, text="⚠️  Copiar es 100-1000x más lento", 
                                 foreground="red", font=("TkDefaultFont", 9, "bold"))
        warning_label2.pack(anchor=tk.W, padx=(20, 0))
        
        # Modo extremo
        self.modo_extremo = tk.BooleanVar(value=True)
        ttk.Checkbutton(config_frame, text="🔥 Modo EXTREMO (máxima velocidad, sin verificaciones)", 
                       variable=self.modo_extremo).pack(anchor=tk.W)
        
        # ADVERTENCIA WINDOWS DEFENDER - MÁS COMPACTA
        separator = ttk.Separator(config_frame, orient='horizontal')
        separator.pack(fill=tk.X, pady=10)
        
        defender_frame = ttk.LabelFrame(config_frame, text="⚠️  Windows Defender", padding="8")
        defender_frame.pack(fill=tk.X, pady=(0, 10))
        
        msg_defender = ttk.Label(defender_frame, 
                                text="Windows Defender ralentiza 10-50x (horas para 170k archivos).\n"
                                     "SOLUCIÓN: Desactiva 'Protección en tiempo real' temporalmente.\n"
                                     "Seguridad Windows → Protección virus → Administrar config.",
                                foreground="red",
                                font=("TkDefaultFont", 8),
                                justify=tk.LEFT)
        msg_defender.pack(anchor=tk.W)
        
        btn_abrir_defender = ttk.Button(defender_frame, 
                                       text="🛡️ Abrir Seguridad Windows",
                                       command=lambda: os.system('start windowsdefender:'))
        btn_abrir_defender.pack(pady=(5, 0), anchor=tk.W)
        
        # Filtro de extensiones
        filtro_frame = ttk.Frame(config_frame)
        filtro_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(filtro_frame, text="Filtrar extensiones (opcional):").pack(side=tk.LEFT)
        self.entry_filtro = ttk.Entry(filtro_frame, width=20)
        self.entry_filtro.pack(side=tk.LEFT, padx=(10, 0))
        ttk.Label(filtro_frame, text="Ej: .jpg,.png,.pdf").pack(side=tk.LEFT, padx=(10, 0))
        
        # Información
        info_frame = ttk.LabelFrame(main_frame, text="Información", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.label_info = ttk.Label(info_frame, text="Selecciona una carpeta para comenzar")
        self.label_info.pack()
        
        self.label_velocidad = ttk.Label(info_frame, text="", 
                                        font=("TkDefaultFont", 11, "bold"),
                                        foreground="green")
        self.label_velocidad.pack()
        
        self.label_tiempo = ttk.Label(info_frame, text="")
        self.label_tiempo.pack()
        
        # Barra de progreso
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(info_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(10, 0))
        
        # Botones
        botones_frame = ttk.Frame(main_frame)
        botones_frame.pack(fill=tk.X)
        
        self.btn_organizar = ttk.Button(botones_frame, text="🔥 ORGANIZAR ULTRA RÁPIDO", 
                                      command=self.iniciar_organizacion)
        self.btn_organizar.pack(side=tk.LEFT, padx=(0, 10))
        
        self.btn_cancelar = ttk.Button(botones_frame, text="Cancelar", 
                                     command=self.cancelar_operacion, state=tk.DISABLED)
        self.btn_cancelar.pack(side=tk.LEFT)
        
        # Bind para actualizar info
        self.entry_carpeta.bind('<KeyRelease>', self.actualizar_info)
        
    def seleccionar_carpeta(self):
        """Seleccionar carpeta usando diálogo"""
        carpeta = filedialog.askdirectory(title="Selecciona la carpeta a organizar")
        if carpeta:
            self.entry_carpeta.delete(0, tk.END)
            self.entry_carpeta.insert(0, carpeta)
            self.actualizar_info()
    
    def actualizar_info(self, event=None):
        """Actualizar información sobre la carpeta seleccionada"""
        ruta = self.entry_carpeta.get()
        if not ruta or not os.path.exists(ruta):
            self.label_info.config(text="Selecciona una carpeta válida")
            return
            
        try:
            # Escaneo rápido
            count = 0
            size = 0
            filtro = self.entry_filtro.get().strip()
            extensiones = set()
            
            if filtro:
                for ext in filtro.split(','):
                    ext = ext.strip().lower()
                    extensiones.add(ext if ext.startswith('.') else f'.{ext}')
            
            with os.scandir(ruta) as entries:
                for entry in entries:
                    if entry.is_file(follow_symlinks=False):
                        if not extensiones or any(entry.name.lower().endswith(ext) for ext in extensiones):
                            count += 1
                            size += entry.stat(follow_symlinks=False).st_size
            
            size_mb = size / (1024 * 1024)
            self.label_info.config(text=f"Archivos encontrados: {count} ({size_mb:.2f} MB)")
        except Exception as e:
            self.label_info.config(text=f"Error: {str(e)}")
    
    def obtener_archivos_filtrados_rapido(self, ruta_origen):
        """Escaneo ultra rápido de archivos - USANDO FECHA DE CREACIÓN"""
        filtro = self.entry_filtro.get().strip()
        extensiones = set()
        
        if filtro:
            for ext in filtro.split(','):
                ext = ext.strip().lower()
                extensiones.add(ext if ext.startswith('.') else f'.{ext}')
        
        archivos = []
        with os.scandir(ruta_origen) as entries:
            for entry in entries:
                if entry.is_file(follow_symlinks=False):
                    if not extensiones or any(entry.name.lower().endswith(ext) for ext in extensiones):
                        stat = entry.stat(follow_symlinks=False)
                        # CAMBIO: Usar st_ctime (fecha de creación) en lugar de st_mtime
                        archivos.append((entry.name, stat.st_ctime, stat.st_size))
        
        return archivos
    
    def ordenar_archivos(self, archivos, metodo):
        """Ordenar archivos con ordenamiento natural para nombres"""
        import random
        
        if metodo == "ninguno":
            return archivos
        elif metodo == "fecha":
            # Ordenar por fecha de creación (del más viejo al más nuevo)
            return sorted(archivos, key=lambda x: x[1])
        elif metodo == "nombre":
            # ORDENAMIENTO NATURAL: 1(1), 1(2), 1(10), 1(100)
            return sorted(archivos, key=lambda x: self.ordenamiento_natural_key(x[0]))
        elif metodo == "tamanio":
            return sorted(archivos, key=lambda x: x[2])
        elif metodo == "tipo":
            # También usa ordenamiento natural dentro de cada tipo
            return sorted(archivos, key=lambda x: (
                os.path.splitext(x[0])[1].lower(), 
                self.ordenamiento_natural_key(x[0])
            ))
        elif metodo == "aleatorio":
            archivos_copia = archivos.copy()
            random.shuffle(archivos_copia)
            return archivos_copia
        
        return archivos
    
    def validar_entrada(self):
        """Validar datos de entrada"""
        ruta = self.entry_carpeta.get().strip()
        cantidad = self.entry_cantidad.get().strip()
        hilos = self.entry_hilos.get().strip()
        batch = self.entry_batch.get().strip()
        
        if not ruta:
            messagebox.showwarning("Aviso", "Selecciona una carpeta primero.")
            return None, None, None, None
            
        if not os.path.exists(ruta):
            messagebox.showerror("Error", "La ruta proporcionada no existe.")
            return None, None, None, None
            
        try:
            cantidad_num = int(cantidad)
            if cantidad_num <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Aviso", "Ingresa un número válido mayor que 0.")
            return None, None, None, None
        
        try:
            hilos_num = int(hilos)
            if hilos_num <= 0 or hilos_num > 512:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Aviso", "Ingresa un número de hilos válido (1-512).")
            return None, None, None, None
        
        try:
            batch_num = int(batch)
            if batch_num <= 0 or batch_num > 1000:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Aviso", "Ingresa un batch size válido (1-1000).")
            return None, None, None, None
            
        return ruta, cantidad_num, hilos_num, batch_num
    
    def iniciar_organizacion(self):
        """Iniciar el proceso de organización"""
        resultado = self.validar_entrada()
        if resultado[0] is None:
            return
        
        ruta, cantidad, hilos, batch_size = resultado
            
        self.progreso_cancelado = False
        self.btn_organizar.config(state=tk.DISABLED)
        self.btn_cancelar.config(state=tk.NORMAL)
        self.progress_var.set(0)
        
        thread = threading.Thread(target=self.organizar_archivos_en_lotes, 
                                 args=(ruta, cantidad, hilos, batch_size))
        thread.daemon = True
        thread.start()
    
    def cancelar_operacion(self):
        """Cancelar la operación en curso"""
        self.progreso_cancelado = True
        self.btn_cancelar.config(state=tk.DISABLED)
        self.label_info.config(text="Cancelando operación...")
    
    def procesar_batch_extremo(self, batch_info):
        """Procesar un lote de archivos de una vez - MODO EXTREMO"""
        archivos_batch, ruta_origen, carpeta_lote, crear_fecha, copiar = batch_info
        exitosos = 0
        
        if self.progreso_cancelado:
            return exitosos
        
        for archivo, timestamp in archivos_batch:
            try:
                ruta_archivo = os.path.join(ruta_origen, archivo)
                
                if crear_fecha:
                    # Usar timestamp de creación para crear subcarpetas
                    fecha = datetime.fromtimestamp(timestamp)
                    subcarpeta = fecha.strftime("%Y-%m")
                    destino_dir = os.path.join(carpeta_lote, subcarpeta)
                else:
                    destino_dir = carpeta_lote
                
                ruta_destino = os.path.join(destino_dir, archivo)
                
                # Manejo rápido de duplicados
                if os.path.exists(ruta_destino):
                    nombre_base, extension = os.path.splitext(archivo)
                    contador = 1
                    while os.path.exists(ruta_destino):
                        ruta_destino = os.path.join(destino_dir, f"{nombre_base}_{contador}{extension}")
                        contador += 1
                
                # Operación ultra rápida
                if copiar:
                    # Copia directa con buffer grande
                    with open(ruta_archivo, 'rb') as src, open(ruta_destino, 'wb') as dst:
                        shutil.copyfileobj(src, dst, 1024*1024*64)  # 64MB buffer
                else:
                    # Movimiento directo - instantáneo en mismo disco
                    os.replace(ruta_archivo, ruta_destino)
                
                exitosos += 1
            except:
                pass  # Modo extremo: ignorar errores
        
        return exitosos
    
    def organizar_archivos_en_lotes(self, ruta_origen, cantidad_por_carpeta, num_hilos, batch_size):
        """Organización EXTREMADAMENTE RÁPIDA"""
        tiempo_inicio = time.perf_counter()
        
        try:
            # Escaneo rápido
            self.window.after(0, lambda: self.label_info.config(text="Escaneando archivos..."))
            archivos = self.obtener_archivos_filtrados_rapido(ruta_origen)
            
            # Ordenamiento
            metodo = self.metodo_ordenamiento.get()
            metodo_map = {
                "Ninguno (más rápido)": "ninguno",
                "Fecha de creación (más viejo primero)": "fecha",
                "Nombre (A-Z con orden natural)": "nombre",
                "Tamaño (menor a mayor)": "tamanio",
                "Tipo de archivo": "tipo",
                "Aleatorio": "aleatorio"
            }
            metodo_key = metodo_map.get(metodo, "ninguno")
            
            if metodo_key != "ninguno":
                self.window.after(0, lambda: self.label_info.config(text="Ordenando archivos..."))
                archivos = self.ordenar_archivos(archivos, metodo_key)
            
            total_archivos = len(archivos)
            if total_archivos == 0:
                self.window.after(0, lambda: messagebox.showinfo("Info", "No se encontraron archivos válidos."))
                self.window.after(0, self.finalizar_operacion)
                return
            
            total_lotes = math.ceil(total_archivos / cantidad_por_carpeta)
            
            # Pre-crear TODAS las carpetas
            self.window.after(0, lambda: self.label_info.config(text="Creando carpetas..."))
            carpetas_lote = []
            crear_fecha = self.crear_subcarpetas_fecha.get()
            
            for i in range(total_lotes):
                carpeta_lote = os.path.join(ruta_origen, f"Lote_{i+1:03d}")
                os.makedirs(carpeta_lote, exist_ok=True)
                carpetas_lote.append(carpeta_lote)
            
            # Pre-crear subcarpetas si es necesario (usando fecha de creación)
            if crear_fecha:
                subcarpetas = set()
                for _, timestamp, _ in archivos:
                    fecha = datetime.fromtimestamp(timestamp)
                    subcarpetas.add(fecha.strftime("%Y-%m"))
                
                for carpeta_lote in carpetas_lote:
                    for subcarpeta in subcarpetas:
                        os.makedirs(os.path.join(carpeta_lote, subcarpeta), exist_ok=True)
            
            # Preparar batches
            self.window.after(0, lambda: self.label_info.config(text="Preparando operación..."))
            batches = []
            
            for i in range(total_lotes):
                carpeta_lote = carpetas_lote[i]
                inicio = i * cantidad_por_carpeta
                fin = min(inicio + cantidad_por_carpeta, total_archivos)
                
                archivos_lote = archivos[inicio:fin]
                
                # Dividir en batches más pequeños para paralelizar
                for j in range(0, len(archivos_lote), batch_size):
                    batch = archivos_lote[j:j+batch_size]
                    # Solo nombre y timestamp para reducir overhead
                    batch_simple = [(a[0], a[1]) for a in batch]
                    batches.append((
                        batch_simple,
                        ruta_origen,
                        carpeta_lote,
                        crear_fecha,
                        self.copiar_archivos.get()
                    ))
            
            # Procesamiento paralelo MASIVO
            self.window.after(0, lambda: self.label_info.config(text="Procesando archivos..."))
            archivos_procesados = 0
            ultima_actualizacion = time.perf_counter()
            tiempo_ultima_medicion = tiempo_inicio
            archivos_ultima_medicion = 0
            
            with ThreadPoolExecutor(max_workers=num_hilos) as executor:
                futures = [executor.submit(self.procesar_batch_extremo, batch) for batch in batches]
                
                for future in as_completed(futures):
                    if self.progreso_cancelado:
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    
                    exitosos = future.result()
                    archivos_procesados += exitosos
                    
                    # Actualizar UI cada 0.1 segundos
                    ahora = time.perf_counter()
                    if (ahora - ultima_actualizacion) >= 0.1:
                        progreso = (archivos_procesados / total_archivos) * 100
                        tiempo_transcurrido = ahora - tiempo_inicio
                        
                        # Velocidad instantánea (más precisa)
                        tiempo_delta = ahora - tiempo_ultima_medicion
                        archivos_delta = archivos_procesados - archivos_ultima_medicion
                        velocidad_instantanea = archivos_delta / tiempo_delta if tiempo_delta > 0 else 0
                        
                        # Velocidad promedio
                        velocidad_promedio = archivos_procesados / tiempo_transcurrido if tiempo_transcurrido > 0 else 0
                        
                        # ETA
                        archivos_restantes = total_archivos - archivos_procesados
                        eta = archivos_restantes / velocidad_instantanea if velocidad_instantanea > 0 else 0
                        
                        self.window.after(0, lambda p=progreso: self.progress_var.set(p))
                        self.window.after(0, lambda ap=archivos_procesados, t=total_archivos: 
                            self.label_info.config(text=f"Procesados: {ap:,}/{t:,} archivos"))
                        self.window.after(0, lambda vi=velocidad_instantanea, vp=velocidad_promedio: 
                            self.label_velocidad.config(text=f"🚀 {vi:,.0f} archivos/seg (promedio: {vp:,.0f})"))
                        self.window.after(0, lambda e=eta:
                            self.label_tiempo.config(text=f"⏱️ Tiempo restante: {e:.1f}s"))
                        
                        ultima_actualizacion = ahora
                        tiempo_ultima_medicion = ahora
                        archivos_ultima_medicion = archivos_procesados
            
            # Finalizar
            tiempo_total = time.perf_counter() - tiempo_inicio
            self.window.after(0, self.finalizar_operacion)
            
            if not self.progreso_cancelado:
                velocidad_final = archivos_procesados / tiempo_total if tiempo_total > 0 else 0
                mensaje = f"🎉 ¡COMPLETADO!\n\n"
                mensaje += f"📁 Archivos procesados: {archivos_procesados:,}/{total_archivos:,}\n"
                mensaje += f"📦 Lotes creados: {total_lotes}\n"
                mensaje += f"🔄 Ordenamiento: {metodo}\n"
                mensaje += f"⏱️ Tiempo total: {tiempo_total:.2f} segundos\n"
                mensaje += f"🚀 Velocidad: {velocidad_final:,.0f} archivos/seg\n"
                mensaje += f"💾 Operación: {'Copiado' if self.copiar_archivos.get() else 'Movido'}\n"
                mensaje += f"⚡ Modo: {'EXTREMO' if self.modo_extremo.get() else 'Normal'}"
                self.window.after(0, lambda: messagebox.showinfo("¡Listo!", mensaje))
            else:
                self.window.after(0, lambda: messagebox.showinfo("Cancelado", 
                    f"Operación cancelada.\nProcesados: {archivos_procesados:,} archivos en {tiempo_total:.2f}s"))
                
        except Exception as e:
            import traceback
            error_msg = f"Error: {str(e)}\n\n{traceback.format_exc()}"
            self.window.after(0, lambda: messagebox.showerror("Error", error_msg))
            self.window.after(0, self.finalizar_operacion)
    
    def finalizar_operacion(self):
        """Restaurar estado de la interfaz"""
        self.btn_organizar.config(state=tk.NORMAL)
        self.btn_cancelar.config(state=tk.DISABLED)
        self.progress_var.set(0)
        self.label_velocidad.config(text="")
        self.label_tiempo.config(text="")
        self.actualizar_info()
    
    def run(self):
        """Ejecutar la aplicación"""
        self.window.mainloop()

def main():
    app = OrganizadorArchivos()
    app.run()

if __name__ == "__main__":
    main()