import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import hashlib
from PIL import Image, ImageTk
import shutil
import threading
from collections import defaultdict

class DuplicateImageOrganizer:
    def __init__(self, root):
        self.root = root
        self.root.title("Organizador de Imágenes Duplicadas")
        self.root.geometry("800x600")
        
        # Variables
        self.selected_folder = tk.StringVar()
        self.duplicates = {}
        self.image_hashes = {}
        
        # Formatos de imagen soportados
        self.supported_formats = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
        
        self.setup_ui()
    
    def setup_ui(self):
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configurar el grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # Selección de carpeta
        ttk.Label(main_frame, text="Carpeta a analizar:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        folder_frame = ttk.Frame(main_frame)
        folder_frame.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        folder_frame.columnconfigure(0, weight=1)
        
        self.folder_entry = ttk.Entry(folder_frame, textvariable=self.selected_folder, state='readonly')
        self.folder_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        ttk.Button(folder_frame, text="Seleccionar", command=self.select_folder).grid(row=0, column=1)
        
        # Botones de acción
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=1, column=0, columnspan=3, pady=10)
        
        self.scan_btn = ttk.Button(button_frame, text="Buscar Duplicados", command=self.start_scan)
        self.scan_btn.pack(side=tk.LEFT, padx=5)
        
        self.organize_btn = ttk.Button(button_frame, text="Organizar en Carpetas", 
                                     command=self.organize_duplicates, state='disabled')
        self.organize_btn.pack(side=tk.LEFT, padx=5)
        
        # Barra de progreso
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=1, column=3, sticky=(tk.W, tk.E), padx=(10, 0), pady=10)
        
        # Área de resultados
        results_frame = ttk.LabelFrame(main_frame, text="Duplicados encontrados", padding="5")
        results_frame.grid(row=2, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        
        # Treeview para mostrar duplicados
        columns = ('Grupo', 'Archivo', 'Tamaño', 'Ruta')
        self.tree = ttk.Treeview(results_frame, columns=columns, show='tree headings')
        
        # Configurar columnas
        self.tree.heading('#0', text='')
        self.tree.column('#0', width=20, stretch=False)
        
        for col in columns:
            self.tree.heading(col, text=col)
            if col == 'Ruta':
                self.tree.column(col, width=300)
            elif col == 'Tamaño':
                self.tree.column(col, width=100)
            else:
                self.tree.column(col, width=150)
        
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.tree.yview)
        v_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.tree.configure(yscrollcommand=v_scrollbar.set)
        
        h_scrollbar = ttk.Scrollbar(results_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        h_scrollbar.grid(row=1, column=0, sticky=(tk.W, tk.E))
        self.tree.configure(xscrollcommand=h_scrollbar.set)
        
        # Etiqueta de estado
        self.status_label = ttk.Label(main_frame, text="Selecciona una carpeta para comenzar")
        self.status_label.grid(row=3, column=0, columnspan=4, pady=5)
    
    def select_folder(self):
        folder = filedialog.askdirectory(title="Seleccionar carpeta con imágenes")
        if folder:
            self.selected_folder.set(folder)
            self.status_label.config(text=f"Carpeta seleccionada: {os.path.basename(folder)}")
            # Limpiar resultados anteriores
            self.tree.delete(*self.tree.get_children())
            self.duplicates.clear()
            self.organize_btn.config(state='disabled')
    
    def get_image_hash(self, file_path):
        """Calcula el hash MD5 de una imagen"""
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                return hashlib.md5(content).hexdigest()
        except Exception as e:
            print(f"Error al calcular hash para {file_path}: {e}")
            return None
    
    def is_image_file(self, filename):
        """Verifica si el archivo es una imagen soportada"""
        return os.path.splitext(filename.lower())[1] in self.supported_formats
    
    def scan_for_duplicates(self):
        """Escanea la carpeta en busca de imágenes duplicadas"""
        folder_path = self.selected_folder.get()
        if not folder_path:
            return
        
        self.image_hashes.clear()
        hash_to_files = defaultdict(list)
        total_files = 0
        processed_files = 0
        
        # Contar archivos de imagen
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if self.is_image_file(file):
                    total_files += 1
        
        if total_files == 0:
            self.root.after(0, lambda: self.status_label.config(text="No se encontraron imágenes en la carpeta"))
            self.root.after(0, self.progress.stop)
            return
        
        # Procesar archivos
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if self.is_image_file(file):
                    file_path = os.path.join(root, file)
                    
                    # Actualizar progreso
                    processed_files += 1
                    progress_text = f"Procesando {processed_files}/{total_files}: {file}"
                    self.root.after(0, lambda text=progress_text: self.status_label.config(text=text))
                    
                    # Calcular hash
                    file_hash = self.get_image_hash(file_path)
                    if file_hash:
                        hash_to_files[file_hash].append(file_path)
                        self.image_hashes[file_path] = file_hash
        
        # Filtrar solo los duplicados (hash con más de un archivo)
        self.duplicates = {hash_val: files for hash_val, files in hash_to_files.items() if len(files) > 1}
        
        # Actualizar UI en el hilo principal
        self.root.after(0, self.update_results)
        self.root.after(0, self.progress.stop)
    
    def update_results(self):
        """Actualiza la interfaz con los resultados"""
        self.tree.delete(*self.tree.get_children())
        
        if not self.duplicates:
            self.status_label.config(text="No se encontraron imágenes duplicadas")
            self.organize_btn.config(state='disabled')
            return
        
        # Mostrar duplicados agrupados
        group_num = 1
        total_duplicates = 0
        
        for hash_val, file_list in self.duplicates.items():
            # Crear nodo padre para el grupo
            group_id = self.tree.insert('', 'end', text='', values=(
                f'Grupo {group_num}', f'{len(file_list)} archivos', '', ''
            ))
            
            # Agregar archivos del grupo
            for file_path in file_list:
                try:
                    file_size = os.path.getsize(file_path)
                    file_size_str = f"{file_size:,} bytes"
                    filename = os.path.basename(file_path)
                    
                    self.tree.insert(group_id, 'end', text='', values=(
                        '', filename, file_size_str, file_path
                    ))
                    total_duplicates += 1
                except Exception as e:
                    print(f"Error al obtener info de {file_path}: {e}")
            
            group_num += 1
        
        # Expandir todos los grupos
        for item in self.tree.get_children():
            self.tree.item(item, open=True)
        
        self.status_label.config(text=f"Se encontraron {len(self.duplicates)} grupos de duplicados ({total_duplicates} archivos)")
        self.organize_btn.config(state='normal')
    
    def start_scan(self):
        """Inicia el escaneo en un hilo separado"""
        if not self.selected_folder.get():
            messagebox.showwarning("Advertencia", "Por favor selecciona una carpeta primero")
            return
        
        self.progress.start()
        self.status_label.config(text="Iniciando búsqueda de duplicados...")
        
        # Ejecutar en hilo separado para no bloquear la UI
        thread = threading.Thread(target=self.scan_for_duplicates)
        thread.daemon = True
        thread.start()
    
    def organize_duplicates(self):
        """Organiza los duplicados en carpetas separadas"""
        if not self.duplicates:
            return
        
        folder_path = self.selected_folder.get()
        
        # Confirmar acción
        result = messagebox.askyesno(
            "Confirmar organización",
            f"¿Estás seguro de que quieres organizar {len(self.duplicates)} grupos de duplicados en carpetas separadas?\n\n"
            "Los archivos se moverán a carpetas con nombres 'Folder 1', 'Folder 2', etc."
        )
        
        if not result:
            return
        
        try:
            folder_num = 1
            moved_files = 0
            
            for hash_val, file_list in self.duplicates.items():
                # Crear carpeta para este grupo
                duplicate_folder = os.path.join(folder_path, f"Folder {folder_num}")
                os.makedirs(duplicate_folder, exist_ok=True)
                
                # Mover archivos a la carpeta
                for file_path in file_list:
                    if os.path.exists(file_path):
                        filename = os.path.basename(file_path)
                        destination = os.path.join(duplicate_folder, filename)
                        
                        # Si ya existe un archivo con el mismo nombre, agregar número
                        counter = 1
                        base_name, ext = os.path.splitext(filename)
                        while os.path.exists(destination):
                            new_filename = f"{base_name}_{counter}{ext}"
                            destination = os.path.join(duplicate_folder, new_filename)
                            counter += 1
                        
                        shutil.move(file_path, destination)
                        moved_files += 1
                
                folder_num += 1
            
            messagebox.showinfo(
                "Organización completada",
                f"Se organizaron {moved_files} archivos duplicados en {len(self.duplicates)} carpetas"
            )
            
            # Limpiar resultados
            self.tree.delete(*self.tree.get_children())
            self.duplicates.clear()
            self.organize_btn.config(state='disabled')
            self.status_label.config(text="Organización completada. Puedes buscar duplicados nuevamente.")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al organizar archivos: {str(e)}")

def main():
    root = tk.Tk()
    app = DuplicateImageOrganizer(root)
    root.mainloop()

if __name__ == "__main__":
    main()