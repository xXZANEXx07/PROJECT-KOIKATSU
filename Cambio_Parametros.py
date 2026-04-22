import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
from pathlib import Path
import traceback
import json

try:
    from kkloader import KoikatuCharaData
    KKLOADER_AVAILABLE = True
except ImportError:
    KKLOADER_AVAILABLE = False

class KoikatsuHEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Koikatsu H-Parameters Mass Editor")
        self.root.geometry("900x700")
        
        # Variables
        self.folder_path = tk.StringVar()
        self.progress_var = tk.DoubleVar()
        self.status_var = tk.StringVar(value="Listo para procesar")
        self.log_text = tk.StringVar(value="")
        
        # Debug mode
        self.debug_var = tk.BooleanVar(value=False)
        
        self.setup_ui()
        
        if not KKLOADER_AVAILABLE:
            messagebox.showerror("Error", "kkloader no está instalado.\nInstálalo con: pip install kkloader")
    
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Koikatsu H-Parameters Mass Editor", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Folder selection
        ttk.Label(main_frame, text="Carpeta con cartas:").grid(row=1, column=0, sticky=tk.W, pady=5)
        folder_entry = ttk.Entry(main_frame, textvariable=self.folder_path, width=50)
        folder_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        ttk.Button(main_frame, text="Examinar", command=self.browse_folder).grid(row=1, column=2, pady=5)
        
        # Parameters section
        params_frame = ttk.LabelFrame(main_frame, text="Parámetros H a modificar", padding="10")
        params_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        params_frame.columnconfigure(0, weight=1)
        
        # Radio buttons for H-parameters
        self.param_vars = {}
        param_labels = {
            "kiss": "Besos",
            "aibu": "Caricias/manoseos", 
            "anal": "Sexo anal",
            "massage": "Juguetes/vibradores",
            "notCondom": "Sexo sin condón"
        }
        
        for i, (param, label) in enumerate(param_labels.items()):
            # Create frame for each parameter
            param_frame = ttk.Frame(params_frame)
            param_frame.grid(row=i, column=0, sticky=(tk.W, tk.E), pady=2)
            param_frame.columnconfigure(1, weight=1)
            
            # Parameter label
            ttk.Label(param_frame, text=f"{label}:", width=20).grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
            
            # Radio buttons frame
            radio_frame = ttk.Frame(param_frame)
            radio_frame.grid(row=0, column=1, sticky=tk.W)
            
            # Create StringVar for radio buttons: "allow", "deny", "ignore"
            var = tk.StringVar(value="ignore")
            self.param_vars[param] = var
            
            ttk.Radiobutton(radio_frame, text="Permitir", variable=var, value="allow").pack(side=tk.LEFT, padx=5)
            ttk.Radiobutton(radio_frame, text="Denegar", variable=var, value="deny").pack(side=tk.LEFT, padx=5)
            ttk.Radiobutton(radio_frame, text="No modificar", variable=var, value="ignore").pack(side=tk.LEFT, padx=5)
        
        # Options
        options_frame = ttk.LabelFrame(main_frame, text="Opciones", padding="10")
        options_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        self.backup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Crear respaldos (_backup)", variable=self.backup_var).grid(row=0, column=0, sticky=tk.W)
        
        self.skip_complete_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Saltar cartas que ya tienen todos los parámetros habilitados", 
                       variable=self.skip_complete_var).grid(row=1, column=0, sticky=tk.W)
        
        ttk.Checkbutton(options_frame, text="Modo debug (mostrar estructura de datos)", 
                       variable=self.debug_var).grid(row=2, column=0, sticky=tk.W)
        
        # Progress section
        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        progress_frame.columnconfigure(0, weight=1)
        
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(progress_frame, textvariable=self.status_var).grid(row=1, column=0, sticky=tk.W)
        
        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=3, pady=10)
        
        ttk.Button(button_frame, text="Procesar Cartas", command=self.start_processing).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Analizar Estructura", command=self.analyze_structure).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Limpiar Log", command=self.clear_log).pack(side=tk.LEFT, padx=5)
        
        # Log area
        log_frame = ttk.LabelFrame(main_frame, text="Log de Procesamiento", padding="10")
        log_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(6, weight=1)
        
        self.log_text_widget = tk.Text(log_frame, wrap=tk.WORD, height=12)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text_widget.yview)
        self.log_text_widget.configure(yscrollcommand=scrollbar.set)
        
        self.log_text_widget.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
    
    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path.set(folder)
    
    def log_message(self, message):
        """Add message to log"""
        self.log_text_widget.insert(tk.END, message + "\n")
        self.log_text_widget.see(tk.END)
        self.root.update_idletasks()
    
    def clear_log(self):
        self.log_text_widget.delete(1.0, tk.END)
    
    def explore_data_structure(self, data, path="", max_depth=3, current_depth=0):
        """Recursively explore data structure to find H-parameters"""
        findings = []
        
        if current_depth > max_depth:
            return findings
        
        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                
                # Check if this looks like H-parameter data
                if key.lower() in ['denial', 'h', 'sexual', 'parameter', 'status']:
                    findings.append({
                        'path': current_path,
                        'type': type(value).__name__,
                        'value': value if not isinstance(value, dict) else f"dict with {len(value)} keys"
                    })
                
                # Look for our specific parameters
                if isinstance(value, dict):
                    for param in ['kiss', 'aibu', 'anal', 'massage', 'notCondom']:
                        if param in value:
                            findings.append({
                                'path': f"{current_path}.{param}",
                                'type': type(value[param]).__name__,
                                'value': value[param]
                            })
                
                # Recurse into nested structures
                if isinstance(value, (dict, list)) and current_depth < max_depth:
                    findings.extend(self.explore_data_structure(value, current_path, max_depth, current_depth + 1))
        
        elif isinstance(data, list) and data:
            for i, item in enumerate(data[:3]):  # Check first 3 items
                current_path = f"{path}[{i}]"
                findings.extend(self.explore_data_structure(item, current_path, max_depth, current_depth + 1))
        
        return findings
    
    def find_h_parameters(self, kc):
        """Find H-parameters in the character data"""
        try:
            # First, explore the structure to find potential locations
            findings = self.explore_data_structure(kc)
            
            if self.debug_var.get():
                self.log_message("=== ESTRUCTURA ENCONTRADA ===")
                for finding in findings:
                    self.log_message(f"{finding['path']}: {finding['type']} = {finding['value']}")
                self.log_message("=== FIN ESTRUCTURA ===\n")
            
            # Try to find actual H-parameters
            h_params_location = None
            h_params_data = None
            
            # Common locations to check
            check_paths = [
                ('Parameter', 'denial'),
                ('Parameter', 'h'),
                ('Status', 'denial'),
                ('Custom', 'denial'),
                ('Parameter', 'sexual'),
                ('gameinfo', 'denial'),
                ('gameinfo2', 'denial'),
                # Add more potential paths based on findings
            ]
            
            # Add paths found in exploration
            for finding in findings:
                if any(param in finding['path'].lower() for param in ['denial', 'sexual', 'h']):
                    path_parts = finding['path'].split('.')
                    if len(path_parts) >= 2:
                        check_paths.append(tuple(path_parts))
            
            for path in check_paths:
                try:
                    temp = kc
                    for key in path:
                        temp = temp[key]
                    
                    # Check if this contains our target parameters
                    if isinstance(temp, dict):
                        found_params = [p for p in ['kiss', 'aibu', 'anal', 'massage', 'notCondom'] if p in temp]
                        if found_params:
                            h_params_location = path
                            h_params_data = temp
                            self.log_message(f"Encontrados parámetros H en: {'.'.join(path)}")
                            self.log_message(f"Parámetros disponibles: {found_params}")
                            break
                except (KeyError, TypeError, AttributeError):
                    continue
            
            return h_params_location, h_params_data
            
        except Exception as e:
            self.log_message(f"Error explorando estructura: {str(e)}")
            return None, None
    
    def check_h_parameters(self, kc):
        """Check if all selected H-parameters are already configured"""
        try:
            location, params = self.find_h_parameters(kc)
            
            if params is None:
                return False, "No se encontraron parámetros H"
            
            # Check each parameter
            needs_modification = False
            status = []
            
            # Si no hay parámetros para modificar, solo reportar estado actual
            selected_params = [param for param, var in self.param_vars.items() if var.get() != "ignore"]
            if not selected_params:
                for param in ['kiss', 'aibu', 'anal', 'massage', 'notCondom']:
                    if param in params:
                        current_value = params[param]
                        if current_value is True:
                            status.append(f"{param}: permitido")
                        elif current_value is False or current_value is None or current_value == "":
                            status.append(f"{param}: denegado/vacío")
                        else:
                            status.append(f"{param}: valor desconocido ({current_value})")
                    else:
                        status.append(f"{param}: no encontrado")
                return False, "; ".join(status)
            
            # Verificar solo los parámetros seleccionados
            for param, var in self.param_vars.items():
                setting = var.get()
                if setting == "ignore":
                    continue
                    
                if param in params:
                    current_value = params[param]
                    
                    if setting == "allow":
                        # Queremos permitir (True)
                        if current_value is not True:
                            needs_modification = True
                            status.append(f"{param}: necesita permitir")
                        else:
                            status.append(f"{param}: ya permitido")
                    elif setting == "deny":
                        # Queremos denegar (False)
                        if current_value is not False:
                            needs_modification = True
                            status.append(f"{param}: necesita denegar")
                        else:
                            status.append(f"{param}: ya denegado")
                else:
                    needs_modification = True
                    status.append(f"{param}: no encontrado")
            
            return needs_modification, "; ".join(status)
            
        except Exception as e:
            return False, f"Error al verificar parámetros: {str(e)}"
    
    def modify_h_parameters(self, kc):
        """Modify H-parameters in the character"""
        try:
            location, params = self.find_h_parameters(kc)
            
            if params is None:
                return False, "No se encontraron parámetros H para modificar"
            
            # Si no hay parámetros seleccionados, no modificar nada
            selected_params = [param for param, var in self.param_vars.items() if var.get() != "ignore"]
            if not selected_params:
                return False, "No hay parámetros seleccionados para modificar"
            
            # Store original values for comparison
            original_values = {}
            modifications = []
            
            for param, var in self.param_vars.items():
                setting = var.get()
                if setting == "ignore":
                    continue
                    
                if param in params:
                    original_values[param] = params[param]
                    
                    if setting == "allow":
                        # Set to True to allow the action
                        params[param] = True
                        modifications.append(f"{param}: {original_values[param]} → True (permitir)")
                    elif setting == "deny":
                        # Set to False to deny the action
                        params[param] = False
                        modifications.append(f"{param}: {original_values[param]} → False (denegar)")
                else:
                    # If parameter doesn't exist, add it
                    if setting == "allow":
                        params[param] = True
                        modifications.append(f"{param}: añadido como True (permitir)")
                    elif setting == "deny":
                        params[param] = False
                        modifications.append(f"{param}: añadido como False (denegar)")
            
            if modifications:
                return True, f"Modificaciones en {'.'.join(location)}: {'; '.join(modifications)}"
            else:
                return False, "No se realizaron modificaciones"
            
        except Exception as e:
            return False, f"Error al modificar parámetros: {str(e)}"
    
    def analyze_structure(self):
        """Analyze the structure of a single file to understand data layout"""
        if not KKLOADER_AVAILABLE:
            messagebox.showerror("Error", "kkloader no está disponible")
            return
        
        file_path = filedialog.askopenfilename(
            title="Seleccionar archivo PNG para analizar",
            filetypes=[("PNG files", "*.png")]
        )
        
        if not file_path:
            return
        
        try:
            self.log_message(f"Analizando estructura de: {Path(file_path).name}")
            kc = KoikatuCharaData.load(file_path)
            
            # Enable debug mode temporarily
            old_debug = self.debug_var.get()
            self.debug_var.set(True)
            
            # Find H-parameters
            location, params = self.find_h_parameters(kc)
            
            if params:
                self.log_message(f"\nParámetros H encontrados en: {'.'.join(location)}")
                for param, value in params.items():
                    self.log_message(f"  {param}: {value} ({type(value).__name__})")
            else:
                self.log_message("No se encontraron parámetros H conocidos")
            
            # Restore debug mode
            self.debug_var.set(old_debug)
            
        except Exception as e:
            self.log_message(f"Error analizando archivo: {str(e)}")
            self.log_message(traceback.format_exc())
    
    def process_character_file(self, file_path):
        """Process a single character file"""
        try:
            # Load character
            kc = KoikatuCharaData.load(str(file_path))
            
            # Check current parameters
            needs_modification, check_status = self.check_h_parameters(kc)
            
            if not needs_modification and self.skip_complete_var.get():
                return f"✓ Saltado (ya configurado): {check_status}"
            
            # Create backup if requested
            if self.backup_var.get():
                backup_path = file_path.with_suffix(f"{file_path.suffix}_backup")
                import shutil
                shutil.copy2(file_path, backup_path)
            
            # Modify parameters
            success, mod_status = self.modify_h_parameters(kc)
            
            if success:
                # Save modified character
                kc.save(str(file_path))
                
                # Verify changes were saved by reloading
                try:
                    kc_verify = KoikatuCharaData.load(str(file_path))
                    _, verify_status = self.check_h_parameters(kc_verify)
                    return f"✓ Modificado y verificado: {mod_status} | Estado: {verify_status}"
                except:
                    return f"✓ Modificado (sin verificar): {mod_status}"
            else:
                return f"⚠ No modificado: {mod_status}"
                
        except Exception as e:
            return f"❌ Error procesando: {str(e)}"
    
    def start_processing(self):
        """Start processing in a separate thread"""
        if not KKLOADER_AVAILABLE:
            messagebox.showerror("Error", "kkloader no está disponible")
            return
        
        # VALIDACIÓN: Verificar que se seleccionó una carpeta
        if not self.folder_path.get() or not self.folder_path.get().strip():
            messagebox.showerror("Error", "Por favor selecciona una carpeta")
            return
        
        # VALIDACIÓN: Verificar que la carpeta existe
        if not os.path.exists(self.folder_path.get()):
            messagebox.showerror("Error", "La carpeta seleccionada no existe")
            return
        
        # Check if any parameters are selected (permite procesar sin modificar)
        selected_params = [param for param, var in self.param_vars.items() if var.get() != "ignore"]
        # No necesita validación - siempre permite continuar
        
        # Disable button during processing
        for widget in self.root.winfo_children():
            self.disable_widgets(widget)
        
        # Start processing thread
        thread = threading.Thread(target=self.process_files)
        thread.daemon = True
        thread.start()
    
    def disable_widgets(self, widget):
        """Recursively disable all widgets"""
        try:
            widget.configure(state='disabled')
        except:
            pass
        for child in widget.winfo_children():
            self.disable_widgets(child)
    
    def enable_widgets(self, widget):
        """Recursively enable all widgets"""
        try:
            widget.configure(state='normal')
        except:
            pass
        for child in widget.winfo_children():
            self.enable_widgets(child)
    
    def process_files(self):
        """Process all PNG files in the selected folder"""
        try:
            folder = Path(self.folder_path.get())
            
            # Find all PNG files
            png_files = list(folder.glob("*.png"))
            
            if not png_files:
                self.log_message("No se encontraron archivos PNG en la carpeta")
                return
            
            self.log_message(f"Iniciando procesamiento de {len(png_files)} archivos PNG...")
            
            # Show selected parameters
            selected_params = [(param, var.get()) for param, var in self.param_vars.items() if var.get() != "ignore"]
            if selected_params:
                param_settings = [f"{param}={setting}" for param, setting in selected_params]
                self.log_message(f"Parámetros a modificar: {', '.join(param_settings)}")
            else:
                self.log_message("Modo análisis: No se modificarán parámetros, solo se analizarán los archivos")
            
            processed = 0
            modified = 0
            skipped = 0
            errors = 0
            
            for i, file_path in enumerate(png_files):
                # Update progress
                progress = (i / len(png_files)) * 100
                self.progress_var.set(progress)
                self.status_var.set(f"Procesando: {file_path.name}")
                
                # Process file
                result = self.process_character_file(file_path)
                self.log_message(f"{file_path.name}: {result}")
                
                # Count results
                processed += 1
                if "✓ Modificado" in result:
                    modified += 1
                elif "✓ Saltado" in result:
                    skipped += 1
                elif "❌" in result:
                    errors += 1
            
            # Final results
            self.progress_var.set(100)
            self.status_var.set("Procesamiento completado")
            
            summary = f"\n=== RESUMEN ===\n"
            summary += f"Archivos procesados: {processed}\n"
            summary += f"Archivos modificados: {modified}\n"
            summary += f"Archivos saltados: {skipped}\n"
            summary += f"Errores: {errors}\n"
            
            self.log_message(summary)
            
            messagebox.showinfo("Completado", summary)
            
        except Exception as e:
            error_msg = f"Error durante el procesamiento: {str(e)}\n{traceback.format_exc()}"
            self.log_message(error_msg)
            messagebox.showerror("Error", error_msg)
        
        finally:
            # Re-enable widgets
            for widget in self.root.winfo_children():
                self.enable_widgets(widget)
            
            self.status_var.set("Listo para procesar")
            self.progress_var.set(0)

def main():
    root = tk.Tk()
    app = KoikatsuHEditor(root)
    root.mainloop()

if __name__ == "__main__":
    main()