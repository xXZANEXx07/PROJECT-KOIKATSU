import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import threading
from typing import List, Tuple, Optional

class FolderRenamer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Contador y Renombrador de Carpetas")
        self.root.geometry("500x400")
        self.root.resizable(True, True)
        
        # Variables
        self.selected_folder = tk.StringVar()
        self.processing = False
        
        self.setup_ui()
        
    def setup_ui(self):
        """Configura la interfaz de usuario"""
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configurar peso de las columnas y filas
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Título
        title_label = ttk.Label(main_frame, text="Renombrador de Carpetas", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Selección de carpeta
        ttk.Label(main_frame, text="Carpeta seleccionada:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        folder_entry = ttk.Entry(main_frame, textvariable=self.selected_folder, state="readonly")
        folder_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(5, 5), pady=5)
        
        select_btn = ttk.Button(main_frame, text="Seleccionar", command=self.select_folder)
        select_btn.grid(row=1, column=2, padx=(5, 0), pady=5)
        
        # Opciones
        options_frame = ttk.LabelFrame(main_frame, text="Opciones", padding="10")
        options_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        options_frame.columnconfigure(0, weight=1)
        
        self.sort_ascending = tk.BooleanVar(value=True)
        ttk.Radiobutton(options_frame, text="Ordenar de menor a mayor cantidad", 
                       variable=self.sort_ascending, value=True).grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(options_frame, text="Ordenar de mayor a menor cantidad", 
                       variable=self.sort_ascending, value=False).grid(row=1, column=0, sticky=tk.W)
        
        self.include_files = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Incluir archivos en el conteo", 
                       variable=self.include_files).grid(row=2, column=0, sticky=tk.W, pady=(10, 0))
        
        self.preview_mode = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Solo vista previa (no renombrar)", 
                       variable=self.preview_mode).grid(row=3, column=0, sticky=tk.W)
        
        # Botones de acción
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=20)
        
        self.process_btn = ttk.Button(button_frame, text="Procesar Carpetas", 
                                     command=self.process_folders_threaded, state="disabled")
        self.process_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.reset_btn = ttk.Button(button_frame, text="Restaurar Nombres", 
                                   command=self.restore_names, state="disabled")
        self.reset_btn.pack(side=tk.LEFT)
        
        # Barra de progreso
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        # Área de texto para mostrar resultados
        text_frame = ttk.LabelFrame(main_frame, text="Resultados", padding="5")
        text_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(5, weight=1)
        
        self.result_text = tk.Text(text_frame, height=10, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=scrollbar.set)
        
        self.result_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
    def select_folder(self):
        """Selecciona la carpeta a procesar"""
        folder = filedialog.askdirectory()
        if folder:
            self.selected_folder.set(folder)
            self.process_btn.config(state="normal")
            self.reset_btn.config(state="normal")
            self.log_message(f"Carpeta seleccionada: {folder}")
            
    def count_items_in_folder(self, folder_path: Path) -> int:
        """Cuenta elementos en una carpeta con mejor manejo de errores"""
        try:
            if not folder_path.exists():
                self.log_message(f"Advertencia: La carpeta {folder_path} no existe")
                return 0
            
            if not folder_path.is_dir():
                self.log_message(f"Advertencia: {folder_path} no es una carpeta")
                return 0
            
            # Verificar permisos de lectura
            if not os.access(folder_path, os.R_OK):
                self.log_message(f"Advertencia: Sin permisos para leer {folder_path}")
                return 0
            
            count = 0
            items_processed = 0
            
            try:
                # Usar os.listdir en lugar de iterdir para mejor compatibilidad
                items = os.listdir(folder_path)
                
                for item_name in items:
                    try:
                        item_path = folder_path / item_name
                        
                        if self.include_files.get():
                            # Contar tanto archivos como carpetas
                            if item_path.exists():
                                count += 1
                                items_processed += 1
                        else:
                            # Solo contar carpetas
                            if item_path.is_dir():
                                count += 1
                                items_processed += 1
                                
                    except (OSError, PermissionError) as e:
                        # Continuar con el siguiente elemento si hay error con uno específico
                        self.log_message(f"Advertencia: Error accediendo a {item_name}: {e}")
                        continue
                        
            except (OSError, PermissionError) as e:
                self.log_message(f"Error listando contenido de {folder_path}: {e}")
                return 0
            
            return count
            
        except Exception as e:
            self.log_message(f"Error inesperado contando elementos en {folder_path}: {e}")
            return 0
    
    def get_folder_info(self, root_folder: Path) -> List[Tuple[str, int, Path]]:
        """Obtiene información de las subcarpetas con mejor manejo de errores"""
        folders_info = []
        
        try:
            if not root_folder.exists():
                self.log_message(f"Error: La carpeta {root_folder} no existe")
                return []
            
            if not root_folder.is_dir():
                self.log_message(f"Error: {root_folder} no es una carpeta")
                return []
            
            # Verificar permisos
            if not os.access(root_folder, os.R_OK):
                self.log_message(f"Error: Sin permisos para leer {root_folder}")
                return []
            
            self.log_message("Escaneando subcarpetas...")
            
            try:
                # Usar os.listdir para mejor compatibilidad
                items = os.listdir(root_folder)
                
                for item_name in items:
                    try:
                        item_path = root_folder / item_name
                        
                        if item_path.is_dir():
                            self.log_message(f"Contando elementos en: {item_name}")
                            count = self.count_items_in_folder(item_path)
                            folders_info.append((item_name, count, item_path))
                            
                    except (OSError, PermissionError) as e:
                        self.log_message(f"Error accediendo a {item_name}: {e}")
                        continue
                        
            except (OSError, PermissionError) as e:
                self.log_message(f"Error listando contenido de {root_folder}: {e}")
                return []
                
        except Exception as e:
            self.log_message(f"Error inesperado accediendo a la carpeta: {e}")
            return []
        
        if not folders_info:
            self.log_message("No se encontraron subcarpetas válidas")
            return []
        
        # Ordenar según la opción seleccionada
        folders_info.sort(key=lambda x: x[1], reverse=not self.sort_ascending.get())
        
        self.log_message(f"Se encontraron {len(folders_info)} subcarpetas")
        return folders_info
    
    def process_folders_threaded(self):
        """Ejecuta el procesamiento en un hilo separado"""
        if not self.processing:
            self.processing = True
            self.progress.start()
            self.process_btn.config(state="disabled")
            
            thread = threading.Thread(target=self.process_folders)
            thread.daemon = True
            thread.start()
    
    def process_folders(self):
        """Procesa las carpetas (renombra o muestra vista previa)"""
        try:
            folder_path = Path(self.selected_folder.get())
            
            if not folder_path.exists():
                self.log_message("Error: La carpeta seleccionada no existe.")
                self.finish_processing()
                return
            
            self.log_message("Iniciando procesamiento...")
            self.log_message("-" * 50)
            
            folders_info = self.get_folder_info(folder_path)
            
            if not folders_info:
                self.log_message("No se encontraron subcarpetas para procesar.")
                self.finish_processing()
                return
            
            success_count = 0
            error_count = 0
            
            for i, (original_name, count, folder_path_obj) in enumerate(folders_info, 1):
                try:
                    # Crear el nuevo nombre
                    count_text = "elementos" if self.include_files.get() else "carpetas"
                    new_name = f"{i}. {original_name} ({count} {count_text})"
                    new_path = folder_path_obj.parent / new_name
                    
                    if self.preview_mode.get():
                        # Solo mostrar vista previa
                        self.log_message(f"Vista previa: '{original_name}' → '{new_name}'")
                        success_count += 1
                    else:
                        # Renombrar realmente
                        if folder_path_obj.name == new_name:
                            self.log_message(f"Sin cambios: '{original_name}' (ya tiene el nombre correcto)")
                            success_count += 1
                        else:
                            try:
                                # Verificar que el nuevo nombre no exista
                                if new_path.exists():
                                    self.log_message(f"Error: Ya existe una carpeta con el nombre '{new_name}'")
                                    error_count += 1
                                    continue
                                
                                folder_path_obj.rename(new_path)
                                self.log_message(f"Renombrado: '{original_name}' → '{new_name}'")
                                success_count += 1
                                
                            except Exception as e:
                                self.log_message(f"Error renombrando '{original_name}': {e}")
                                error_count += 1
                                
                except Exception as e:
                    self.log_message(f"Error procesando '{original_name}': {e}")
                    error_count += 1
            
            self.log_message("-" * 50)
            mode_text = "Vista previa completada" if self.preview_mode.get() else "Renombrado completado"
            self.log_message(f"{mode_text}: {success_count} exitosos, {error_count} errores")
            
        except Exception as e:
            self.log_message(f"Error inesperado durante el procesamiento: {e}")
        
        finally:
            self.finish_processing()
    
    def restore_names(self):
        """Restaura los nombres originales removiendo la numeración"""
        try:
            folder_path = Path(self.selected_folder.get())
            
            if not folder_path.exists():
                self.log_message("Error: La carpeta seleccionada no existe.")
                return
            
            self.log_message("Restaurando nombres originales...")
            self.log_message("-" * 50)
            
            success_count = 0
            error_count = 0
            
            try:
                items = os.listdir(folder_path)
                
                for item_name in items:
                    try:
                        item_path = folder_path / item_name
                        
                        if item_path.is_dir():
                            # Buscar patrón "numero. nombre (cantidad elementos/carpetas)"
                            if '. ' in item_name and ' (' in item_name:
                                # Más flexible para diferentes tipos de conteo
                                if item_name.endswith(' elementos)') or item_name.endswith(' carpetas)'):
                                    # Extraer nombre original
                                    start_index = item_name.find('. ') + 2
                                    end_index = item_name.rfind(' (')
                                    
                                    if start_index < end_index:
                                        original_name = item_name[start_index:end_index]
                                        new_path = folder_path / original_name
                                        
                                        # Verificar que el nombre original no exista ya
                                        if new_path.exists() and new_path != item_path:
                                            self.log_message(f"Error: Ya existe una carpeta con el nombre '{original_name}'")
                                            error_count += 1
                                            continue
                                        
                                        try:
                                            item_path.rename(new_path)
                                            self.log_message(f"Restaurado: '{item_name}' → '{original_name}'")
                                            success_count += 1
                                        except Exception as e:
                                            self.log_message(f"Error restaurando '{item_name}': {e}")
                                            error_count += 1
                                            
                    except Exception as e:
                        self.log_message(f"Error procesando '{item_name}': {e}")
                        error_count += 1
                        
            except Exception as e:
                self.log_message(f"Error accediendo a la carpeta: {e}")
            
            self.log_message("-" * 50)
            self.log_message(f"Restauración completada: {success_count} exitosos, {error_count} errores")
            
        except Exception as e:
            self.log_message(f"Error inesperado durante la restauración: {e}")
    
    def log_message(self, message: str):
        """Agrega un mensaje al área de texto"""
        def update_ui():
            self.result_text.insert(tk.END, message + "\n")
            self.result_text.see(tk.END)
            self.root.update_idletasks()
        
        # Asegurar que la actualización de UI se ejecute en el hilo principal
        if threading.current_thread() == threading.main_thread():
            update_ui()
        else:
            self.root.after(0, update_ui)
    
    def finish_processing(self):
        """Finaliza el procesamiento"""
        def update_ui():
            self.processing = False
            self.progress.stop()
            self.process_btn.config(state="normal")
        
        # Asegurar que la actualización de UI se ejecute en el hilo principal
        if threading.current_thread() == threading.main_thread():
            update_ui()
        else:
            self.root.after(0, update_ui)
    
    def run(self):
        """Ejecuta la aplicación"""
        self.root.mainloop()

if __name__ == "__main__":
    app = FolderRenamer()
    app.run()