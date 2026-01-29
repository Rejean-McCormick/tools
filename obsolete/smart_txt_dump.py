import os
import sys
import fnmatch
import math
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
import threading

# --------------------------------------------------------------------
# Core Logic (The Worker)
# --------------------------------------------------------------------

class DumpWorker:
    def __init__(self, root_dir: Path, output_dir: Path, max_output_files: int, 
                 ignore_txt: bool, ignore_md: bool, only_md: bool, 
                 custom_excludes: List[Path], log_callback):
        self.root_dir = root_dir.resolve()
        self.output_dir = output_dir.resolve()
        
        # User limit (Target maximum files generated)
        self.max_output_files = max(3, max_output_files) 
        
        self.ignore_txt = ignore_txt
        self.ignore_md = ignore_md
        self.only_md = only_md
        self.custom_excludes = [p.resolve() for p in custom_excludes]
        self.log = log_callback
        
        # Standard Exclusions
        self.ALWAYS_IGNORE_DIRS = {
            ".git", ".svn", ".hg", ".idea", ".vscode", 
            "node_modules", "venv", ".venv", "env", 
            "__pycache__", ".mypy_cache", ".pytest_cache",
            "dist", "build", "coverage", "target", "out",
            "abstract_wiki_architect.egg-info"
        }
        self.ALWAYS_IGNORE_EXT = {
            ".pyc", ".pyo", ".pyd", ".exe", ".dll", ".so", ".dylib", 
            ".bin", ".iso", ".img", ".log", ".sqlite", ".db", ".zip", ".gz",
            ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".lock"
        }
        
        # Cache gitignore patterns
        self.git_patterns = self.load_gitignore()

    def load_gitignore(self) -> list:
        patterns = []
        gitignore = self.root_dir / ".gitignore"
        if gitignore.exists():
            try:
                with gitignore.open("r", encoding="utf-8") as f:
                    patterns = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                self.log(f"-> Loaded .gitignore ({len(patterns)} rules active).")
            except Exception as e:
                self.log(f"Error reading .gitignore: {e}")
        else:
            self.log("-> No .gitignore found. Using standard exclusions only.")
        return patterns

    def match_ignore(self, name: str) -> bool:
        for pat in self.git_patterns:
            if fnmatch.fnmatch(name, pat.rstrip("/")):
                return True
        return False

    def is_custom_excluded(self, path: Path) -> bool:
        path = path.resolve()
        for exc in self.custom_excludes:
            if path == exc or exc in path.parents:
                return True
        return False

    def get_file_size(self, f: Path) -> int:
        try:
            return f.stat().st_size
        except:
            return 0

    def collect_files_in_folder(self, folder_path: Path, recursive: bool = True) -> List[Path]:
        """
        Collects valid files within a specific folder. 
        If recursive=False, only scans immediate children (used for Root).
        """
        valid_files = []
        
        if recursive:
            iterator = os.walk(folder_path, followlinks=True)
        else:
            # Fake an os.walk for just one level
            try:
                # next() gets the first tuple (current, dirs, files)
                iterator = [next(os.walk(folder_path, followlinks=True))]
            except StopIteration:
                return []

        for dirpath, dirnames, filenames in iterator:
            current_dir = Path(dirpath).resolve()

            # 1. Prune Directories
            safe_dirs = []
            for d in dirnames:
                full_dir_path = current_dir / d
                if d in self.ALWAYS_IGNORE_DIRS: continue
                if self.match_ignore(d): continue
                if self.is_custom_excluded(full_dir_path): continue
                safe_dirs.append(d)
            
            dirnames[:] = safe_dirs
            
            # 2. Process Files
            for f in filenames:
                fpath = current_dir / f
                ext = fpath.suffix.lower()

                if ext in self.ALWAYS_IGNORE_EXT: continue
                if self.match_ignore(f): continue
                if self.is_custom_excluded(fpath): continue

                if self.only_md:
                    if ext != ".md": continue
                else:
                    if self.ignore_txt and ext == ".txt": continue
                    if self.ignore_md and ext == ".md": continue

                valid_files.append(fpath)
                
        return valid_files

    def write_dump_file(self, filename: str, files: List[Path], title: str) -> dict:
        if not files:
            return None

        out_path = self.output_dir / filename
        total_files = len(files)
        total_size = sum(self.get_file_size(f) for f in files)
        size_mb = total_size / (1024*1024)

        # Sort files inside the dump for readability
        try:
            files.sort(key=lambda p: p.relative_to(self.root_dir).as_posix().lower())
        except:
            files.sort(key=lambda p: p.name.lower())

        with out_path.open("w", encoding="utf-8") as out:
            out.write(f"===== {title} =====\n")
            out.write(f"Generated: {datetime.now()}\n")
            out.write(f"Source: {self.root_dir}\n")
            out.write(f"Files: {total_files} | Size: {size_mb:.2f} MB\n\n")
            
            out.write("===== CONTENTS =====\n")
            for f in files:
                try:
                    rel = f.relative_to(self.root_dir).as_posix()
                except:
                    rel = f.name
                out.write(f" - {rel}\n")
            out.write("\n")

            for f in files:
                try:
                    rel = f.relative_to(self.root_dir).as_posix()
                except:
                    rel = f.name

                out.write(f"\n{'='*60}\nFILE: {rel}\n{'='*60}\n\n")
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                    out.write(text + "\n")
                except Exception as e:
                    out.write(f"[Error reading file: {e}]\n")
        
        self.log(f"-> Created: {filename} ({size_mb:.2f} MB)")
        
        return {
            "filename": filename,
            "title": title,
            "file_list": files,
            "size_mb": size_mb
        }

    def run(self):
        try:
            self.log(f"Scanning structure of: {self.root_dir}")
            
            # Setup Output
            repo_name = self.root_dir.name
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            base_name_pattern = f"{repo_name}_{ts}"
            
            mode_suffix = "_MD_ONLY" if self.only_md else ""
            run_folder_name = f"{base_name_pattern}_Dump{mode_suffix}"
            self.output_dir = self.output_dir / run_folder_name
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"Output: {self.output_dir}")

            # -------------------------------------------------------------
            # STEP 1: ANALYZE ROOT STRUCTURE
            # -------------------------------------------------------------
            
            # A. Get files directly in Root
            root_files = self.collect_files_in_folder(self.root_dir, recursive=False)
            
            # B. Get Top-Level Directories
            top_level_items = []
            try:
                for item in os.listdir(self.root_dir):
                    full_path = self.root_dir / item
                    if full_path.is_dir():
                        if item in self.ALWAYS_IGNORE_DIRS: continue
                        if self.match_ignore(item): continue
                        if self.is_custom_excluded(full_path): continue
                        top_level_items.append(full_path)
            except Exception as e:
                self.log(f"Error scanning root dir: {e}")
                return

            # C. Analyze each folder (collect files & calculate size)
            analyzed_folders = []
            self.log(f"Found {len(top_level_items)} top-level folders. Analyzing contents...")
            
            for folder in top_level_items:
                f_files = self.collect_files_in_folder(folder, recursive=True)
                if f_files: # Only keep folders that have valid content
                    size = sum(self.get_file_size(f) for f in f_files)
                    analyzed_folders.append({
                        'name': folder.name,
                        'files': f_files,
                        'size': size
                    })

            # Sort folders by size (Largest first)
            analyzed_folders.sort(key=lambda x: x['size'], reverse=True)

            # -------------------------------------------------------------
            # STEP 2: DETERMINE PARTITIONING
            # -------------------------------------------------------------
            
            # Slots calculation
            # Max Output = (1 Index) + (1 Root, optional) + (Folders...)
            
            available_slots = self.max_output_files - 1 # Reserve 1 for Master Index
            
            dumps_to_create = [] # List of (Filename, Files, Title)

            # 1. Handle Root Files
            if root_files:
                available_slots -= 1
                fname = f"{base_name_pattern}_ROOT_Files.txt"
                dumps_to_create.append((fname, root_files, "ROOT FILES"))
            
            # 2. Handle Folders
            if not analyzed_folders:
                self.log("No valid folders found.")
            else:
                # If we have more folders than slots, we need an "OTHERS" bin
                if len(analyzed_folders) <= available_slots:
                    # Case A: We have enough slots for every folder
                    for folder in analyzed_folders:
                        fname = f"{base_name_pattern}_{folder['name']}.txt"
                        dumps_to_create.append((fname, folder['files'], f"FOLDER: {folder['name']}"))
                else:
                    # Case B: Too many folders, need to group the smallest ones
                    # Calculate how many individual folders we can keep
                    # We need 1 slot for "OTHERS", so distinct folders = available_slots - 1
                    distinct_count = max(0, available_slots - 1)
                    
                    # Top folders get their own files
                    top_folders = analyzed_folders[:distinct_count]
                    remaining_folders = analyzed_folders[distinct_count:]
                    
                    for folder in top_folders:
                        fname = f"{base_name_pattern}_{folder['name']}.txt"
                        dumps_to_create.append((fname, folder['files'], f"FOLDER: {folder['name']}"))
                    
                    # Combine the rest
                    others_files = []
                    others_names = []
                    for folder in remaining_folders:
                        others_files.extend(folder['files'])
                        others_names.append(folder['name'])
                    
                    if others_files:
                        fname = f"{base_name_pattern}_OTHERS.txt"
                        title = f"OTHERS ({len(remaining_folders)} folders: {', '.join(others_names[:3])}...)"
                        dumps_to_create.append((fname, others_files, title))

            # -------------------------------------------------------------
            # STEP 3: WRITE FILES
            # -------------------------------------------------------------
            
            generated_stats = []
            
            self.log(f"Generating {len(dumps_to_create)} content files...")
            
            for fname, files, title in dumps_to_create:
                info = self.write_dump_file(fname, files, title)
                if info:
                    generated_stats.append(info)

            # -------------------------------------------------------------
            # STEP 4: MASTER INDEX
            # -------------------------------------------------------------
            index_filename = f"{base_name_pattern}_MASTER_INDEX.txt"
            total_source_files = sum(len(stat['file_list']) for stat in generated_stats)
            
            with (self.output_dir / index_filename).open("w", encoding="utf-8") as f:
                f.write(f"===== MASTER INDEX =====\n")
                f.write(f"Repo: {repo_name}\n")
                f.write(f"Source: {self.root_dir}\n")
                f.write(f"Generated: {ts}\n")
                f.write(f"Total Valid Files: {total_source_files}\n")
                f.write(f"Dump Files Created: {len(generated_stats)}\n\n")
                
                f.write("===== FILE MAP =====\n\n")
                
                for stat in generated_stats:
                    d_name = stat['filename']
                    d_title = stat['title']
                    d_count = len(stat['file_list'])
                    d_size = stat['size_mb']
                    
                    f.write(f"FILE: {d_name}\n")
                    f.write(f"Context: {d_title}\n")
                    f.write(f"Stats: {d_count} files, {d_size:.2f} MB\n")
                    f.write(f"Contains:\n")
                    
                    # Sort list for index
                    f_list_sorted = sorted(stat['file_list'], key=lambda x: str(x))
                    
                    for src_file in f_list_sorted:
                        try:
                            rel = src_file.relative_to(self.root_dir).as_posix()
                        except:
                            rel = src_file.name
                        f.write(f"   [x] {rel}\n")
                    f.write(f"\n{'-'*40}\n\n")

            self.log(f"-> Created Master Index: {index_filename}")
            self.log("\nDONE! You can close this window.")
            messagebox.showinfo("Success", f"Dumps generated in:\n{self.output_dir}")

        except Exception as e:
            self.log(f"CRITICAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", str(e))

# --------------------------------------------------------------------
# GUI Application
# --------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Smart Code Dumper v5.0 (Folder-Aware)")
        self.geometry("600x750")
        
        # Styles
        pad_opts = {'padx': 10, 'pady': 5}
        
        # 1. Configuration Frame
        lbl_frame = tk.LabelFrame(self, text="Configuration", padx=10, pady=10)
        lbl_frame.pack(fill="x", **pad_opts)

        # Paths
        tk.Label(lbl_frame, text="Repository Root:").grid(row=0, column=0, sticky="w")
        self.entry_repo = tk.Entry(lbl_frame, width=50)
        self.entry_repo.grid(row=0, column=1, padx=5)
        tk.Button(lbl_frame, text="Browse...", command=self.browse_repo).grid(row=0, column=2)

        tk.Label(lbl_frame, text="Output Folder:").grid(row=1, column=0, sticky="w")
        self.entry_out = tk.Entry(lbl_frame, width=50)
        self.entry_out.grid(row=1, column=1, padx=5)
        tk.Button(lbl_frame, text="Browse...", command=self.browse_out).grid(row=1, column=2)

        # Total Output Files Selector
        tk.Label(lbl_frame, text="Max Output Files Limit:").grid(row=2, column=0, sticky="w")
        self.spin_split = tk.Spinbox(lbl_frame, from_=2, to=50, width=5)
        self.spin_split.delete(0, "end")
        self.spin_split.insert(0, 10) # Default 10
        self.spin_split.grid(row=2, column=1, sticky="w", padx=5)
        
        tk.Label(lbl_frame, text="(Determines when to group small folders into 'OTHERS')", fg="gray", font=("Arial", 8)).grid(row=3, column=1, sticky="w", padx=5)

        # ---------------------------------------------------
        # Custom Exclusions
        # ---------------------------------------------------
        self.frame_excludes = tk.LabelFrame(self, text="Custom Path Exclusions", padx=10, pady=10)
        self.frame_excludes.pack(fill="x", **pad_opts)

        tk.Label(self.frame_excludes, text="Quantity of paths to exclude:").grid(row=0, column=0, sticky="w")
        
        # Quantity Selector (0-5)
        self.spin_exclude_qty = tk.Spinbox(self.frame_excludes, from_=0, to=5, width=5, 
                                           command=self.update_exclusion_widgets)
        self.spin_exclude_qty.delete(0, "end")
        self.spin_exclude_qty.insert(0, 0)
        self.spin_exclude_qty.grid(row=0, column=1, sticky="w", padx=5)

        # Container for the dynamic rows
        self.frame_dynamic_excludes = tk.Frame(self.frame_excludes)
        self.frame_dynamic_excludes.grid(row=1, column=0, columnspan=3, sticky="we", pady=5)
        
        self.exclusion_entries = []

        # ---------------------------------------------------
        # Filters & Modes
        # ---------------------------------------------------
        opts_frame = tk.LabelFrame(self, text="Filters", padx=10, pady=10)
        opts_frame.pack(fill="x", **pad_opts)

        self.var_ignore_txt = tk.BooleanVar(value=False)
        self.var_ignore_md = tk.BooleanVar(value=False)
        self.var_only_md = tk.BooleanVar(value=False)

        chk_txt = tk.Checkbutton(opts_frame, text="Ignore .txt files", variable=self.var_ignore_txt)
        chk_txt.grid(row=0, column=0, sticky="w", padx=10)

        self.chk_md = tk.Checkbutton(opts_frame, text="Ignore .md files", variable=self.var_ignore_md)
        self.chk_md.grid(row=0, column=1, sticky="w", padx=10)

        chk_only_md = tk.Checkbutton(opts_frame, text="Scan only .md files", 
                                     variable=self.var_only_md, command=self.toggle_md_mode)
        chk_only_md.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=5)

        tk.Label(opts_frame, 
                 text="Note: .gitignore rules & standard junk (node_modules, .git) are always excluded.",
                 fg="gray", font=("Arial", 8, "italic")
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

        # 2. Action
        self.btn_run = tk.Button(self, text="GENERATE DUMPS", bg="#dddddd", height=2, command=self.start_thread)
        self.btn_run.pack(fill="x", padx=20, pady=10)

        # 3. Log
        self.txt_log = scrolledtext.ScrolledText(self, height=12)
        self.txt_log.pack(fill="both", expand=True, padx=10, pady=10)

    def update_exclusion_widgets(self):
        """Rebuilds the exclusion path rows based on the spinbox value."""
        for widget in self.frame_dynamic_excludes.winfo_children():
            widget.destroy()
        self.exclusion_entries.clear()

        try:
            count = int(self.spin_exclude_qty.get())
        except ValueError:
            count = 0

        for i in range(count):
            row_frame = tk.Frame(self.frame_dynamic_excludes)
            row_frame.pack(fill="x", pady=2)
            
            tk.Label(row_frame, text=f"Path {i+1}:").pack(side="left")
            
            entry = tk.Entry(row_frame)
            entry.pack(side="left", fill="x", expand=True, padx=5)
            self.exclusion_entries.append(entry)
            
            btn = tk.Button(row_frame, text="Browse", 
                            command=lambda e=entry: self.browse_exclusion(e))
            btn.pack(side="right")

    def browse_exclusion(self, entry_widget):
        d = filedialog.askdirectory(title="Select Folder to Exclude")
        if d:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, d)

    def toggle_md_mode(self):
        if self.var_only_md.get():
            self.var_ignore_md.set(False)
            self.chk_md.config(state="disabled")
        else:
            self.chk_md.config(state="normal")

    def browse_repo(self):
        d = filedialog.askdirectory()
        if d:
            self.entry_repo.delete(0, tk.END)
            self.entry_repo.insert(0, d)
            p = Path(d)
            parent = p.parent
            self.entry_out.delete(0, tk.END)
            self.entry_out.insert(0, str(parent))

    def browse_out(self):
        d = filedialog.askdirectory()
        if d:
            self.entry_out.delete(0, tk.END)
            self.entry_out.insert(0, d)

    def log(self, msg):
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)

    def start_thread(self):
        repo = self.entry_repo.get()
        out = self.entry_out.get()
        
        try:
            max_files = int(self.spin_split.get())
        except ValueError:
            messagebox.showerror("Error", "Max files must be a number")
            return

        if not repo or not os.path.isdir(repo):
            messagebox.showerror("Error", "Please select a valid repository folder.")
            return

        # Gather Custom Exclusions
        custom_excludes_paths = []
        for entry in self.exclusion_entries:
            val = entry.get().strip()
            if val:
                custom_excludes_paths.append(Path(val))

        self.btn_run.config(state="disabled", text="Running...")
        self.txt_log.delete(1.0, tk.END)
        
        ign_txt = self.var_ignore_txt.get()
        ign_md = self.var_ignore_md.get()
        only_md = self.var_only_md.get()

        t = threading.Thread(target=self.run_process, 
                             args=(Path(repo), Path(out), max_files, ign_txt, ign_md, only_md, custom_excludes_paths))
        t.start()

    def run_process(self, repo, out, max_files, ign_txt, ign_md, only_md, custom_excludes):
        worker = DumpWorker(repo, out, max_files, ign_txt, ign_md, only_md, custom_excludes, self.log)
        worker.run()
        self.btn_run.config(state="normal", text="GENERATE DUMPS")

if __name__ == "__main__":
    app = App()
    app.mainloop()