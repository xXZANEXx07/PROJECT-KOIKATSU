import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import os
import shutil
import re

class ImageOrganizer:
    def __init__(self, root):
        self.root = root
        self.root.title("Organizador Automático de Imágenes y Videos")
        self.root.geometry("900x750")
        
        # Variables
        self.images = []
        self.current_index = 0
        self.source_folder = ""
        self.folder_mapping = {}  # Mapeo de imagen -> carpeta detectada
        self.preview_mode = True
        
        # Configurar GUI
        self.setup_gui()
        
    def setup_gui(self):
        # Frame superior para controles
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)
        
        # Botón para seleccionar carpeta
        ttk.Button(top_frame, text="Seleccionar Carpeta", 
                  command=self.select_folder).pack(side=tk.LEFT, padx=5)
        
        # Label para mostrar carpeta actual
        self.folder_label = ttk.Label(top_frame, text="No hay carpeta seleccionada")
        self.folder_label.pack(side=tk.LEFT, padx=10)
        
        # Contador de imágenes
        self.counter_label = ttk.Label(top_frame, text="0/0")
        self.counter_label.pack(side=tk.RIGHT, padx=5)
        
        # Frame para vista previa de organización
        preview_frame = ttk.LabelFrame(self.root, text="Vista Previa de Organización", 
                                       padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Scrollbar y Listbox
        scrollbar = ttk.Scrollbar(preview_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.preview_listbox = tk.Listbox(preview_frame, 
                                          yscrollcommand=scrollbar.set,
                                          font=("Consolas", 9),
                                          height=15)
        self.preview_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.preview_listbox.yview)
        
        # Frame para imagen seleccionada
        image_frame = ttk.LabelFrame(self.root, text="Archivo Actual", padding="10")
        image_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Canvas para mostrar imagen
        self.canvas = tk.Canvas(image_frame, bg="gray", height=250)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Label para nombre del archivo
        self.filename_label = ttk.Label(image_frame, text="", font=("Arial", 10, "bold"))
        self.filename_label.pack(pady=5)
        
        # Frame inferior para controles
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(fill=tk.X)
        
        # Label y Entry para editar carpeta detectada
        ttk.Label(bottom_frame, text="Carpeta destino:").pack(side=tk.LEFT, padx=5)
        
        self.folder_entry = ttk.Entry(bottom_frame, width=30, font=("Arial", 11))
        self.folder_entry.pack(side=tk.LEFT, padx=5)
        self.folder_entry.bind('<Return>', lambda e: self.move_current_image())
        
        # Botones de acción
        ttk.Button(bottom_frame, text="Mover Esta (Enter)", 
                  command=self.move_current_image).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(bottom_frame, text="Organizar Todas", 
                  command=self.organize_all,
                  style="Accent.TButton").pack(side=tk.LEFT, padx=10)
        
        # Navegación
        nav_frame = ttk.Frame(self.root, padding="5")
        nav_frame.pack(fill=tk.X)
        
        ttk.Button(nav_frame, text="← Anterior", 
                  command=self.previous_image).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(nav_frame, text="Siguiente →", 
                  command=self.next_image).pack(side=tk.LEFT, padx=5)
        
        # Atajos de teclado
        self.root.bind('<Right>', lambda e: self.next_image())
        self.root.bind('<Left>', lambda e: self.previous_image())
        self.preview_listbox.bind('<<ListboxSelect>>', self.on_listbox_select)
        
    def select_folder(self):
        folder = filedialog.askdirectory(title="Seleccionar carpeta con imágenes/videos")
        if folder:
            self.source_folder = folder
            self.load_images()
            self.folder_label.config(text=f"Carpeta: {os.path.basename(folder)}")
            
    def load_images(self):
        # Extensiones soportadas
        image_extensions = (
            # Formatos estándar
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif',
            '.ico', '.jfif', '.pjpeg', '.pjp', '.svg', '.heic', '.heif',
            # Formatos RAW
            '.raw', '.cr2', '.cr3', '.nef', '.arw', '.dng', '.orf', '.rw2',
            '.pef', '.srw', '.raf', '.3fr', '.fff', '.dcr', '.kdc', '.mrw',
            '.mos', '.nrw', '.ptx', '.r3d', '.rwl', '.rwz', '.x3f', '.erf',
            '.mef', '.srf', '.sr2', '.iiq', '.crw'
        )
        
        video_extensions = (
            # Formatos de video populares
            '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v',
            '.mpg', '.mpeg', '.3gp', '.3g2', '.f4v', '.swf', '.avchd', '.mts',
            '.m2ts', '.ts', '.vob', '.ogv', '.ogg', '.drc', '.gifv', '.mng',
            '.qt', '.yuv', '.rm', '.rmvb', '.asf', '.amv', '.mp2', '.mpe',
            '.mpv', '.m2v', '.svi', '.mxf', '.roq', '.nsv', '.divx'
        )
        
        all_extensions = image_extensions + video_extensions
        
        # Cargar todas las imágenes y videos de la carpeta (solo raíz, no subcarpetas)
        self.images = []
        try:
            for file in os.listdir(self.source_folder):
                file_path = os.path.join(self.source_folder, file)
                # Solo archivos (no carpetas) y con extensión válida
                if os.path.isfile(file_path) and file.lower().endswith(all_extensions):
                    self.images.append(file)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer la carpeta: {e}")
            return
        
        self.images.sort()
        self.current_index = 0
        
        if self.images:
            # Detectar carpetas para cada imagen/video
            self.detect_folders()
            self.update_preview_list()
            self.show_image()
            
            # Contar tipos de archivos
            img_count = sum(1 for f in self.images if f.lower().endswith(image_extensions))
            vid_count = sum(1 for f in self.images if f.lower().endswith(video_extensions))
            
            messagebox.showinfo("Carga completa", 
                              f"Se encontraron:\n"
                              f"• {img_count} imágenes (incluyendo RAW)\n"
                              f"• {vid_count} videos\n"
                              f"• Total: {len(self.images)} archivos\n\n"
                              f"Detectadas {len(set(self.folder_mapping.values()))} carpetas diferentes")
        else:
            messagebox.showwarning("Sin archivos", 
                                 "No se encontraron imágenes ni videos en la carpeta raíz")
            
    def detect_folders(self):
        """Detecta el nombre de la carpeta basándose en el nombre del archivo"""
        self.folder_mapping = {}
        
        for filename in self.images:
            # Remover extensión
            name_without_ext = os.path.splitext(filename)[0]
            
            # Patrones para detectar el nombre base
            # Patrón 1: "Nombre (123)" -> "Nombre"
            match = re.match(r'^(.+?)\s*\(\d+\)$', name_without_ext)
            if match:
                folder_name = match.group(1).strip()
            else:
                # Patrón 2: "Nombre - 123" -> "Nombre"
                match = re.match(r'^(.+?)\s*-\s*\d+$', name_without_ext)
                if match:
                    folder_name = match.group(1).strip()
                else:
                    # Patrón 3: "Nombre_123" -> "Nombre"
                    match = re.match(r'^(.+?)_\d+$', name_without_ext)
                    if match:
                        folder_name = match.group(1).strip()
                    else:
                        # Patrón 4: "Nombre 123" -> "Nombre"
                        match = re.match(r'^(.+?)\s+\d+$', name_without_ext)
                        if match:
                            folder_name = match.group(1).strip()
                        else:
                            # Si no coincide con ningún patrón, usar el nombre completo
                            folder_name = name_without_ext
            
            self.folder_mapping[filename] = folder_name
            
    def update_preview_list(self):
        """Actualiza la lista de vista previa"""
        self.preview_listbox.delete(0, tk.END)
        
        for i, filename in enumerate(self.images):
            folder = self.folder_mapping.get(filename, "Sin clasificar")
            
            # Añadir indicador de tipo de archivo
            file_type = self.get_file_type(filename)
            display_text = f"[{folder}] ← {filename} ({file_type})"
            
            self.preview_listbox.insert(tk.END, display_text)
            
            # Resaltar la imagen actual
            if i == self.current_index:
                self.preview_listbox.itemconfig(i, bg='lightblue')
    
    def get_file_type(self, filename):
        """Determina el tipo de archivo"""
        ext = filename.lower()
        
        raw_extensions = ('.raw', '.cr2', '.cr3', '.nef', '.arw', '.dng', '.orf', 
                         '.rw2', '.pef', '.srw', '.raf', '.3fr', '.fff', '.dcr', 
                         '.kdc', '.mrw', '.mos', '.nrw', '.ptx', '.r3d', '.rwl', 
                         '.rwz', '.x3f', '.erf', '.mef', '.srf', '.sr2', '.iiq', '.crw')
        
        video_extensions = ('.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', 
                           '.m4v', '.mpg', '.mpeg', '.3gp', '.3g2', '.f4v', '.swf', 
                           '.avchd', '.mts', '.m2ts', '.ts', '.vob', '.ogv', '.ogg', 
                           '.drc', '.gifv', '.mng', '.qt', '.yuv', '.rm', '.rmvb', 
                           '.asf', '.amv', '.mp2', '.mpe', '.mpv', '.m2v', '.svi', 
                           '.mxf', '.roq', '.nsv', '.divx')
        
        if ext.endswith(raw_extensions):
            return "RAW"
        elif ext.endswith(video_extensions):
            return "VIDEO"
        else:
            return "IMG"
                
    def show_image(self):
        if not self.images:
            return
            
        # Actualizar contador
        self.counter_label.config(
            text=f"{self.current_index + 1}/{len(self.images)}"
        )
        
        # Mostrar nombre del archivo y carpeta detectada
        current_file = self.images[self.current_index]
        detected_folder = self.folder_mapping.get(current_file, "Sin clasificar")
        file_type = self.get_file_type(current_file)
        self.filename_label.config(text=f"{current_file} → [{detected_folder}] ({file_type})")
        
        # Actualizar entry con carpeta detectada
        self.folder_entry.delete(0, tk.END)
        self.folder_entry.insert(0, detected_folder)
        
        # Cargar y mostrar imagen
        image_path = os.path.join(self.source_folder, current_file)
        
        try:
            # Verificar si es un video o RAW
            if file_type == "VIDEO":
                self.show_video_placeholder()
            elif file_type == "RAW":
                self.show_raw_placeholder()
            else:
                # Cargar imagen normal
                image = Image.open(image_path)
                
                # Redimensionar para ajustar al canvas manteniendo proporción
                canvas_width = self.canvas.winfo_width()
                canvas_height = self.canvas.winfo_height()
                
                if canvas_width > 1 and canvas_height > 1:
                    image.thumbnail((canvas_width - 20, canvas_height - 20), 
                                  Image.Resampling.LANCZOS)
                
                self.photo = ImageTk.PhotoImage(image)
                
                # Centrar imagen en canvas
                self.canvas.delete("all")
                x = canvas_width // 2
                y = canvas_height // 2
                self.canvas.create_image(x, y, image=self.photo, anchor=tk.CENTER)
            
        except Exception as e:
            # Si falla la carga, mostrar placeholder
            self.show_error_placeholder(str(e))
            
        # Resaltar en la lista
        self.update_preview_list()
        self.preview_listbox.see(self.current_index)
    
    def show_video_placeholder(self):
        """Muestra un placeholder para videos"""
        self.canvas.delete("all")
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        x = canvas_width // 2
        y = canvas_height // 2
        
        self.canvas.create_rectangle(x-100, y-60, x+100, y+60, 
                                     fill='#2c3e50', outline='white', width=3)
        self.canvas.create_polygon(x-30, y-30, x-30, y+30, x+30, y, 
                                  fill='white')
        self.canvas.create_text(x, y+80, text="VIDEO", 
                               fill='white', font=('Arial', 16, 'bold'))
    
    def show_raw_placeholder(self):
        """Muestra un placeholder para archivos RAW"""
        self.canvas.delete("all")
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        x = canvas_width // 2
        y = canvas_height // 2
        
        self.canvas.create_rectangle(x-100, y-60, x+100, y+60, 
                                     fill='#34495e', outline='#e74c3c', width=3)
        self.canvas.create_text(x, y-20, text="RAW", 
                               fill='#e74c3c', font=('Arial', 24, 'bold'))
        self.canvas.create_text(x, y+20, text="Archivo de formato RAW", 
                               fill='white', font=('Arial', 10))
    
    def show_error_placeholder(self, error_msg):
        """Muestra un placeholder cuando hay error"""
        self.canvas.delete("all")
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        x = canvas_width // 2
        y = canvas_height // 2
        
        self.canvas.create_text(x, y-20, text="⚠ No se pudo cargar", 
                               fill='#e74c3c', font=('Arial', 14, 'bold'))
        self.canvas.create_text(x, y+10, text="Vista previa no disponible", 
                               fill='white', font=('Arial', 10))
        
    def move_current_image(self):
        """Mueve solo la imagen actual"""
        if not self.images:
            return
            
        folder_name = self.folder_entry.get().strip()
        
        if not folder_name:
            messagebox.showwarning("Advertencia", 
                                 "Por favor ingresa un nombre de carpeta")
            return
        
        current_file = self.images[self.current_index]
        
        if self.move_image_to_folder(current_file, folder_name):
            # Actualizar el mapeo
            self.folder_mapping[current_file] = folder_name
            
            # Remover de la lista
            self.images.pop(self.current_index)
            
            # Mostrar siguiente imagen o finalizar
            if self.images:
                if self.current_index >= len(self.images):
                    self.current_index = len(self.images) - 1
                self.show_image()
            else:
                messagebox.showinfo("Completado", 
                                  "¡Todos los archivos han sido organizados!")
                self.canvas.delete("all")
                self.filename_label.config(text="No hay más archivos")
                self.counter_label.config(text="0/0")
                self.preview_listbox.delete(0, tk.END)
                
    def organize_all(self):
        """Organiza todas las imágenes automáticamente"""
        if not self.images:
            messagebox.showwarning("Advertencia", "No hay archivos para organizar")
            return
            
        response = messagebox.askyesno(
            "Confirmar", 
            f"¿Deseas organizar automáticamente {len(self.images)} archivos?\n\n"
            "Se crearán las carpetas detectadas y se moverán los archivos."
        )
        
        if not response:
            return
            
        success_count = 0
        error_count = 0
        
        # Crear barra de progreso
        progress_window = tk.Toplevel(self.root)
        progress_window.title("Organizando...")
        progress_window.geometry("400x100")
        progress_window.transient(self.root)
        progress_window.grab_set()
        
        ttk.Label(progress_window, text="Organizando archivos...").pack(pady=10)
        progress_bar = ttk.Progressbar(progress_window, length=350, mode='determinate')
        progress_bar.pack(pady=10)
        progress_bar['maximum'] = len(self.images)
        
        images_copy = self.images.copy()
        
        for i, filename in enumerate(images_copy):
            folder_name = self.folder_mapping.get(filename, "Sin clasificar")
            
            if self.move_image_to_folder(filename, folder_name):
                success_count += 1
            else:
                error_count += 1
                
            progress_bar['value'] = i + 1
            progress_window.update()
            
        progress_window.destroy()
        
        # Limpiar listas
        self.images = []
        self.folder_mapping = {}
        self.current_index = 0
        
        # Actualizar interfaz
        self.canvas.delete("all")
        self.filename_label.config(text="Organización completada")
        self.counter_label.config(text="0/0")
        self.preview_listbox.delete(0, tk.END)
        self.folder_entry.delete(0, tk.END)
        
        messagebox.showinfo(
            "Completado", 
            f"Organización completada!\n\n"
            f"✓ Movidos exitosamente: {success_count}\n"
            f"✗ Errores: {error_count}"
        )
        
    def move_image_to_folder(self, filename, folder_name):
        """Mueve una imagen a la carpeta especificada"""
        # Crear carpeta destino si no existe
        dest_folder = os.path.join(self.source_folder, folder_name)
        
        try:
            os.makedirs(dest_folder, exist_ok=True)
            
            # Mover imagen
            source_path = os.path.join(self.source_folder, filename)
            dest_path = os.path.join(dest_folder, filename)
            
            # Si ya existe un archivo con ese nombre, añadir sufijo
            if os.path.exists(dest_path):
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(dest_path):
                    new_filename = f"{base}_{counter}{ext}"
                    dest_path = os.path.join(dest_folder, new_filename)
                    counter += 1
            
            shutil.move(source_path, dest_path)
            return True
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo mover '{filename}': {e}")
            return False
            
    def next_image(self):
        if not self.images:
            return
            
        if self.current_index < len(self.images) - 1:
            self.current_index += 1
            self.show_image()
            
    def previous_image(self):
        if not self.images:
            return
            
        if self.current_index > 0:
            self.current_index -= 1
            self.show_image()
            
    def on_listbox_select(self, event):
        """Cuando se selecciona un elemento en la lista"""
        selection = self.preview_listbox.curselection()
        if selection:
            self.current_index = selection[0]
            self.show_image()

def main():
    root = tk.Tk()
    app = ImageOrganizer(root)
    root.mainloop()

if __name__ == "__main__":
    main()