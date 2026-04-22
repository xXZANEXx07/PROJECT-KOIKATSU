import os
import json
import shutil
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

class ModOrganizer:
    def __init__(self):
        self.inventory = {}
        
    def create_inventory(self, base_folder):
        """Crea un inventario de todos los archivos en subcarpetas"""
        base_path = Path(base_folder)
        
        if not base_path.exists():
            raise Exception(f"La carpeta {base_folder} no existe")
        
        print(f"Creando inventario de: {base_folder}")
        
        # Recorrer todas las subcarpetas
        for subfolder in base_path.iterdir():
            if subfolder.is_dir():
                folder_name = subfolder.name
                self.inventory[folder_name] = []
                
                print(f"Procesando carpeta: {folder_name}")
                
                # Obtener todos los archivos en esta subcarpeta (incluyendo subdirectorios)
                for file_path in subfolder.rglob('*'):
                    if file_path.is_file():
                        # Guardar la ruta relativa desde la subcarpeta
                        relative_path = file_path.relative_to(subfolder)
                        file_info = {
                            'name': file_path.name,
                            'relative_path': str(relative_path),
                            'size': file_path.stat().st_size
                        }
                        self.inventory[folder_name].append(file_info)
        
        print(f"Inventario creado con {len(self.inventory)} carpetas")
        return self.inventory
    
    def save_inventory(self, filename):
        """Guarda el inventario en un archivo JSON"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.inventory, f, indent=2, ensure_ascii=False)
        print(f"Inventario guardado en: {filename}")
    
    def load_inventory(self, filename):
        """Carga el inventario desde un archivo JSON"""
        with open(filename, 'r', encoding='utf-8') as f:
            self.inventory = json.load(f)
        print(f"Inventario cargado desde: {filename}")
        return self.inventory
    
    def organize_files(self, mixed_folder, destination_folder):
        """Organiza los archivos mezclados basándose en el inventario"""
        mixed_path = Path(mixed_folder)
        dest_path = Path(destination_folder)
        
        if not mixed_path.exists():
            raise Exception(f"La carpeta {mixed_folder} no existe")
        
        # Crear carpeta de destino si no existe
        dest_path.mkdir(parents=True, exist_ok=True)
        
        # Obtener lista de archivos en la carpeta mezclada
        mixed_files = {}
        for file_path in mixed_path.rglob('*'):
            if file_path.is_file():
                # Usar nombre y tamaño como clave para identificar archivos
                key = f"{file_path.name}_{file_path.stat().st_size}"
                mixed_files[key] = file_path
        
        organized_count = 0
        not_found = []
        
        print("Organizando archivos...")
        
        # Para cada carpeta en el inventario
        for folder_name, file_list in self.inventory.items():
            target_folder = dest_path / folder_name
            
            for file_info in file_list:
                file_key = f"{file_info['name']}_{file_info['size']}"
                
                if file_key in mixed_files:
                    # Crear la estructura de carpetas necesaria
                    target_file_path = target_folder / file_info['relative_path']
                    target_file_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Mover el archivo
                    shutil.move(str(mixed_files[file_key]), str(target_file_path))
                    print(f"Movido: {file_info['name']} -> {folder_name}/{file_info['relative_path']}")
                    organized_count += 1
                    
                    # Remover de la lista de archivos mezclados
                    del mixed_files[file_key]
                else:
                    not_found.append(f"{folder_name}/{file_info['relative_path']}")
        
        print(f"\n=== RESUMEN ===")
        print(f"Archivos organizados: {organized_count}")
        print(f"Archivos no encontrados: {len(not_found)}")
        print(f"Archivos no identificados: {len(mixed_files)}")
        
        if not_found:
            print("\nArchivos no encontrados:")
            for file in not_found[:10]:  # Mostrar solo los primeros 10
                print(f"  - {file}")
            if len(not_found) > 10:
                print(f"  ... y {len(not_found) - 10} más")
        
        if mixed_files:
            print("\nArchivos no identificados (permanecen en carpeta original):")
            for file_path in list(mixed_files.values())[:10]:
                print(f"  - {file_path.name}")
            if len(mixed_files) > 10:
                print(f"  ... y {len(mixed_files) - 10} más")

class ModOrganizerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Organizador de Mods Koikatsu")
        self.root.geometry("600x500")
        
        self.organizer = ModOrganizer()
        
        self.create_widgets()
    
    def create_widgets(self):
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Título
        title_label = ttk.Label(main_frame, text="Organizador de Mods Koikatsu", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Sección 1: Crear inventario
        section1_frame = ttk.LabelFrame(main_frame, text="1. Crear Inventario", padding="10")
        section1_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(section1_frame, text="Carpeta con mods organizados:").grid(row=0, column=0, sticky=tk.W)
        self.organized_folder_var = tk.StringVar()
        ttk.Entry(section1_frame, textvariable=self.organized_folder_var, width=50).grid(row=1, column=0, padx=(0, 5))
        ttk.Button(section1_frame, text="Examinar", 
                  command=self.browse_organized_folder).grid(row=1, column=1)
        
        ttk.Button(section1_frame, text="Crear Inventario", 
                  command=self.create_inventory).grid(row=2, column=0, pady=(10, 0))
        
        # Sección 2: Organizar archivos
        section2_frame = ttk.LabelFrame(main_frame, text="2. Organizar Archivos", padding="10")
        section2_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(section2_frame, text="Archivo de inventario:").grid(row=0, column=0, sticky=tk.W)
        self.inventory_file_var = tk.StringVar()
        ttk.Entry(section2_frame, textvariable=self.inventory_file_var, width=50).grid(row=1, column=0, padx=(0, 5))
        ttk.Button(section2_frame, text="Examinar", 
                  command=self.browse_inventory_file).grid(row=1, column=1)
        
        ttk.Label(section2_frame, text="Carpeta con archivos mezclados:").grid(row=2, column=0, sticky=tk.W, pady=(10, 0))
        self.mixed_folder_var = tk.StringVar()
        ttk.Entry(section2_frame, textvariable=self.mixed_folder_var, width=50).grid(row=3, column=0, padx=(0, 5))
        ttk.Button(section2_frame, text="Examinar", 
                  command=self.browse_mixed_folder).grid(row=3, column=1)
        
        ttk.Label(section2_frame, text="Carpeta de destino:").grid(row=4, column=0, sticky=tk.W, pady=(10, 0))
        self.dest_folder_var = tk.StringVar()
        ttk.Entry(section2_frame, textvariable=self.dest_folder_var, width=50).grid(row=5, column=0, padx=(0, 5))
        ttk.Button(section2_frame, text="Examinar", 
                  command=self.browse_dest_folder).grid(row=5, column=1)
        
        ttk.Button(section2_frame, text="Organizar Archivos", 
                  command=self.organize_files).grid(row=6, column=0, pady=(10, 0))
        
        # Área de log
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="10")
        log_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        self.log_text = tk.Text(log_frame, height=10, width=70)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Configurar redimensionamiento
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
    
    def log(self, message):
        """Añade un mensaje al área de log"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update()
    
    def browse_organized_folder(self):
        folder = filedialog.askdirectory(title="Seleccionar carpeta con mods organizados")
        if folder:
            self.organized_folder_var.set(folder)
    
    def browse_inventory_file(self):
        file = filedialog.askopenfilename(title="Seleccionar archivo de inventario",
                                         filetypes=[("JSON files", "*.json")])
        if file:
            self.inventory_file_var.set(file)
    
    def browse_mixed_folder(self):
        folder = filedialog.askdirectory(title="Seleccionar carpeta con archivos mezclados")
        if folder:
            self.mixed_folder_var.set(folder)
    
    def browse_dest_folder(self):
        folder = filedialog.askdirectory(title="Seleccionar carpeta de destino")
        if folder:
            self.dest_folder_var.set(folder)
    
    def create_inventory(self):
        try:
            folder = self.organized_folder_var.get()
            if not folder:
                messagebox.showerror("Error", "Por favor selecciona la carpeta con mods organizados")
                return
            
            self.log("Iniciando creación de inventario...")
            inventory = self.organizer.create_inventory(folder)
            
            # Preguntar dónde guardar el inventario
            save_path = filedialog.asksaveasfilename(
                title="Guardar inventario como",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json")]
            )
            
            if save_path:
                self.organizer.save_inventory(save_path)
                self.log(f"Inventario guardado: {save_path}")
                self.inventory_file_var.set(save_path)
                messagebox.showinfo("Éxito", "Inventario creado correctamente")
            
        except Exception as e:
            self.log(f"Error: {str(e)}")
            messagebox.showerror("Error", str(e))
    
    def organize_files(self):
        try:
            inventory_file = self.inventory_file_var.get()
            mixed_folder = self.mixed_folder_var.get()
            dest_folder = self.dest_folder_var.get()
            
            if not inventory_file:
                messagebox.showerror("Error", "Por favor selecciona el archivo de inventario")
                return
            
            if not mixed_folder:
                messagebox.showerror("Error", "Por favor selecciona la carpeta con archivos mezclados")
                return
            
            if not dest_folder:
                messagebox.showerror("Error", "Por favor selecciona la carpeta de destino")
                return
            
            self.log("Cargando inventario...")
            self.organizer.load_inventory(inventory_file)
            
            self.log("Iniciando organización de archivos...")
            
            # Redirigir print a nuestro log
            import sys
            from io import StringIO
            
            old_stdout = sys.stdout
            sys.stdout = StringIO()
            
            try:
                self.organizer.organize_files(mixed_folder, dest_folder)
                output = sys.stdout.getvalue()
                self.log(output)
                
            finally:
                sys.stdout = old_stdout
            
            messagebox.showinfo("Éxito", "Archivos organizados correctamente")
            
        except Exception as e:
            self.log(f"Error: {str(e)}")
            messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    # Modo GUI
    root = tk.Tk()
    app = ModOrganizerGUI(root)
    root.mainloop()