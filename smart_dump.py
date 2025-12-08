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
                 ignore_txt: bool, ignore_md: bool, only_md: bool, log_callback):
        self.root_dir = root_dir
        self.output_dir = output_dir
        self.top_n_count = top_n_count
        self.ignore_txt = ignore_txt
        self.ignore_md = ignore_md
        self.only_md = only_md
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
            # Prune directories
            dirnames[:] = [d for d in dirnames 
                           if d not in self.ALWAYS_IGNORE_DIRS 
                           and not self.match_ignore(d, git_patterns)]
            
            for f in filenames:
                fpath = Path(dirpath) / f
                ext = fpath.suffix.lower()

                # 1. Global binary/junk exclusions
                if ext in self.ALWAYS_IGNORE_EXT: continue
                if self.match_ignore(f, git_patterns): continue
                
                # 2. Specific Format Logic
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
                out.write(f" - {f.relative_to(self.root_dir).as_posix()}\n")
            out.write("===== END INDEX =====\n\n")

            for f in files:
                rel = f.relative_to(self.root_dir).as_posix()
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
                all_files.sort(key=lambda p: p.relative_to(self.root_dir).as_posix().lower())
                
                total = len(all_files)
                # Calculate chunk size (ceiling division)
                chunk_size = math.ceil(total / 7)
                
                for i in range(7):
                    start = i * chunk_size
                    end = start + chunk_size
                    chunk_files = all_files[start:end]
                    
                    if not chunk_files:
                        break # No more files
                        
                    fname = f"0{i+1}_md_bundle.md"
                    title = f"MD Bundle {i+1} (Alphabetical)"
                    info = self.write_dump_file(fname, chunk_files, title)
                    if info: master_index_content.append(info)

                # Index as 8th file
                index_fname = "08_MASTER_INDEX.md"

            # ---------------------------------------------------------
            # MODE B: Standard Folder Split
            # ---------------------------------------------------------
            else:
                self.log(f"Mode: Splitting by top {self.top_n_count} folders.")
                
                root_files = []
                folder_groups: Dict[str, List[Path]] = {}

                for f in all_files:
                    rel = f.relative_to(self.root_dir)
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
        self.title("Smart Code Dumper v3")
        self.geometry("600x650")
        
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
        # NEW OPTIONS
        # ---------------------------------------------------
        opts_frame = tk.LabelFrame(self, text="Filters & Modes", padx=10, pady=10)
        opts_frame.pack(fill="x", **pad_opts)

        self.var_ignore_txt = tk.BooleanVar(value=False)
        self.var_ignore_md = tk.BooleanVar(value=False)
        self.var_only_md = tk.BooleanVar(value=False)

        # Checkboxes
        chk_txt = tk.Checkbutton(opts_frame, text="Ignore .txt files", variable=self.var_ignore_txt)
        chk_txt.grid(row=0, column=0, sticky="w", padx=10)

        self.chk_md = tk.Checkbutton(opts_frame, text="Ignore .md files", variable=self.var_ignore_md)
        self.chk_md.grid(row=0, column=1, sticky="w", padx=10)

        chk_only_md = tk.Checkbutton(opts_frame, text="Only select .md (Bundles: 7 pkgs + Index)", 
                                     variable=self.var_only_md, command=self.toggle_md_mode)
        chk_only_md.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=5)

        # Gitignore Notice
        tk.Label(opts_frame, 
                 text="Note: .gitignore rules & standard junk (node_modules, .git) are always excluded.",
                 fg="gray", font=("Arial", 8, "italic")
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

        # 2. Action
        self.btn_run = tk.Button(self, text="GENERATE DUMPS", bg="#dddddd", height=2, command=self.start_thread)
        self.btn_run.pack(fill="x", padx=20, pady=10)

        # 3. Log
        self.txt_log = scrolledtext.ScrolledText(self, height=15)
        self.txt_log.pack(fill="both", expand=True, padx=10, pady=10)

    def toggle_md_mode(self):
        """Ensures logic consistency when 'Only MD' is toggled."""
        if self.var_only_md.get():
            # If Only MD is ON, we cannot Ignore MD
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

        self.btn_run.config(state="disabled", text="Running...")
        self.txt_log.delete(1.0, tk.END)
        
        # Capture variables for thread safety
        ign_txt = self.var_ignore_txt.get()
        ign_md = self.var_ignore_md.get()
        only_md = self.var_only_md.get()

        t = threading.Thread(target=self.run_process, 
                             args=(Path(repo), Path(out), split_n, ign_txt, ign_md, only_md))
        t.start()

    def run_process(self, repo, out, split_n, ign_txt, ign_md, only_md):
        worker = DumpWorker(repo, out, split_n, ign_txt, ign_md, only_md, self.log)
        worker.run()
        self.btn_run.config(state="normal", text="GENERATE DUMPS")

if __name__ == "__main__":
    app = App()
    app.mainloop()