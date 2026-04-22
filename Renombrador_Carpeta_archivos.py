import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

class RenombradorArchivos:
    def __init__(self, root):
        self.root = root
        self.root.title("Renombrador de Archivos Multimedia Pro")
        self.root.geometry("900x650")
        
        # Extensiones soportadas organizadas por categoría
        self.extensiones_soportadas = {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
            '.webp', '.heic', '.heif', '.svg',
            '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm',
            '.m4v', '.mpg', '.mpeg', '.3gp',
            '.raw', '.cr2', '.nef', '.arw', '.dng', '.orf', '.rw2',
            '.pef', '.srw', '.raf'
        }
        
        self.carpeta_seleccionada = None
        self.cambios_propuestos = []
        self.cancelar_operacion = False
        self.crear_interfaz()
    
    def crear_interfaz(self):
        # Frame superior para selección de carpeta
        frame_superior = ttk.Frame(self.root, padding="10")
        frame_superior.pack(fill=tk.X)
        
        ttk.Label(frame_superior, text="Carpeta principal:").pack(side=tk.LEFT, padx=5)
        
        self.entry_carpeta = ttk.Entry(frame_superior, width=50)
        self.entry_carpeta.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        ttk.Button(frame_superior, text="Seleccionar", 
                   command=self.seleccionar_carpeta).pack(side=tk.LEFT, padx=5)
        
        # Frame de opciones
        frame_opciones = ttk.LabelFrame(self.root, text="Opciones", padding="10")
        frame_opciones.pack(fill=tk.X, padx=10, pady=5)
        
        # Primera fila de opciones
        fila1 = ttk.Frame(frame_opciones)
        fila1.pack(fill=tk.X, pady=2)
        
        self.var_preview = tk.BooleanVar(value=True)
        ttk.Checkbutton(fila1, text="Vista previa antes de renombrar", 
                        variable=self.var_preview).pack(side=tk.LEFT, padx=10)
        
        self.var_subcarpetas = tk.BooleanVar(value=True)
        ttk.Checkbutton(fila1, text="Incluir subcarpetas", 
                        variable=self.var_subcarpetas).pack(side=tk.LEFT, padx=10)
        
        # Segunda fila de opciones
        fila2 = ttk.Frame(frame_opciones)
        fila2.pack(fill=tk.X, pady=2)
        
        self.var_log_detallado = tk.BooleanVar(value=False)
        ttk.Checkbutton(fila2, text="Log detallado (más lento)", 
                        variable=self.var_log_detallado).pack(side=tk.LEFT, padx=10)
        
        self.var_mantener_originales = tk.BooleanVar(value=False)
        ttk.Checkbutton(fila2, text="Preservar nombres si ya están correctos", 
                        variable=self.var_mantener_originales).pack(side=tk.LEFT, padx=10)
        
        # Frame de estadísticas
        frame_stats = ttk.LabelFrame(self.root, text="Estadísticas", padding="10")
        frame_stats.pack(fill=tk.X, padx=10, pady=5)
        
        self.label_stats = ttk.Label(frame_stats, text="Carpetas: 0 | Archivos encontrados: 0 | Cambios propuestos: 0")
        self.label_stats.pack()
        
        # Frame de botones
        frame_botones = ttk.Frame(self.root, padding="10")
        frame_botones.pack(fill=tk.X)
        
        self.btn_analizar = ttk.Button(frame_botones, text="🔍 Analizar", 
                                        command=self.analizar_carpetas)
        self.btn_analizar.pack(side=tk.LEFT, padx=5)
        
        self.btn_renombrar = ttk.Button(frame_botones, text="✏️ Renombrar", 
                                         command=self.renombrar_archivos, 
                                         state=tk.DISABLED)
        self.btn_renombrar.pack(side=tk.LEFT, padx=5)
        
        self.btn_cancelar = ttk.Button(frame_botones, text="🛑 Cancelar", 
                                        command=self.cancelar,
                                        state=tk.DISABLED)
        self.btn_cancelar.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(frame_botones, text="🧹 Limpiar", 
                   command=self.limpiar).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(frame_botones, text="💾 Exportar Log", 
                   command=self.exportar_log).pack(side=tk.LEFT, padx=5)
        
        # Área de texto para mostrar resultados
        frame_texto = ttk.LabelFrame(self.root, text="Registro", padding="10")
        frame_texto.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.texto_log = scrolledtext.ScrolledText(frame_texto, 
                                                     wrap=tk.WORD, 
                                                     height=20,
                                                     font=("Consolas", 9))
        self.texto_log.pack(fill=tk.BOTH, expand=True)
        
        # Barra de progreso
        self.progress = ttk.Progressbar(self.root, mode='determinate')
        self.progress.pack(fill=tk.X, padx=10, pady=5)
        
        self.label_progreso = ttk.Label(self.root, text="")
        self.label_progreso.pack()
    
    def seleccionar_carpeta(self):
        carpeta = filedialog.askdirectory(title="Seleccionar carpeta principal")
        if carpeta:
            self.carpeta_seleccionada = carpeta
            self.entry_carpeta.delete(0, tk.END)
            self.entry_carpeta.insert(0, carpeta)
            self.log(f"📂 Carpeta seleccionada: {carpeta}\n")
    
    def log(self, mensaje, actualizar=True):
        """Agrega mensaje al log de manera thread-safe"""
        self.root.after(0, self._log_safe, mensaje, actualizar)
    
    def _log_safe(self, mensaje, actualizar):
        """Método seguro para actualizar el log desde el hilo principal"""
        self.texto_log.insert(tk.END, mensaje)
        if actualizar:
            self.texto_log.see(tk.END)
            self.root.update_idletasks()
    
    def actualizar_stats(self, carpetas=0, archivos=0, cambios=0):
        """Actualiza las estadísticas en la interfaz"""
        self.root.after(0, self._actualizar_stats_safe, carpetas, archivos, cambios)
    
    def _actualizar_stats_safe(self, carpetas, archivos, cambios):
        self.label_stats.config(
            text=f"Carpetas: {carpetas} | Archivos encontrados: {archivos} | Cambios propuestos: {cambios}"
        )
    
    def limpiar(self):
        self.texto_log.delete(1.0, tk.END)
        self.cambios_propuestos = []
        self.btn_renombrar.config(state=tk.DISABLED)
        self.progress['value'] = 0
        self.label_progreso.config(text="")
        self.actualizar_stats(0, 0, 0)
    
    def cancelar(self):
        self.cancelar_operacion = True
        self.log("\n⚠️ Cancelación solicitada...\n")
    
    def exportar_log(self):
        """Exporta el contenido del log a un archivo de texto"""
        archivo = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Archivos de texto", "*.txt"), ("Todos los archivos", "*.*")]
        )
        if archivo:
            try:
                with open(archivo, 'w', encoding='utf-8') as f:
                    f.write(self.texto_log.get(1.0, tk.END))
                messagebox.showinfo("Éxito", "Log exportado correctamente")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo exportar el log: {str(e)}")
    
    def obtener_nuevo_nombre(self, nombre_base, extension, nombres_usados):
        """Genera un nombre único para el archivo de forma optimizada"""
        nuevo_nombre = f"{nombre_base}{extension}"
        
        if nuevo_nombre not in nombres_usados:
            return nuevo_nombre
        
        # Búsqueda binaria optimizada para encontrar el siguiente número disponible
        contador = 1
        while f"{nombre_base}({contador}){extension}" in nombres_usados:
            contador += 1
        
        return f"{nombre_base}({contador}){extension}"
    
    def procesar_carpeta(self, subcarpeta, nombre_carpeta):
        """Procesa una carpeta individual y retorna los cambios propuestos"""
        cambios_locales = []
        
        try:
            # Obtener archivos de forma optimizada
            archivos = [
                f for f in subcarpeta.iterdir() 
                if f.is_file() and f.suffix.lower() in self.extensiones_soportadas
            ]
            
            if not archivos:
                return cambios_locales, 0
            
            # Obtener archivos existentes en la carpeta de una sola vez
            archivos_existentes = {f.name for f in subcarpeta.iterdir() if f.is_file()}
            
            # Agrupar por extensión para procesamiento más eficiente
            archivos_por_extension = defaultdict(list)
            for archivo in archivos:
                archivos_por_extension[archivo.suffix.lower()].append(archivo)
            
            # Procesar cada grupo de extensión
            for extension, grupo_archivos in archivos_por_extension.items():
                nombres_usados = {f for f in archivos_existentes if f.endswith(extension)}
                
                for archivo in grupo_archivos:
                    if self.cancelar_operacion:
                        break
                        
                    nombre_actual = archivo.name
                    
                    # Verificar si el archivo ya tiene el formato correcto
                    if self.var_mantener_originales.get():
                        if nombre_actual.startswith(nombre_carpeta):
                            continue
                    
                    # Generar nuevo nombre
                    nuevo_nombre = self.obtener_nuevo_nombre(
                        nombre_carpeta, 
                        extension,
                        nombres_usados
                    )
                    
                    # Agregar a nombres usados
                    nombres_usados.add(nuevo_nombre)
                    
                    # Solo agregar si el nombre cambia
                    if nombre_actual != nuevo_nombre:
                        cambios_locales.append({
                            'carpeta': nombre_carpeta,
                            'ruta_actual': str(archivo),
                            'ruta_nueva': str(subcarpeta / nuevo_nombre),
                            'nombre_actual': nombre_actual,
                            'nombre_nuevo': nuevo_nombre
                        })
            
            return cambios_locales, len(archivos)
            
        except Exception as e:
            self.log(f"⚠️ Error procesando {nombre_carpeta}: {str(e)}\n")
            return cambios_locales, 0
    
    def analizar_carpetas(self):
        if not self.carpeta_seleccionada:
            messagebox.showwarning("Advertencia", 
                                   "Por favor selecciona una carpeta primero")
            return
        
        self.limpiar()
        self.cancelar_operacion = False
        self.btn_analizar.config(state=tk.DISABLED)
        self.btn_cancelar.config(state=tk.NORMAL)
        
        thread = threading.Thread(target=self._analizar_carpetas_thread)
        thread.daemon = True
        thread.start()
    
    def _analizar_carpetas_thread(self):
        try:
            self.cambios_propuestos = []
            total_archivos = 0
            
            carpeta_principal = Path(self.carpeta_seleccionada)
            
            # Obtener subcarpetas
            if self.var_subcarpetas.get():
                subcarpetas = [d for d in carpeta_principal.iterdir() if d.is_dir()]
            else:
                subcarpetas = [carpeta_principal]
            
            if not subcarpetas:
                self.log("⚠️ No se encontraron carpetas para procesar\n")
                return
            
            total_carpetas = len(subcarpetas)
            self.log(f"🔍 Analizando {total_carpetas} carpeta(s)...\n\n")
            
            # Procesar carpetas en paralelo para mayor velocidad
            max_workers = min(8, os.cpu_count() or 4)
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Crear futures para cada carpeta
                futures = {
                    executor.submit(self.procesar_carpeta, subcarpeta, subcarpeta.name): subcarpeta 
                    for subcarpeta in subcarpetas
                }
                
                carpetas_procesadas = 0
                
                # Procesar resultados a medida que se completan
                for future in as_completed(futures):
                    if self.cancelar_operacion:
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    
                    try:
                        cambios, num_archivos = future.result()
                        self.cambios_propuestos.extend(cambios)
                        total_archivos += num_archivos
                        carpetas_procesadas += 1
                        
                        # Actualizar progreso
                        progreso = (carpetas_procesadas / total_carpetas) * 100
                        self.root.after(0, self.progress.config, {'value': progreso})
                        self.root.after(0, self.label_progreso.config, 
                                      {'text': f"Procesando: {carpetas_procesadas}/{total_carpetas} carpetas"})
                        
                        # Log detallado opcional
                        if self.var_log_detallado.get() and cambios:
                            subcarpeta = futures[future]
                            self.log(f"📁 {subcarpeta.name}/ ({len(cambios)} cambios)\n")
                            for cambio in cambios[:5]:  # Mostrar solo primeros 5
                                self.log(f"  ➜ {cambio['nombre_actual']} → {cambio['nombre_nuevo']}\n")
                            if len(cambios) > 5:
                                self.log(f"  ... y {len(cambios) - 5} más\n")
                            self.log("\n")
                        
                    except Exception as e:
                        self.log(f"❌ Error: {str(e)}\n")
                
                self.actualizar_stats(total_carpetas, total_archivos, len(self.cambios_propuestos))
            
            if self.cancelar_operacion:
                self.log(f"\n⚠️ Análisis cancelado\n")
                self.log(f"Carpetas procesadas: {carpetas_procesadas}/{total_carpetas}\n")
            else:
                self.log(f"\n{'='*70}\n")
                self.log(f"✅ Análisis completado\n")
                self.log(f"📊 Estadísticas:\n")
                self.log(f"   • Carpetas analizadas: {total_carpetas}\n")
                self.log(f"   • Archivos encontrados: {total_archivos}\n")
                self.log(f"   • Archivos a renombrar: {len(self.cambios_propuestos)}\n")
            
            if len(self.cambios_propuestos) > 0 and not self.cancelar_operacion:
                self.root.after(0, self.btn_renombrar.config, {'state': tk.NORMAL})
            
        except Exception as e:
            self.log(f"\n❌ Error crítico: {str(e)}\n")
        
        finally:
            self.root.after(0, self.progress.config, {'value': 0})
            self.root.after(0, self.label_progreso.config, {'text': ''})
            self.root.after(0, self.btn_analizar.config, {'state': tk.NORMAL})
            self.root.after(0, self.btn_cancelar.config, {'state': tk.DISABLED})
            self.cancelar_operacion = False
    
    def renombrar_archivos(self):
        if not self.cambios_propuestos:
            messagebox.showinfo("Info", "No hay archivos para renombrar")
            return
        
        if self.var_preview.get():
            respuesta = messagebox.askyesno(
                "Confirmar", 
                f"¿Deseas renombrar {len(self.cambios_propuestos)} archivo(s)?\n\n"
                f"Esta acción no se puede deshacer."
            )
            if not respuesta:
                return
        
        self.cancelar_operacion = False
        self.btn_renombrar.config(state=tk.DISABLED)
        self.btn_cancelar.config(state=tk.NORMAL)
        
        thread = threading.Thread(target=self._renombrar_archivos_thread)
        thread.daemon = True
        thread.start()
    
    def _renombrar_archivos_thread(self):
        try:
            self.log(f"\n{'='*70}\n")
            self.log("🔄 Iniciando renombrado...\n\n")
            
            exitosos = 0
            errores = 0
            total = len(self.cambios_propuestos)
            
            # Agrupar cambios por carpeta para mejor organización
            cambios_por_carpeta = defaultdict(list)
            for cambio in self.cambios_propuestos:
                cambios_por_carpeta[cambio['carpeta']].append(cambio)
            
            archivos_procesados = 0
            
            for carpeta, cambios in cambios_por_carpeta.items():
                if self.cancelar_operacion:
                    break
                
                if self.var_log_detallado.get():
                    self.log(f"\n📁 Procesando: {carpeta}/\n")
                
                for cambio in cambios:
                    if self.cancelar_operacion:
                        break
                    
                    try:
                        os.rename(cambio['ruta_actual'], cambio['ruta_nueva'])
                        exitosos += 1
                        
                        if self.var_log_detallado.get():
                            self.log(f"  ✓ {cambio['nombre_actual']} → {cambio['nombre_nuevo']}\n")
                        
                    except Exception as e:
                        errores += 1
                        self.log(f"  ✗ Error: {cambio['nombre_actual']}: {str(e)}\n")
                    
                    archivos_procesados += 1
                    progreso = (archivos_procesados / total) * 100
                    self.root.after(0, self.progress.config, {'value': progreso})
                    self.root.after(0, self.label_progreso.config, 
                                  {'text': f"Renombrando: {archivos_procesados}/{total}"})
            
            self.log(f"\n{'='*70}\n")
            if self.cancelar_operacion:
                self.log(f"⚠️ Renombrado cancelado\n")
            else:
                self.log(f"✅ Proceso completado\n")
            
            self.log(f"📊 Resultados:\n")
            self.log(f"   • Exitosos: {exitosos}\n")
            self.log(f"   • Errores: {errores}\n")
            self.log(f"   • Total procesado: {archivos_procesados}/{total}\n")
            
            if not self.cancelar_operacion:
                self.root.after(0, messagebox.showinfo, "Completado", 
                               f"Renombrado completado\n\n"
                               f"✓ Exitosos: {exitosos}\n"
                               f"✗ Errores: {errores}")
            
            self.cambios_propuestos = []
            
        except Exception as e:
            self.log(f"\n❌ Error crítico: {str(e)}\n")
            self.root.after(0, messagebox.showerror, "Error", f"Error crítico: {str(e)}")
        
        finally:
            self.root.after(0, self.progress.config, {'value': 0})
            self.root.after(0, self.label_progreso.config, {'text': ''})
            self.root.after(0, self.btn_cancelar.config, {'state': tk.DISABLED})
            self.cancelar_operacion = False

if __name__ == "__main__":
    root = tk.Tk()
    app = RenombradorArchivos(root)
    root.mainloop()