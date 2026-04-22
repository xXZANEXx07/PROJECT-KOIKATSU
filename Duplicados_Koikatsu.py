import os
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from PIL import Image, ImageTk
from kkloader import KoikatuCharaData
import numpy as np
from skimage.metrics import structural_similarity as ssim
import shutil
from threading import Thread
import json
import logging
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from datetime import datetime
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class CardMetadata:
    path: str
    firstname: str = ""
    lastname: str = ""
    nickname: str = ""
    personality: str = ""
    sex: str = ""
    height: float = 0
    bust: float = 0
    waist: float = 0
    hip: float = 0
    file_hash: str = ""
    file_size: int = 0

class SettingsManager:
    def __init__(self, config_file="duplicate_viewer_config.json"):
        self.config_file = config_file
        self.default_settings = {
            "similarity_threshold_metadata": 0.90,
            "similarity_threshold_image": 0.97,
            "max_threads": 4,
            "thumbnail_size": (180, 180),
            "image_preview_size": (64, 64),
            "auto_save_session": True,
            "backup_before_move": True
        }
        self.settings = self.load_settings()
    
    def load_settings(self) -> Dict:
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return {**self.default_settings, **json.load(f)}
        except Exception as e:
            logger.warning(f"Error cargando configuración: {e}")
        return self.default_settings.copy()
    
    def save_settings(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error guardando configuración: {e}")
    
    def get(self, key: str, default=None):
        return self.settings.get(key, default)
    
    def set(self, key: str, value):
        self.settings[key] = value
        self.save_settings()

class CardProcessor:
    def __init__(self, settings_manager: SettingsManager):
        self.settings = settings_manager
        self.processed_cards: List[CardMetadata] = []
        self.image_cache: Dict[str, np.ndarray] = {}
    
    def calculate_file_hash(self, filepath: str) -> str:
        try:
            with open(filepath, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"Error calculando hash para {filepath}: {e}")
            return ""
    
    def load_card_metadata(self, filepath: str) -> Optional[CardMetadata]:
        try:
            file_size = os.path.getsize(filepath)
            file_hash = self.calculate_file_hash(filepath)
            
            kc = KoikatuCharaData.load(filepath)
            param = kc["Parameter"].data
            
            metadata = CardMetadata(
                path=filepath,
                firstname=param.get("firstname", ""),
                lastname=param.get("lastname", ""),
                nickname=param.get("nickname", ""),
                personality=param.get("personality", ""),
                sex=param.get("sex", ""),
                height=param.get("height", 0),
                bust=param.get("bust", 0),
                waist=param.get("waist", 0),
                hip=param.get("hip", 0),
                file_hash=file_hash,
                file_size=file_size
            )
            
            with Image.open(filepath).convert("L").resize(self.settings.get("image_preview_size", (64, 64))) as img:
                self.image_cache[filepath] = np.array(img)
            
            return metadata
        except Exception as e:
            logger.error(f"Error cargando carta {filepath}: {e}")
            return None
    
    def calculate_metadata_similarity(self, card1: CardMetadata, card2: CardMetadata) -> float:
        if card1.file_hash and card2.file_hash and card1.file_hash == card2.file_hash:
            return 1.0
        
        matches = sum([
            card1.firstname == card2.firstname, card1.lastname == card2.lastname,
            card1.nickname == card2.nickname, card1.personality == card2.personality,
            card1.sex == card2.sex, abs(card1.height - card2.height) <= 1,
            abs(card1.bust - card2.bust) <= 1, abs(card1.waist - card2.waist) <= 1,
            abs(card1.hip - card2.hip) <= 1
        ])
        return matches / 9
    
    def calculate_image_similarity(self, path1: str, path2: str) -> float:
        try:
            if path1 not in self.image_cache or path2 not in self.image_cache:
                return 0.0
            score, _ = ssim(self.image_cache[path1], self.image_cache[path2], full=True)
            return score
        except Exception as e:
            logger.error(f"Error calculando similitud: {e}")
            return 0.0
    
    def find_duplicate_groups(self, cards: List[CardMetadata]) -> List[List[Tuple[str, float]]]:
        groups = []
        used_indices = set()
        
        for i, card1 in enumerate(cards):
            if i in used_indices:
                continue
            
            current_group = [(card1.path, 1.0)]
            used_indices.add(i)
            
            for j, card2 in enumerate(cards[i+1:], start=i+1):
                if j in used_indices:
                    continue
                
                metadata_sim = self.calculate_metadata_similarity(card1, card2)
                if metadata_sim >= self.settings.get("similarity_threshold_metadata", 0.90):
                    image_sim = self.calculate_image_similarity(card1.path, card2.path)
                    if image_sim >= self.settings.get("similarity_threshold_image", 0.97):
                        current_group.append((card2.path, metadata_sim))
                        used_indices.add(j)
            
            if len(current_group) > 1:
                groups.append(current_group)
        
        return groups

class SettingsWindow:
    def __init__(self, parent, settings_manager: SettingsManager):
        self.parent = parent
        self.settings = settings_manager
        self.window = tk.Toplevel(parent)
        self.window.title("Configuración")
        self.window.geometry("400x400")
        self.window.configure(bg="#2e2e2e")
        self.window.transient(parent)
        self.window.grab_set()
        self.create_widgets()
    
    def create_widgets(self):
        main_frame = tk.Frame(self.window, bg="#2e2e2e")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        self.scales = {}
        configs = [
            ("Umbral Metadatos:", "metadata_threshold", 0.5, 1.0, 0.01, "similarity_threshold_metadata"),
            ("Umbral Imagen:", "image_threshold", 0.5, 1.0, 0.01, "similarity_threshold_image"),
            ("Hilos:", "max_threads", 1, 8, 1, "max_threads")
        ]
        
        for label_text, var_name, from_, to, resolution, setting_key in configs:
            tk.Label(main_frame, text=label_text, fg="white", bg="#2e2e2e").pack(anchor="w")
            scale = tk.Scale(main_frame, from_=from_, to=to, resolution=resolution,
                           orient="horizontal", bg="#444", fg="white", troughcolor="#666")
            scale.set(self.settings.get(setting_key, 0.90 if "threshold" in setting_key else 4))
            scale.pack(fill="x", pady=(0, 10))
            self.scales[var_name] = (scale, setting_key)
        
        btn_frame = tk.Frame(main_frame, bg="#2e2e2e")
        btn_frame.pack(fill="x", pady=20)
        
        tk.Button(btn_frame, text="Guardar", command=self.save_settings, 
                 bg="#0078D7", fg="white", padx=20).pack(side="right", padx=5)
        tk.Button(btn_frame, text="Cancelar", command=self.window.destroy, 
                 bg="#666", fg="white", padx=20).pack(side="right")
    
    def save_settings(self):
        for var_name, (scale, setting_key) in self.scales.items():
            self.settings.set(setting_key, scale.get())
        messagebox.showinfo("Configuración", "Configuración guardada")
        self.window.destroy()

class DuplicateGroupViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Koikatsu Duplicate Groups Viewer - Compacto")
        self.geometry("1200x900")
        self.configure(bg="#2e2e2e")
        
        self.settings_manager = SettingsManager()
        self.card_processor = CardProcessor(self.settings_manager)
        
        self.setup_ui()
        self.setup_bindings()
        
        self.folder = None
        self.duplicates_groups = []
        self.current_group_idx = 0
        self.is_scanning = False
        
        logger.info("Aplicación iniciada")
    
    def setup_ui(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Archivo", menu=file_menu)
        file_menu.add_command(label="Seleccionar Carpeta", command=self.select_folder)
        file_menu.add_command(label="Exportar Reporte", command=self.export_report)
        
        btn_frame = tk.Frame(self, bg="#2e2e2e")
        btn_frame.pack(pady=10, fill="x", padx=10)
        
        buttons = [
            ("📁 Carpeta", self.select_folder, "left"),
            ("🔍 Escanear", self.threaded_scan, "left"),
            ("📦 Mover Actual", self.move_duplicates, "left"),
            ("🚀 Mover Todos", self.move_all_duplicates, "left"),
            ("⚙️ Config", self.open_settings, "left")
        ]
        
        for text, cmd, side in buttons:
            btn = ttk.Button(btn_frame, text=text, command=cmd)
            btn.pack(side=side, padx=2)
            if "Escanear" in text:
                self.scan_button = btn
            elif "Mover" in text:
                if "Todos" in text:
                    self.move_all_button = btn
                else:
                    self.move_button = btn
        
        nav_frame = tk.Frame(btn_frame, bg="#2e2e2e")
        nav_frame.pack(side="right")
        
        for text, cmd in [("⬅️ Ant", self.prev_group), ("➡️ Sig", self.next_group)]:
            ttk.Button(nav_frame, text=text, command=cmd).pack(side="left", padx=1)
        
        self.status_label = tk.Label(self, text="Seleccione carpeta y escanee", 
                                   fg="white", bg="#2e2e2e", anchor="w")
        self.status_label.pack(fill="x", padx=10, pady=5)
        
        self.progress_bar = ttk.Progressbar(self, orient="horizontal")
        self.progress_bar.pack(fill="x", padx=10, pady=5)
        
        content_frame = tk.Frame(self, bg="#2e2e2e")
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.canvas = tk.Canvas(content_frame, bg="#222")
        scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        
        self.scrollable_frame = tk.Frame(self.canvas, bg="#222")
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.scrollable_frame.bind("<Configure>", 
                                  lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
    
    def setup_bindings(self):
        bindings = [("<z>", self.prev_group), ("<x>", self.next_group), ("<F5>", self.threaded_scan)]
        for key, cmd in bindings:
            self.bind(key, lambda e, command=cmd: command())
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
    
    def select_folder(self):
        folder = filedialog.askdirectory(title="Seleccionar carpeta con cartas")
        if folder:
            self.folder = folder
            self.status_label.config(text=f"Carpeta: {os.path.basename(folder)}")
            self.clear_display()
    
    def open_settings(self):
        SettingsWindow(self, self.settings_manager)
    
    def threaded_scan(self):
        if self.is_scanning or not self.folder:
            return
        
        self.is_scanning = True
        self.scan_button.config(state="disabled", text="🔄 Escaneando...")
        Thread(target=self.scan_duplicates, daemon=True).start()
    
    def scan_duplicates(self):
        try:
            self.clear_display()
            self.duplicates_groups = []
            
            png_files = [os.path.join(root, file) for root, dirs, files in os.walk(self.folder) 
                        for file in files if file.lower().endswith(".png")]
            
            if len(png_files) < 2:
                self.after(0, lambda: self.status_label.config(text="Pocos archivos para comparar"))
                return
            
            self.after(0, lambda: self.progress_bar.config(maximum=len(png_files), value=0))
            
            cards = []
            with ThreadPoolExecutor(max_workers=self.settings_manager.get("max_threads", 4)) as executor:
                futures = {executor.submit(self.card_processor.load_card_metadata, file): file for file in png_files}
                
                for i, future in enumerate(as_completed(futures)):
                    self.after(0, lambda i=i: self.progress_bar.config(value=i+1))
                    card = future.result()
                    if card:
                        cards.append(card)
            
            if len(cards) < 2:
                self.after(0, lambda: self.status_label.config(text="Cartas válidas insuficientes"))
                return
            
            groups = self.card_processor.find_duplicate_groups(cards)
            
            if not groups:
                self.after(0, lambda: self.status_label.config(text="Sin duplicados"))
                return
            
            self.duplicates_groups = groups
            self.current_group_idx = 0
            
            total_duplicates = sum(len(group) for group in groups)
            self.after(0, lambda: self.status_label.config(
                text=f"{len(groups)} grupos, {total_duplicates} duplicados"))
            self.after(0, self.show_group)
            
        except Exception as e:
            logger.error(f"Error en escaneo: {e}")
            self.after(0, lambda: self.status_label.config(text=f"Error: {str(e)}"))
        finally:
            self.is_scanning = False
            self.after(0, lambda: self.scan_button.config(state="normal", text="🔍 Escanear"))
    
    def clear_display(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
    
    def show_group(self):
        self.clear_display()
        
        if not self.duplicates_groups:
            return
        
        group = self.duplicates_groups[self.current_group_idx]
        self.status_label.config(text=f"Grupo {self.current_group_idx + 1}/{len(self.duplicates_groups)} ({len(group)} cartas)")
        
        for idx, (path, sim) in enumerate(group):
            try:
                row, col = divmod(idx, 5)
                
                with Image.open(path) as img:
                    img.thumbnail((180, 180), Image.Resampling.LANCZOS)
                    img_tk = ImageTk.PhotoImage(img)
                
                card_frame = tk.Frame(self.scrollable_frame, bg="#333", relief="raised", bd=2)
                card_frame.grid(row=row, column=col, padx=5, pady=5, sticky="n")
                
                lbl_img = tk.Label(card_frame, image=img_tk, bg="#333")
                lbl_img.image = img_tk
                lbl_img.pack(padx=5, pady=5)
                
                info_text = f"{os.path.basename(path)}\nSim: {sim*100:.1f}%"
                tk.Label(card_frame, text=info_text, fg="white", bg="#333", 
                        font=("Arial", 8), wraplength=170).pack(padx=5, pady=5)
                
            except Exception as e:
                logger.error(f"Error mostrando {path}: {e}")
        
        self.after(100, lambda: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
    
    def get_character_folder_name(self, metadata: CardMetadata) -> str:
        if not metadata:
            return "sin_nombre"
        
        name_parts = []
        if metadata.firstname.strip():
            name_parts.append(metadata.firstname.strip())
        if metadata.lastname.strip():
            name_parts.append(metadata.lastname.strip())
        
        if name_parts:
            full_name = " ".join(name_parts).replace(" ", "_")
            full_name = "".join(c for c in full_name if c.isalnum() or c in "_-")
            return full_name
        else:
            return "sin_nombre"
    
    def get_unique_folder_path(self, base_name: str) -> str:
        path = os.path.join(self.folder, base_name)
        if not os.path.exists(path):
            return path
        
        counter = 1
        while True:
            numbered_path = os.path.join(self.folder, f"{base_name}_{counter}")
            if not os.path.exists(numbered_path):
                return numbered_path
            counter += 1

    def move_duplicates(self):
        if not self.duplicates_groups:
            return

        group = self.duplicates_groups[self.current_group_idx]
        original_card_path = group[0][0]
        
        metadata = self.card_processor.load_card_metadata(original_card_path)
        folder_name = self.get_character_folder_name(metadata)
        character_folder = self.get_unique_folder_path(folder_name)

        try:
            os.makedirs(character_folder, exist_ok=True)
            
            moved_count = 0
            for path, _ in group:
                try:
                    shutil.move(path, character_folder)
                    moved_count += 1
                except Exception as e:
                    logger.error(f"Error moviendo {path}: {e}")

            self.status_label.config(text=f"Movidos {moved_count} a '{os.path.basename(character_folder)}'")
            
            self.duplicates_groups.pop(self.current_group_idx)
            if self.current_group_idx >= len(self.duplicates_groups):
                self.current_group_idx = max(0, len(self.duplicates_groups) - 1)

            if self.duplicates_groups:
                self.show_group()
            else:
                self.clear_display()
                self.status_label.config(text="Todos los grupos procesados")
                
        except Exception as e:
            self.status_label.config(text=f"Error: {e}")

    def move_all_duplicates(self):
        if not self.duplicates_groups:
            self.status_label.config(text="No hay duplicados para mover")
            return
        
        if not messagebox.askyesno("Confirmar", f"¿Mover todos los {len(self.duplicates_groups)} grupos de duplicados?"):
            return
        
        total_moved = 0
        total_errors = 0
        
        for i, group in enumerate(self.duplicates_groups):
            try:
                original_card_path = group[0][0]
                metadata = self.card_processor.load_card_metadata(original_card_path)
                folder_name = self.get_character_folder_name(metadata)
                
                if folder_name == "sin_nombre":
                    folder_name = f"sin_nombre_{i+1}"
                
                character_folder = self.get_unique_folder_path(folder_name)
                os.makedirs(character_folder, exist_ok=True)
                
                for path, _ in group:
                    try:
                        shutil.move(path, character_folder)
                        total_moved += 1
                    except Exception as e:
                        logger.error(f"Error moviendo {path}: {e}")
                        total_errors += 1
                        
            except Exception as e:
                logger.error(f"Error procesando grupo {i+1}: {e}")
                total_errors += len(group)
        
        self.duplicates_groups.clear()
        self.clear_display()
        
        if total_errors == 0:
            self.status_label.config(text=f"¡Éxito! Movidos {total_moved} archivos a sus carpetas")
        else:
            self.status_label.config(text=f"Movidos {total_moved} archivos, {total_errors} errores")
    
    def next_group(self):
        if self.duplicates_groups and self.current_group_idx < len(self.duplicates_groups) - 1:
            self.current_group_idx += 1
            self.show_group()
    
    def prev_group(self):
        if self.duplicates_groups and self.current_group_idx > 0:
            self.current_group_idx -= 1
            self.show_group()
    
    def export_report(self):
        if not self.duplicates_groups:
            messagebox.showwarning("Advertencia", "No hay duplicados para exportar")
            return
        
        filename = filedialog.asksaveasfilename(defaultextension=".txt",
                                              filetypes=[("Texto", "*.txt"), ("JSON", "*.json")])
        if not filename:
            return
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"REPORTE DE DUPLICADOS\nCarpeta: {self.folder}\nGrupos: {len(self.duplicates_groups)}\n\n")
                
                for i, group in enumerate(self.duplicates_groups, 1):
                    f.write(f"GRUPO {i}:\n")
                    for path, sim in group:
                        f.write(f"  {os.path.basename(path)} ({sim*100:.1f}%)\n")
                    f.write("\n")
            
            messagebox.showinfo("Éxito", f"Reporte exportado: {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Error exportando: {e}")

if __name__ == "__main__":
    try:
        app = DuplicateGroupViewer()
        app.mainloop()
    except Exception as e:
        logger.critical(f"Error crítico: {e}")
        messagebox.showerror("Error", f"Error crítico: {e}")