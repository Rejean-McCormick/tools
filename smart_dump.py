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
    def __init__(self, root_dir: Path, output_dir: Path, top_n_count: int, 
                 ignore_txt: bool, ignore_md: bool, only_md: bool, 
                 custom_excludes: List[Path], log_callback):
        self.root_dir = root_dir.resolve()
        self.output_dir = output_dir.resolve()
        self.top_n_count = top_n_count
        self.ignore_txt = ignore_txt
        self.ignore_md = ignore_md
        self.only_md = only_md
        # Resolve all custom exclusions to absolute paths for comparison
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

    def match_ignore(self, name: str, patterns: list) -> bool:
        for pat in patterns:
            if fnmatch.fnmatch(name, pat.rstrip("/")):
                return True
        return False

    def is_custom_excluded(self, path: Path) -> bool:
        """
        Checks if the path is explicitly excluded or inside an excluded folder.
        """
        path = path.resolve()
        for exc in self.custom_excludes:
            # Check if it is the excluded path OR inside it
            if path == exc or exc in path.parents:
                return True
        return False

    def get_file_size(self, f: Path) -> int:
        try:
            return f.stat().st_size
        except:
            return 0

    def collect_files(self) -> List[Path]:
        valid_files = []
        git_patterns = self.load_gitignore()
        
        self.log("Scanning directories...")
        
        for dirpath, dirnames, filenames in os.walk(self.root_dir, followlinks=True):
            current_dir = Path(dirpath).resolve()

            # 1. Prune Directories (In-place)
            # We filter out standard ignore dirs AND custom excluded dirs
            safe_dirs = []
            for d in dirnames:
                full_dir_path = current_dir / d
                
                # Check standard ignore
                if d in self.ALWAYS_IGNORE_DIRS: continue
                # Check gitignore
                if self.match_ignore(d, git_patterns): continue
                # Check custom exclusions
                if self.is_custom_excluded(full_dir_path): 
                    # self.log(f"Skipping custom excluded folder: {d}")
                    continue
                
                safe_dirs.append(d)
            
            dirnames[:] = safe_dirs
            
            # 2. Process Files
            for f in filenames:
                fpath = current_dir / f
                ext = fpath.suffix.lower()

                # Global binary/junk exclusions
                if ext in self.ALWAYS_IGNORE_EXT: continue
                if self.match_ignore(f, git_patterns): continue
                
                # Custom Exclusions (File level)
                if self.is_custom_excluded(fpath): continue

                # Specific Format Logic
                if self.only_md:
                    if ext != ".md": continue
                else:
                    if self.ignore_txt and ext == ".txt": continue
                    if self.ignore_md and ext == ".md": continue

                valid_files.append(fpath)
                
        return valid_files

    def write_dump_file(self, filename: str, files: List[Path], title: str) -> str:
        if not files:
            return ""

        out_path = self.output_dir / filename
        total_files = len(files)
        total_size = sum(self.get_file_size(f) for f in files)
        size_mb = total_size / (1024*1024)

        with out_path.open("w", encoding="utf-8") as out:
            out.write(f"===== {title} =====\n")
            out.write(f"Generated: {datetime.now()}\n")
            out.write(f"Files: {total_files}\n")
            out.write(f"Total Size: {size_mb:.2f} MB\n\n")
            
            out.write("===== INDEX =====\n")
            for f in files:
                try:
                    rel = f.relative_to(self.root_dir).as_posix()
                except ValueError:
                    rel = f.name # Fallback if path issue
                out.write(f" - {rel}\n")
            out.write("===== END INDEX =====\n\n")

            for f in files:
                try:
                    rel = f.relative_to(self.root_dir).as_posix()
                except ValueError:
                    rel = f.name

                out.write(f"\n{'='*60}\nFILE: {rel}\n{'='*60}\n\n")
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                    out.write(text + "\n")
                except Exception as e:
                    out.write(f"[Error reading file: {e}]\n")
        
        self.log(f"-> Created {filename} ({total_files} files)")
        
        return (f"FILE: {filename}\n"
                f"CONTENT: {title}\n"
                f"STATS: {total_files} files, {size_mb:.2f} MB\n"
                f"{'-'*40}\n")

    def run(self):
        try:
            self.log(f"Starting process for: {self.root_dir}")
            if self.custom_excludes:
                self.log(f"Custom exclusions active: {len(self.custom_excludes)} paths.")

            # Setup Output
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            mode_suffix = "_MD_ONLY" if self.only_md else ""
            self.output_dir = self.output_dir / f"smart_dump_{ts}{mode_suffix}"
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"Output folder: {self.output_dir}")

            # Collect
            all_files = self.collect_files()
            self.log(f"Found {len(all_files)} total valid files.")
            
            if not all_files:
                self.log("No files found matching criteria.")
                return

            master_index_content = []

            # ---------------------------------------------------------
            # MODE A: Only MD (7 Alphabetical Bundles)
            # ---------------------------------------------------------
            if self.only_md:
                self.log("Mode: Splitting MD files into 7 bundles alphabetically.")
                # Sort alphabetically by relative path
                try:
                    all_files.sort(key=lambda p: p.relative_to(self.root_dir).as_posix().lower())
                except:
                    all_files.sort(key=lambda p: p.name.lower())
                
                total = len(all_files)
                chunk_size = math.ceil(total / 7)
                
                for i in range(7):
                    start = i * chunk_size
                    end = start + chunk_size
                    chunk_files = all_files[start:end]
                    
                    if not chunk_files:
                        break 
                        
                    fname = f"0{i+1}_md_bundle.md"
                    title = f"MD Bundle {i+1} (Alphabetical)"
                    info = self.write_dump_file(fname, chunk_files, title)
                    if info: master_index_content.append(info)

                index_fname = "08_MASTER_INDEX.md"

            # ---------------------------------------------------------
            # MODE B: Standard Folder Split
            # ---------------------------------------------------------
            else:
                self.log(f"Mode: Splitting by top {self.top_n_count} folders.")
                
                root_files = []
                folder_groups: Dict[str, List[Path]] = {}

                for f in all_files:
                    try:
                        rel = f.relative_to(self.root_dir)
                    except ValueError:
                        continue # Skip if outside root (shouldn't happen)

                    if len(rel.parts) == 1:
                        root_files.append(f)
                    else:
                        top = rel.parts[0]
                        if top not in folder_groups: folder_groups[top] = []
                        folder_groups[top].append(f)

                ranked = []
                for name, f_list in folder_groups.items():
                    size = sum(self.get_file_size(f) for f in f_list)
                    ranked.append((name, size, f_list))
                ranked.sort(key=lambda x: x[1], reverse=True)

                file_counter = 1
                
                # Top N
                top_n = ranked[:self.top_n_count]
                remaining = ranked[self.top_n_count:]
                
                for name, _, f_list in top_n:
                    fname = f"{file_counter:02d}_BIG_{name}.txt"
                    info = self.write_dump_file(fname, f_list, f"Top Folder: {name}")
                    if info: master_index_content.append(info)
                    file_counter += 1

                # Remaining
                remaining_files = [f for _, _, fl in remaining for f in fl]
                if remaining_files:
                    fname = f"{file_counter:02d}_Remaining_Folders.txt"
                    info = self.write_dump_file(fname, remaining_files, "All Other Folders")
                    if info: master_index_content.append(info)
                    file_counter += 1

                # Root
                if root_files:
                    fname = f"{file_counter:02d}_Root_Files.txt"
                    info = self.write_dump_file(fname, root_files, "Root Directory Files")
                    if info: master_index_content.append(info)
                    file_counter += 1
                
                index_fname = f"{file_counter:02d}_MASTER_INDEX.txt"

            # Write Master Index
            with (self.output_dir / index_fname).open("w", encoding="utf-8") as f:
                f.write(f"===== MASTER INDEX ({ts}) =====\n")
                f.write(f"Source: {self.root_dir}\n")
                f.write(f"Mode: {'Only MD (7 Bundles)' if self.only_md else 'Standard Smart Split'}\n\n")
                f.write("\n".join(master_index_content))
            
            self.log(f"-> Created {index_fname}")
            self.log("\nDONE! You can close this window.")
            messagebox.showinfo("Success", f"Dumps generated in:\n{self.output_dir}")

        except Exception as e:
            self.log(f"CRITICAL ERROR: {e}")
            messagebox.showerror("Error", str(e))

# --------------------------------------------------------------------
# GUI Application
# --------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Smart Code Dumper v4")
        self.geometry("600x750")  # Increased height for new fields
        
        # Styles
        pad_opts = {'padx': 10, 'pady': 5}
        
        # 1. Repo Selection
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

        tk.Label(lbl_frame, text="Largest Folders to Split:").grid(row=2, column=0, sticky="w")
        self.spin_split = tk.Spinbox(lbl_frame, from_=1, to=20, width=5)
        self.spin_split.delete(0, "end")
        self.spin_split.insert(0, 4)
        self.spin_split.grid(row=2, column=1, sticky="w", padx=5)

        # ---------------------------------------------------
        # NEW: Custom Exclusions
        # ---------------------------------------------------
        self.frame_excludes = tk.LabelFrame(self, text="Custom Path Exclusions", padx=10, pady=10)
        self.frame_excludes.pack(fill="x", **pad_opts)

        tk.Label(self.frame_excludes, text="Quantity of paths to exclude:").grid(row=0, column=0, sticky="w")
        
        # Quantity Selector (0-5)
        self.spin_exclude_qty = tk.Spinbox(self.frame_excludes, from_=0, to=5, width=5, 
                                           command=self.update_exclusion_widgets)
        self.spin_exclude_qty.delete(0, "end")
        self.spin_exclude_qty.insert(0, 0) # Default 0
        self.spin_exclude_qty.grid(row=0, column=1, sticky="w", padx=5)

        # Container for the dynamic rows
        self.frame_dynamic_excludes = tk.Frame(self.frame_excludes)
        self.frame_dynamic_excludes.grid(row=1, column=0, columnspan=3, sticky="we", pady=5)
        
        self.exclusion_entries = [] # To store Entry widgets

        # ---------------------------------------------------
        # Filters & Modes
        # ---------------------------------------------------
        opts_frame = tk.LabelFrame(self, text="Filters & Modes", padx=10, pady=10)
        opts_frame.pack(fill="x", **pad_opts)

        self.var_ignore_txt = tk.BooleanVar(value=False)
        self.var_ignore_md = tk.BooleanVar(value=False)
        self.var_only_md = tk.BooleanVar(value=False)

        chk_txt = tk.Checkbutton(opts_frame, text="Ignore .txt files", variable=self.var_ignore_txt)
        chk_txt.grid(row=0, column=0, sticky="w", padx=10)

        self.chk_md = tk.Checkbutton(opts_frame, text="Ignore .md files", variable=self.var_ignore_md)
        self.chk_md.grid(row=0, column=1, sticky="w", padx=10)

        chk_only_md = tk.Checkbutton(opts_frame, text="Only select .md (Bundles: 7 pkgs + Index)", 
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
        # 1. Clear existing widgets
        for widget in self.frame_dynamic_excludes.winfo_children():
            widget.destroy()
        self.exclusion_entries.clear()

        # 2. Get count
        try:
            count = int(self.spin_exclude_qty.get())
        except ValueError:
            count = 0

        # 3. Build new rows
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
            split_n = int(self.spin_split.get())
        except ValueError:
            messagebox.showerror("Error", "Split count must be a number")
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
                             args=(Path(repo), Path(out), split_n, ign_txt, ign_md, only_md, custom_excludes_paths))
        t.start()

    def run_process(self, repo, out, split_n, ign_txt, ign_md, only_md, custom_excludes):
        worker = DumpWorker(repo, out, split_n, ign_txt, ign_md, only_md, custom_excludes, self.log)
        worker.run()
        self.btn_run.config(state="normal", text="GENERATE DUMPS")

if __name__ == "__main__":
    app = App()
    app.mainloop()