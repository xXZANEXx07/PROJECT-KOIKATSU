import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import zipfile
import os
import shutil
from pathlib import Path
import threading

class ZipProcessor:
    def __init__(self, root):
        self.root = root
        self.root.title("Procesador ZIP a ZIPMOD")
        self.root.geometry("600x500")
        
        # Variables
        self.source_folder = tk.StringVar()
        self.destination_folder = tk.StringVar()
        self.progress_var = tk.DoubleVar()
        self.status_var = tk.StringVar(value="Listo para procesar")
        
        self.create_widgets()
        
    def create_widgets(self):
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configurar el grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Título
        title_label = ttk.Label(main_frame, text="Procesador ZIP a ZIPMOD", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Carpeta a analizar
        ttk.Label(main_frame, text="Carpeta a analizar:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.source_folder, width=50).grid(row=1, column=1, 
                                                                             sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="Examinar", 
                  command=self.select_source_folder).grid(row=1, column=2, padx=5)
        
        # Descripción
        description_text = """
Condiciones para procesamiento:
• El archivo ZIP debe contener una carpeta llamada "abdata"
• El archivo ZIP debe contener un archivo llamado "manifest.xml"
• Los archivos que cumplan estas condiciones se MOVERÁN a la carpeta "zipmod_files"
• Se renombrarán de .zip a .zipmod automáticamente
        """
        
        desc_frame = ttk.LabelFrame(main_frame, text="Información", padding="10")
        desc_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Label(desc_frame, text=description_text, justify=tk.LEFT).grid(row=0, column=0, sticky=tk.W)
        
        # Botón de procesamiento
        self.process_button = ttk.Button(main_frame, text="Procesar Archivos", 
                                        command=self.start_processing, style="Accent.TButton")
        self.process_button.grid(row=3, column=0, columnspan=3, pady=20)
        
        # Barra de progreso
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, 
                                           maximum=100, length=400)
        self.progress_bar.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        # Estado
        self.status_label = ttk.Label(main_frame, textvariable=self.status_var)
        self.status_label.grid(row=5, column=0, columnspan=3, pady=5)
        
        # Área de resultados
        results_frame = ttk.LabelFrame(main_frame, text="Resultados", padding="10")
        results_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        main_frame.rowconfigure(6, weight=1)
        
        # Text widget con scrollbar
        self.results_text = tk.Text(results_frame, height=8, width=60)
        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_text.yview)
        self.results_text.configure(yscrollcommand=scrollbar.set)
        
        self.results_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        
    def select_source_folder(self):
        folder = filedialog.askdirectory(title="Seleccionar carpeta a analizar")
        if folder:
            self.source_folder.set(folder)
            
    def log_message(self, message):
        """Agregar mensaje al área de resultados"""
        self.results_text.insert(tk.END, message + "\n")
        self.results_text.see(tk.END)
        self.root.update()
        
    def clear_results(self):
        """Limpiar el área de resultados"""
        self.results_text.delete(1.0, tk.END)
        
    def check_zip_conditions(self, zip_path):
        """Verificar si el ZIP cumple las condiciones"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                file_list = zip_file.namelist()
                
                # Verificar si existe carpeta abdata (no abbdata)
                has_abdata = any(path.startswith('abdata/') or path == 'abdata' for path in file_list)
                
                # Verificar si existe manifest.xml específicamente
                has_manifest = 'manifest.xml' in file_list
                
                # Debug: mostrar contenido del ZIP
                self.log_message(f"Contenido de {Path(zip_path).name}:")
                for item in file_list:
                    self.log_message(f"  - {item}")
                
                result = has_abdata and has_manifest
                self.log_message(f"  Carpeta 'abdata': {'✓' if has_abdata else '✗'}")
                self.log_message(f"  Archivo 'manifest.xml': {'✓' if has_manifest else '✗'}")
                self.log_message(f"  Resultado: {'VÁLIDO' if result else 'NO VÁLIDO'}\n")
                
                return result
                
        except Exception as e:
            self.log_message(f"Error al verificar {zip_path}: {str(e)}")
            return False
            
    def process_zip_file(self, zip_path, destination_folder):
        """Procesar un archivo ZIP individual"""
        try:
            # Obtener el nombre del archivo sin extensión
            file_name = Path(zip_path).stem
            
            # Crear el nuevo nombre con extensión .zipmod
            new_file_name = f"{file_name}.zipmod"
            destination_path = os.path.join(destination_folder, new_file_name)
            
            # Mover el archivo (no copiarlo)
            shutil.move(zip_path, destination_path)
            
            self.log_message(f"✓ Movido: {Path(zip_path).name} → {new_file_name}")
            return True
            
        except Exception as e:
            self.log_message(f"✗ Error al mover {Path(zip_path).name}: {str(e)}")
            return False
            
    def start_processing(self):
        """Iniciar el procesamiento en un hilo separado"""
        if not self.source_folder.get():
            messagebox.showerror("Error", "Por favor selecciona la carpeta a analizar")
            return
            
        # Deshabilitar botón y limpiar resultados
        self.process_button.config(state="disabled")
        self.clear_results()
        
        # Iniciar hilo de procesamiento
        thread = threading.Thread(target=self.process_files)
        thread.daemon = True
        thread.start()
        
    def process_files(self):
        """Procesar todos los archivos ZIP"""
        try:
            source_path = Path(self.source_folder.get())
            
            # Crear carpeta de destino dentro de la carpeta de origen
            dest_path = source_path / "zipmod_files"
            dest_path.mkdir(parents=True, exist_ok=True)
            
            self.log_message(f"Carpeta de destino creada: {dest_path}")
            
            # Buscar archivos .zip
            zip_files = list(source_path.glob("*.zip"))
            
            if not zip_files:
                self.log_message("No se encontraron archivos .zip en la carpeta seleccionada")
                self.status_var.set("No se encontraron archivos ZIP")
                self.process_button.config(state="normal")
                return
            
            self.log_message(f"Encontrados {len(zip_files)} archivos ZIP")
            self.log_message("Verificando condiciones...\n")
            
            processed_count = 0
            total_files = len(zip_files)
            
            for i, zip_file in enumerate(zip_files):
                # Actualizar progreso
                progress = (i / total_files) * 100
                self.progress_var.set(progress)
                self.status_var.set(f"Procesando: {zip_file.name}")
                
                # Verificar condiciones
                if self.check_zip_conditions(str(zip_file)):
                    if self.process_zip_file(str(zip_file), str(dest_path)):
                        processed_count += 1
                else:
                    self.log_message(f"✗ No cumple condiciones: {zip_file.name}\n")
            
            # Completar progreso
            self.progress_var.set(100)
            self.status_var.set("Procesamiento completado")
            
            # Mostrar resumen
            self.log_message(f"=== RESUMEN ===")
            self.log_message(f"Archivos verificados: {total_files}")
            self.log_message(f"Archivos movidos: {processed_count}")
            self.log_message(f"Archivos convertidos a .zipmod: {processed_count}")
            self.log_message(f"Ubicación de archivos procesados: {dest_path}")
            
            if processed_count > 0:
                messagebox.showinfo("Completado", 
                                  f"Procesamiento completado.\n"
                                  f"Se movieron {processed_count} de {total_files} archivos.\n"
                                  f"Los archivos .zipmod están en: {dest_path}")
            else:
                messagebox.showwarning("Advertencia", 
                                     "No se encontraron archivos que cumplan las condiciones.\n"
                                     "Verifica que los archivos ZIP contengan:\n"
                                     "- Una carpeta llamada 'abdata'\n"
                                     "- Un archivo llamado 'manifest.xml'")
                
        except Exception as e:
            self.log_message(f"Error general: {str(e)}")
            messagebox.showerror("Error", f"Error durante el procesamiento: {str(e)}")
            
        finally:
            # Rehabilitar botón
            self.process_button.config(state="normal")
            self.progress_var.set(0)

def main():
    root = tk.Tk()
    app = ZipProcessor(root)
    root.mainloop()

if __name__ == "__main__":
    main()