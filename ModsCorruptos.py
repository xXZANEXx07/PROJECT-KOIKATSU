import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import zipfile
import os
import threading
import shutil
from pathlib import Path

class KoikatsuModChecker:
    def __init__(self, root):
        self.root = root
        self.root.title("Verificador de Mods de Koikatsu")
        self.root.geometry("700x500")
        
        # Variables
        self.selected_folder = tk.StringVar()
        self.move_files = tk.BooleanVar(value=True)
        self.valid_mods = []
        self.invalid_mods = []
        self.corrupted_mods = []
        
        self.setup_ui()
        
    def setup_ui(self):
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configurar el grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Título
        title_label = ttk.Label(main_frame, text="Verificador de Mods de Koikatsu", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Selección de carpeta
        ttk.Label(main_frame, text="Carpeta de mods:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        folder_entry = ttk.Entry(main_frame, textvariable=self.selected_folder, width=50)
        folder_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5, padx=(5, 5))
        
        browse_button = ttk.Button(main_frame, text="Examinar", command=self.browse_folder)
        browse_button.grid(row=1, column=2, pady=5)
        
        # Opción para mover archivos
        move_check = ttk.Checkbutton(main_frame, text="Mover archivos a carpetas separadas", 
                                    variable=self.move_files)
        move_check.grid(row=2, column=0, columnspan=3, pady=10, sticky=tk.W)
        
        # Botón de verificar
        check_button = ttk.Button(main_frame, text="Verificar Mods", 
                                 command=self.start_verification, style="Accent.TButton")
        check_button.grid(row=3, column=0, columnspan=3, pady=20)
        
        # Barra de progreso
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, 
                                           maximum=100, length=400)
        self.progress_bar.grid(row=4, column=0, columnspan=3, pady=10, sticky=(tk.W, tk.E))
        
        # Label de estado
        self.status_label = ttk.Label(main_frame, text="Selecciona una carpeta para comenzar")
        self.status_label.grid(row=5, column=0, columnspan=3, pady=5)
        
        # Notebook para resultados
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        
        # Frame para mods válidos
        valid_frame = ttk.Frame(self.notebook)
        self.notebook.add(valid_frame, text="Mods Válidos")
        
        self.valid_listbox = tk.Listbox(valid_frame, height=10)
        self.valid_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        valid_scrollbar = ttk.Scrollbar(valid_frame, orient=tk.VERTICAL, command=self.valid_listbox.yview)
        valid_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.valid_listbox.config(yscrollcommand=valid_scrollbar.set)
        
        # Frame para mods inválidos
        invalid_frame = ttk.Frame(self.notebook)
        self.notebook.add(invalid_frame, text="Mods Inválidos")
        
        self.invalid_listbox = tk.Listbox(invalid_frame, height=10)
        self.invalid_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        invalid_scrollbar = ttk.Scrollbar(invalid_frame, orient=tk.VERTICAL, command=self.invalid_listbox.yview)
        invalid_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.invalid_listbox.config(yscrollcommand=invalid_scrollbar.set)
        
        # Frame para mods corruptos
        corrupted_frame = ttk.Frame(self.notebook)
        self.notebook.add(corrupted_frame, text="Mods Corruptos")
        
        self.corrupted_listbox = tk.Listbox(corrupted_frame, height=10)
        self.corrupted_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        corrupted_scrollbar = ttk.Scrollbar(corrupted_frame, orient=tk.VERTICAL, command=self.corrupted_listbox.yview)
        corrupted_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.corrupted_listbox.config(yscrollcommand=corrupted_scrollbar.set)
        
        # Configurar el redimensionamiento
        main_frame.rowconfigure(6, weight=1)
        
    def browse_folder(self):
        folder_path = filedialog.askdirectory(title="Seleccionar carpeta de mods")
        if folder_path:
            self.selected_folder.set(folder_path)
            
    def start_verification(self):
        if not self.selected_folder.get():
            messagebox.showwarning("Advertencia", "Por favor selecciona una carpeta primero.")
            return
            
        # Limpiar resultados anteriores
        self.valid_mods.clear()
        self.invalid_mods.clear()
        self.corrupted_mods.clear()
        self.valid_listbox.delete(0, tk.END)
        self.invalid_listbox.delete(0, tk.END)
        self.corrupted_listbox.delete(0, tk.END)
        
        # Iniciar verificación en un hilo separado
        thread = threading.Thread(target=self.verify_mods)
        thread.daemon = True
        thread.start()
        
    def verify_mods(self):
        folder_path = self.selected_folder.get()
        
        # Crear carpetas de destino si se va a mover archivos
        valid_folder = None
        invalid_folder = None
        corrupted_folder = None
        
        if self.move_files.get():
            valid_folder = os.path.join(folder_path, "Mods_Validos")
            invalid_folder = os.path.join(folder_path, "Mods_Invalidos")
            corrupted_folder = os.path.join(folder_path, "Mods_Corruptos")
            
            try:
                os.makedirs(valid_folder, exist_ok=True)
                os.makedirs(invalid_folder, exist_ok=True)
                os.makedirs(corrupted_folder, exist_ok=True)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", 
                    f"No se pudieron crear las carpetas de destino: {str(e)}"))
                return
        
        # Obtener todos los archivos .zipmod
        zipmod_files = []
        for file in os.listdir(folder_path):
            if file.lower().endswith('.zipmod'):
                zipmod_files.append(file)
        
        if not zipmod_files:
            self.root.after(0, lambda: self.status_label.config(text="No se encontraron archivos .zipmod en la carpeta"))
            return
            
        total_files = len(zipmod_files)
        moved_valid = 0
        moved_invalid = 0
        moved_corrupted = 0
        
        for i, filename in enumerate(zipmod_files):
            file_path = os.path.join(folder_path, filename)
            
            # Actualizar progreso
            progress = (i / total_files) * 100
            self.root.after(0, lambda p=progress: self.progress_var.set(p))
            self.root.after(0, lambda f=filename: self.status_label.config(text=f"Verificando: {f}"))
            
            # Verificar el mod
            is_valid, error_message, is_corrupted = self.check_mod_validity(file_path)
            
            if is_corrupted:
                self.corrupted_mods.append((filename, error_message))
                self.root.after(0, lambda f=filename, e=error_message: 
                              self.corrupted_listbox.insert(tk.END, f"{f} - {e}"))
                
                # Mover archivo corrupto si está habilitado
                if self.move_files.get() and corrupted_folder:
                    try:
                        dest_path = os.path.join(corrupted_folder, filename)
                        shutil.move(file_path, dest_path)
                        moved_corrupted += 1
                    except Exception as e:
                        self.root.after(0, lambda f=filename, e=str(e): 
                                      messagebox.showwarning("Advertencia", 
                                      f"No se pudo mover {f}: {e}"))
            elif is_valid:
                self.valid_mods.append(filename)
                self.root.after(0, lambda f=filename: self.valid_listbox.insert(tk.END, f))
                
                # Mover archivo si está habilitado
                if self.move_files.get() and valid_folder:
                    try:
                        dest_path = os.path.join(valid_folder, filename)
                        shutil.move(file_path, dest_path)
                        moved_valid += 1
                    except Exception as e:
                        self.root.after(0, lambda f=filename, e=str(e): 
                                      messagebox.showwarning("Advertencia", 
                                      f"No se pudo mover {f}: {e}"))
            else:
                self.invalid_mods.append((filename, error_message))
                self.root.after(0, lambda f=filename, e=error_message: 
                              self.invalid_listbox.insert(tk.END, f"{f} - {e}"))
                
                # Mover archivo si está habilitado
                if self.move_files.get() and invalid_folder:
                    try:
                        dest_path = os.path.join(invalid_folder, filename)
                        shutil.move(file_path, dest_path)
                        moved_invalid += 1
                    except Exception as e:
                        self.root.after(0, lambda f=filename, e=str(e): 
                                      messagebox.showwarning("Advertencia", 
                                      f"No se pudo mover {f}: {e}"))
        
        # Finalizar
        self.root.after(0, lambda: self.progress_var.set(100))
        
        # Mensaje de estado final
        if self.move_files.get():
            status_msg = f"Completado: {len(self.valid_mods)} válidos, {len(self.invalid_mods)} inválidos, {len(self.corrupted_mods)} corruptos. Movidos: {moved_valid} válidos, {moved_invalid} inválidos, {moved_corrupted} corruptos"
        else:
            status_msg = f"Completado: {len(self.valid_mods)} válidos, {len(self.invalid_mods)} inválidos, {len(self.corrupted_mods)} corruptos"
            
        self.root.after(0, lambda: self.status_label.config(text=status_msg))
        
        # Mostrar resumen
        self.root.after(0, lambda: self.show_summary(moved_valid, moved_invalid, moved_corrupted))
        
    def check_mod_validity(self, file_path):
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_file:
                file_list = zip_file.namelist()
                
                # Verificar que existe la carpeta abdata
                has_abdata = any(f.startswith('abdata/') for f in file_list)
                
                # Verificar que existe un archivo .xml (manifest)
                has_xml = any(f.endswith('.xml') for f in file_list)
                
                if not has_abdata and not has_xml:
                    return False, "No tiene carpeta abdata ni archivo XML", False
                elif not has_abdata:
                    return False, "No tiene carpeta abdata", False
                elif not has_xml:
                    return False, "No tiene archivo XML (manifest)", False
                else:
                    return True, "", False
                    
        except zipfile.BadZipFile:
            return False, "Archivo ZIP corrupto", True
        except Exception as e:
            return False, f"Error al leer: {str(e)}", True
            
    def show_summary(self, moved_valid=0, moved_invalid=0, moved_corrupted=0):
        summary = f"Verificación completada:\n\n"
        summary += f"Mods válidos: {len(self.valid_mods)}\n"
        summary += f"Mods inválidos: {len(self.invalid_mods)}\n"
        summary += f"Mods corruptos: {len(self.corrupted_mods)}\n\n"
        
        if self.move_files.get():
            summary += f"Archivos movidos:\n"
            summary += f"• {moved_valid} mods válidos → carpeta 'Mods_Validos'\n"
            summary += f"• {moved_invalid} mods inválidos → carpeta 'Mods_Invalidos'\n"
            summary += f"• {moved_corrupted} mods corruptos → carpeta 'Mods_Corruptos'\n\n"
        
        if self.invalid_mods:
            summary += "Mods inválidos (estructura incorrecta):\n"
            for filename, error in self.invalid_mods:
                summary += f"• {filename}: {error}\n"
        
        if self.corrupted_mods:
            summary += "\nMods corruptos (archivos dañados):\n"
            for filename, error in self.corrupted_mods:
                summary += f"• {filename}: {error}\n"
        
        messagebox.showinfo("Resumen de Verificación", summary)

def main():
    root = tk.Tk()
    app = KoikatsuModChecker(root)
    root.mainloop()

if __name__ == "__main__":
    main()