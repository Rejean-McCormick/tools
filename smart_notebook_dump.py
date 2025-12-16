import os
import sys
import fnmatch
import math
import json
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
import threading
import re

# --------------------------------------------------------------------
# 1. Notebook Generation Helpers
# --------------------------------------------------------------------

def create_notebook_structure():
    return {
        "cells": [],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "codemirror_mode": {"name": "ipython", "version": 3},
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.8.5"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 4
    }

def create_markdown_cell(content):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": content.splitlines(keepends=True)
    }

def create_code_cell(content):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": content.splitlines(keepends=True)
    }

# --------------------------------------------------------------------
# 2. Core Logic (The Worker) - IMPROVED
# --------------------------------------------------------------------

class DumpWorker:
    def __init__(self, root_dir: Path, output_dir: Path, max_output_files: int, 
                 ignore_txt: bool, ignore_md: bool, only_md: bool, 
                 create_index: bool, custom_excludes: List[Path], 
                 log_callback, overwrite_callback):
        
        self.root_dir = root_dir.resolve()
        self.output_dir = output_dir.resolve()
        self.max_output_files = max(2, max_output_files) 
        self.ignore_txt = ignore_txt
        self.ignore_md = ignore_md
        self.only_md = only_md
        self.create_index = create_index
        self.custom_excludes = [p.resolve() for p in custom_excludes]
        
        self.log = log_callback
        self.ask_overwrite = overwrite_callback
        
        # [FIX] Added 'WEB-INF', 'classes', 'lib' to prevent 600MB Java blobs
        self.ALWAYS_IGNORE_DIRS = {
            ".git", ".svn", ".hg", ".idea", ".vscode", ".ipynb_checkpoints",
            "node_modules", "venv", ".venv", "env", 
            "__pycache__", ".mypy_cache", ".pytest_cache",
            "dist", "build", "coverage", "target", "out",
            "abstract_wiki_architect.egg-info",
            "WEB-INF", "classes", "lib" 
        }
        self.ALWAYS_IGNORE_EXT = {
            ".pyc", ".pyo", ".pyd", ".exe", ".dll", ".so", ".dylib", ".class", ".jar", ".war",
            ".bin", ".iso", ".img", ".log", ".sqlite", ".db", ".zip", ".gz",
            ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".lock", ".pdf"
        }
        
        self.git_patterns = self.load_all_gitignores()

    def load_all_gitignores(self) -> list:
        """Scans the entire repo for .gitignore files and aggregates patterns."""
        patterns = []
        self.log("-> Scanning for .gitignore files...")
        
        count = 0
        # Walk the tree to find all .gitignore files (Nested support)
        for root, _, files in os.walk(self.root_dir):
            if ".gitignore" in files:
                git_path = Path(root) / ".gitignore"
                try:
                    with git_path.open("r", encoding="utf-8") as f:
                        # We try to make patterns roughly relative to match anywhere
                        # This is a heuristic: it merges all ignores into a global exclude list
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#"): continue
                            patterns.append(line)
                            # Handle directory-specific ignores (e.g. "foo/") by also adding "foo"
                            if line.endswith("/"):
                                patterns.append(line.rstrip("/"))
                    count += 1
                except Exception as e:
                    self.log(f"Warn: Could not read {git_path}: {e}")

        self.log(f"-> Loaded {count} .gitignore files ({len(patterns)} rules).")
        return patterns

    def match_ignore(self, path: Path, is_dir: bool) -> bool:
        """
        Checks if a path should be ignored based on git patterns.
        [FIX] Now checks RELATIVE PATHS, not just filenames.
        """
        try:
            # Get path relative to project root
            rel_path = path.relative_to(self.root_dir).as_posix()
        except ValueError:
            # Should not happen given how we walk, but safety first
            rel_path = path.name

        name = path.name

        for pat in self.git_patterns:
            # 1. Standard wildcard match on the filename (e.g. *.log)
            if fnmatch.fnmatch(name, pat):
                return True
            
            # 2. Path-specific match (e.g. webapp/WEB-INF/)
            # We normalize patterns to handle matching folders anywhere
            if fnmatch.fnmatch(rel_path, pat):
                return True
            
            # 3. Directory prefix match (e.g. node_modules/*)
            if rel_path.startswith(pat + "/") or rel_path == pat:
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
        valid_files = []
        if recursive:
            iterator = os.walk(folder_path, followlinks=True)
        else:
            try:
                iterator = [next(os.walk(folder_path, followlinks=True))]
            except StopIteration:
                return []

        for dirpath, dirnames, filenames in iterator:
            current_dir = Path(dirpath).resolve()
            
            # [FIX] Filter Directories in place to prevent recursing into ignored dirs
            safe_dirs = []
            for d in dirnames:
                full_dir_path = current_dir / d
                
                # Check 1: Hardcoded ignores
                if d in self.ALWAYS_IGNORE_DIRS: 
                    continue
                
                # Check 2: Gitignore patterns (pass Full Path object + is_dir=True)
                if self.match_ignore(full_dir_path, is_dir=True): 
                    continue
                
                # Check 3: Custom exclusions
                if self.is_custom_excluded(full_dir_path): 
                    continue
                    
                safe_dirs.append(d)
            
            # Apply filter so os.walk doesn't enter them
            dirnames[:] = safe_dirs
            
            # Filter Files
            for f in filenames:
                fpath = current_dir / f
                ext = fpath.suffix.lower()
                
                if ext in self.ALWAYS_IGNORE_EXT: continue
                
                # Check Gitignore (pass Full Path object + is_dir=False)
                if self.match_ignore(fpath, is_dir=False): continue
                
                if self.is_custom_excluded(fpath): continue

                if self.only_md:
                    if ext != ".md": continue
                else:
                    if self.ignore_txt and ext == ".txt": continue
                    if self.ignore_md and ext == ".md": continue
                
                valid_files.append(fpath)
        return valid_files

    def write_notebook(self, filename: str, files: List[Path], title: str, nav_context: dict) -> dict:
        if not files: return None
        out_path = self.output_dir / filename
        total_size = sum(self.get_file_size(f) for f in files)
        size_mb = total_size / (1024*1024)

        try:
            files.sort(key=lambda p: p.relative_to(self.root_dir).as_posix().lower())
        except:
            files.sort(key=lambda p: p.name.lower())

        notebook_data = create_notebook_structure()

        # 1. Navigation
        nav_parts = []
        if nav_context.get('home_file'):
            nav_parts.append(f"[🏠 **Home**]({nav_context['home_file']})")
        
        if nav_context.get('prev_file'):
            nav_parts.append(f"[⏪ **Prev** ({nav_context['prev_title']})]({nav_context['prev_file']})")
        
        if nav_context.get('next_file'):
            nav_parts.append(f"[**Next** ({nav_context['next_title']}) ⏩]({nav_context['next_file']})")
            
        if nav_parts:
            nav_bar_md = " &nbsp; | &nbsp; ".join(nav_parts)
            notebook_data["cells"].append(create_markdown_cell(f"### {nav_bar_md}\n---"))

        # 2. Title
        header_text = (
            f"# {title}\n"
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"**Contains:** {len(files)} files | **Total Size:** {size_mb:.2f} MB"
        )
        notebook_data["cells"].append(create_markdown_cell(header_text))

        # 3. Content
        current_folder_context = None
        for f in files:
            try:
                rel_path = f.relative_to(self.root_dir).as_posix()
                folder_group = os.path.dirname(rel_path)
                if folder_group != current_folder_context:
                    notebook_data["cells"].append(create_markdown_cell(f"## 📂 `{folder_group}/`"))
                    current_folder_context = folder_group

                notebook_data["cells"].append(create_markdown_cell(f"#### 📄 `{rel_path}`"))
                content = f.read_text(encoding="utf-8", errors="replace")
                
                if f.suffix.lower() == '.md':
                    notebook_data["cells"].append(create_markdown_cell(content))
                else:
                    notebook_data["cells"].append(create_code_cell(content))
            except Exception as e:
                notebook_data["cells"].append(create_markdown_cell(f"> **Error reading {f.name}:** {e}"))

        try:
            with out_path.open("w", encoding="utf-8") as out:
                json.dump(notebook_data, out, indent=2)
            self.log(f"-> Created: {filename}")
            return {
                "filename": filename,
                "title": title,
                "size_mb": size_mb,
                "short_title": nav_context.get('short_title', title)
            }
        except Exception as e:
            self.log(f"Error writing {filename}: {e}")
            return None

    def run(self):
        try:
            self.log(f"Scanning structure of: {self.root_dir}")
            
            repo_name = self.root_dir.name
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            base_name_pattern = f"{repo_name}_{ts}"
            
            # Create Output Subfolder
            mode_suffix = "_MD_ONLY" if self.only_md else ""
            run_folder_name = f"{base_name_pattern}_WikiDump{mode_suffix}"
            self.output_dir = self.output_dir / run_folder_name
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"Output Target: {self.output_dir}")

            # ----------------------------------------
            # STEP 1: GATHER & PLAN
            # ----------------------------------------
            root_files = self.collect_files_in_folder(self.root_dir, recursive=False)
            top_level_items = []
            
            # [FIX] Manually check ignoring for Top Level items too
            for item in os.listdir(self.root_dir):
                full_path = self.root_dir / item
                if full_path.is_dir():
                    if item in self.ALWAYS_IGNORE_DIRS: continue
                    if self.match_ignore(full_path, is_dir=True): continue
                    if self.is_custom_excluded(full_path): continue
                    top_level_items.append(full_path)

            analyzed_folders = []
            for folder in top_level_items:
                f_files = self.collect_files_in_folder(folder, recursive=True)
                if f_files:
                    size = sum(self.get_file_size(f) for f in f_files)
                    analyzed_folders.append({'name': folder.name, 'files': f_files, 'size': size})
            
            analyzed_folders.sort(key=lambda x: x['size'], reverse=True)

            available_slots = self.max_output_files 
            planned_dumps = []
            
            index_filename = "NoteBookIndex.ipynb"

            if root_files:
                available_slots -= 1
                fname = f"{base_name_pattern}_01_ROOT.ipynb"
                planned_dumps.append({"filename": fname, "files": root_files, "title": "ROOT FILES", "short_title": "Root"})

            start_idx = len(planned_dumps) + 1
            if len(analyzed_folders) <= available_slots:
                for i, folder in enumerate(analyzed_folders):
                    idx = start_idx + i
                    fname = f"{base_name_pattern}_{idx:02d}_{folder['name']}.ipynb"
                    planned_dumps.append({"filename": fname, "files": folder['files'], "title": f"FOLDER: {folder['name']}", "short_title": folder['name']})
            else:
                distinct_count = max(0, available_slots - 1)
                top_folders = analyzed_folders[:distinct_count]
                remaining_folders = analyzed_folders[distinct_count:]
                for i, folder in enumerate(top_folders):
                    idx = start_idx + i
                    fname = f"{base_name_pattern}_{idx:02d}_{folder['name']}.ipynb"
                    planned_dumps.append({"filename": fname, "files": folder['files'], "title": f"FOLDER: {folder['name']}", "short_title": folder['name']})
                
                others_files = []
                for folder in remaining_folders: others_files.extend(folder['files'])
                if others_files:
                    fname = f"{base_name_pattern}_99_OTHERS.ipynb"
                    planned_dumps.append({"filename": fname, "files": others_files, "title": "OTHERS (Misc Folders)", "short_title": "Others"})

            # ----------------------------------------
            # STEP 2: GENERATE NOTEBOOKS
            # ----------------------------------------
            self.log(f"Generating {len(planned_dumps)} content notebooks...")
            generated_meta = []
            
            for i, dump in enumerate(planned_dumps):
                prev_d = planned_dumps[i-1] if i > 0 else None
                next_d = planned_dumps[i+1] if i < len(planned_dumps) - 1 else None
                nav = {
                    'home_file': index_filename if self.create_index else None,
                    'prev_file': prev_d['filename'] if prev_d else None,
                    'next_file': next_d['filename'] if next_d else None,
                    'prev_title': prev_d['short_title'] if prev_d else "",
                    'next_title': next_d['short_title'] if next_d else "",
                    'short_title': dump['short_title']
                }
                meta = self.write_notebook(dump['filename'], dump['files'], dump['title'], nav)
                if meta:
                    generated_meta.append(meta)

            # ----------------------------------------
            # STEP 3: GENERATE INDEX
            # ----------------------------------------
            if self.create_index:
                index_path = self.output_dir / index_filename
                
                should_write = True
                if index_path.exists():
                    self.log(f"Index file {index_filename} already exists.")
                    if not self.ask_overwrite(index_filename):
                        should_write = False
                        self.log("Skipping index generation (User cancelled overwrite).")
                    else:
                        self.log("Overwriting existing index file.")

                if should_write:
                    index_data = create_notebook_structure()
                    
                    index_data["cells"].append(create_markdown_cell(f"# 🏠 {repo_name} - Index\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"))

                    toc_md = "## 📚 Table of Contents\n\n| Volume | Description | Size |\n|---|---|---|\n"
                    for meta in generated_meta:
                        link = f"[{meta['filename']}]({meta['filename']})"
                        toc_md += f"| **{link}** | {meta['title']} | {meta['size_mb']:.2f} MB |\n"
                    
                    index_data["cells"].append(create_markdown_cell(toc_md))
                    index_data["cells"].append(create_markdown_cell("### 💡 Instructions\n- Click links above to browse code.\n- Use top navigation in files to return here."))

                    with index_path.open("w", encoding="utf-8") as f:
                        json.dump(index_data, f, indent=2)

                    self.log(f"-> Created Master Index: {index_filename}")

            self.log(f"\nSUCCESS! Completed in:\n{self.output_dir}")
            messagebox.showinfo("Done", f"Wiki generated successfully!\n\nFolder:\n{self.output_dir}")

        except Exception as e:
            self.log(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", str(e))

# --------------------------------------------------------------------
# 3. GUI Application
# --------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Smart Wiki Dumper v9.1 (Fixed)")
        self.geometry("600x800")
        
        pad_opts = {'padx': 10, 'pady': 5}
        
        # --- Config ---
        lbl_frame = tk.LabelFrame(self, text="Configuration", padx=10, pady=10)
        lbl_frame.pack(fill="x", **pad_opts)

        tk.Label(lbl_frame, text="Repository Root:").grid(row=0, column=0, sticky="w")
        self.entry_repo = tk.Entry(lbl_frame, width=50)
        self.entry_repo.grid(row=0, column=1, padx=5)
        self.entry_repo.insert(0, os.getcwd()) # Default to current dir
        tk.Button(lbl_frame, text="Browse...", command=self.browse_repo).grid(row=0, column=2)

        tk.Label(lbl_frame, text="Output Folder:").grid(row=1, column=0, sticky="w")
        self.entry_out = tk.Entry(lbl_frame, width=50)
        self.entry_out.grid(row=1, column=1, padx=5)
        tk.Button(lbl_frame, text="Browse...", command=self.browse_out).grid(row=1, column=2)

        tk.Label(lbl_frame, text="Max Content Volumes:").grid(row=2, column=0, sticky="w")
        self.spin_split = tk.Spinbox(lbl_frame, from_=2, to=50, width=5)
        self.spin_split.delete(0, "end")
        self.spin_split.insert(0, 10)
        self.spin_split.grid(row=2, column=1, sticky="w", padx=5)
        
        # --- Exclusions ---
        self.frame_excludes = tk.LabelFrame(self, text="Custom Path Exclusions", padx=10, pady=10)
        self.frame_excludes.pack(fill="x", **pad_opts)

        tk.Label(self.frame_excludes, text="Quantity to exclude:").grid(row=0, column=0, sticky="w")
        self.spin_exclude_qty = tk.Spinbox(self.frame_excludes, from_=0, to=5, width=5, command=self.update_exclusion_widgets)
        self.spin_exclude_qty.delete(0, "end")
        self.spin_exclude_qty.insert(0, 0)
        self.spin_exclude_qty.grid(row=0, column=1, sticky="w", padx=5)

        self.frame_dynamic_excludes = tk.Frame(self.frame_excludes)
        self.frame_dynamic_excludes.grid(row=1, column=0, columnspan=3, sticky="we", pady=5)
        self.exclusion_entries = []

        # --- Filters & Index Options ---
        opts_frame = tk.LabelFrame(self, text="Filters & Options", padx=10, pady=10)
        opts_frame.pack(fill="x", **pad_opts)
        
        self.var_ignore_txt = tk.BooleanVar(value=False)
        self.var_ignore_md = tk.BooleanVar(value=False)
        self.var_only_md = tk.BooleanVar(value=False)
        self.var_create_index = tk.BooleanVar(value=True) # Default Checked

        # Row 0
        tk.Checkbutton(opts_frame, text="Ignore .txt files", variable=self.var_ignore_txt).grid(row=0, column=0, sticky="w", padx=10)
        self.chk_md = tk.Checkbutton(opts_frame, text="Ignore .md files", variable=self.var_ignore_md)
        self.chk_md.grid(row=0, column=1, sticky="w", padx=10)
        
        # Row 1
        tk.Checkbutton(opts_frame, text="Scan ONLY .md files", variable=self.var_only_md, command=self.toggle_md_mode).grid(row=1, column=0, sticky="w", padx=10, pady=5)
        
        # Row 2 (Index Option)
        tk.Frame(opts_frame, height=1, bg="grey").grid(row=2, column=0, columnspan=2, sticky="we", pady=5)
        tk.Checkbutton(opts_frame, text="Create Master Index (NoteBookIndex.ipynb)", variable=self.var_create_index, font=("Arial", 9, "bold")).grid(row=3, column=0, columnspan=2, sticky="w", padx=10)

        # --- Actions ---
        self.btn_run = tk.Button(self, text="GENERATE DUMP & INDEX", bg="#4CAF50", fg="white", font=("Arial", 11, "bold"), height=2, command=self.start_thread)
        self.btn_run.pack(fill="x", padx=20, pady=15)

        # --- Log ---
        self.txt_log = scrolledtext.ScrolledText(self, height=12)
        self.txt_log.pack(fill="both", expand=True, padx=10, pady=10)

    # --- Methods ---
    def update_exclusion_widgets(self):
        for widget in self.frame_dynamic_excludes.winfo_children(): widget.destroy()
        self.exclusion_entries.clear()
        try: count = int(self.spin_exclude_qty.get())
        except: count = 0
        for i in range(count):
            row = tk.Frame(self.frame_dynamic_excludes)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"Path {i+1}:").pack(side="left")
            e = tk.Entry(row)
            e.pack(side="left", fill="x", expand=True, padx=5)
            self.exclusion_entries.append(e)
            tk.Button(row, text="Browse", command=lambda x=e: self.browse_exclusion(x)).pack(side="right")

    def browse_exclusion(self, e):
        d = filedialog.askdirectory()
        if d: 
            e.delete(0, tk.END)
            e.insert(0, d)

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
            if not self.entry_out.get(): self.entry_out.insert(0, str(Path(d).parent))

    def browse_out(self):
        d = filedialog.askdirectory()
        if d:
            self.entry_out.delete(0, tk.END)
            self.entry_out.insert(0, d)

    def log(self, msg):
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)

    def safe_ask_overwrite(self, filename):
        return messagebox.askyesno("File Exists", f"The file '{filename}' already exists.\n\nOverwrite it?")

    def start_thread(self):
        repo = self.entry_repo.get()
        out = self.entry_out.get()
        
        if not repo or not os.path.isdir(repo):
            messagebox.showerror("Error", "Please select a valid repository folder.")
            return
        if not out or not os.path.isdir(out):
            messagebox.showerror("Error", "Please select a valid output folder.")
            return

        try: max_files = int(self.spin_split.get())
        except: max_files = 10

        custom_excludes_paths = [Path(e.get().strip()) for e in self.exclusion_entries if e.get().strip()]
        
        self.btn_run.config(state="disabled", text="Running...")
        self.txt_log.delete(1.0, tk.END)
        
        t = threading.Thread(target=self.run_process, 
                             args=(Path(repo), Path(out), max_files, 
                                   self.var_ignore_txt.get(), self.var_ignore_md.get(), self.var_only_md.get(), 
                                   self.var_create_index.get(), custom_excludes_paths))
        t.start()

    def run_process(self, repo, out, max_files, ign_txt, ign_md, only_md, create_index, custom_excludes):
        worker = DumpWorker(repo, out, max_files, ign_txt, ign_md, only_md, create_index, custom_excludes, 
                            self.log, self.safe_ask_overwrite)
        worker.run()
        self.btn_run.config(state="normal", text="GENERATE DUMP & INDEX")

if __name__ == "__main__":
    app = App()
    app.mainloop()