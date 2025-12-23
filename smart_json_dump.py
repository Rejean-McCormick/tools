import os
import fnmatch
import json
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
import threading
import subprocess
import sys
import queue

# --------------------------------------------------------------------
# 1. JSON Bundle Helpers
# --------------------------------------------------------------------

def create_json_volume_structure():
    return {
        "format": "wiki_dump_json",
        "format_version": 1.1,
        "generated_at": datetime.now().isoformat(timespec="minutes"),
        "title": "",
        "root_dir": "",
        "stats": {
            "file_count": 0,
            "total_size_bytes": 0,
            "total_size_mb": 0.0
        },
        "nav": {
            "home_file": None,
            "prev_file": None,
            "next_file": None,
            "prev_title": "",
            "next_title": ""
        },
        "file_index": [],
        "files": []
    }

def create_json_index_structure():
    return {
        "format": "wiki_dump_index_json",
        "format_version": 1,
        "generated_at": datetime.now().isoformat(timespec="minutes"),
        "repo_name": "",
        "root_dir": "",
        "volumes": [],
        "instructions": [
            "Open a volume JSON to view file contents.",
            "Use the 'file_index' at the top of each volume for a quick overview.",
            "Use the nav fields to jump between volumes."
        ]
    }

# --------------------------------------------------------------------
# 2. Core Logic (The Worker)
# --------------------------------------------------------------------

class DumpWorker:
    def __init__(self, root_dir: Path, output_dir: Path, max_output_files: int,
                 ignore_txt: bool, ignore_md: bool, only_md: bool,
                 create_index: bool, custom_excludes: List[Path],
                 exclusion_mode: str,
                 log_callback, overwrite_callback, stop_event):

        self.root_dir = root_dir.resolve()
        self.output_dir = output_dir.resolve()
        self.max_output_files = max(2, max_output_files)
        self.ignore_txt = ignore_txt
        self.ignore_md = ignore_md
        self.only_md = only_md
        self.create_index = create_index
        self.custom_excludes = [p.resolve() for p in custom_excludes]
        self.exclusion_mode = exclusion_mode

        self.log = log_callback
        self.ask_overwrite = overwrite_callback
        self.stop_event = stop_event  # <--- NEW STOP FLAG

        # Always-ignore dirs/extensions
        self.ALWAYS_IGNORE_DIRS = {
            ".git", ".svn", ".hg", ".idea", ".vscode", ".ipynb_checkpoints",
            "node_modules", "venv", ".venv", "env",
            "__pycache__", ".mypy_cache", ".pytest_cache",
            "dist", "build", "coverage", "target", "out",
            "abstract_wiki_architect.egg-info",
            "WEB-INF", "classes", "lib", "bin", "obj"
        }
        self.ALWAYS_IGNORE_EXT = {
            ".pyc", ".pyo", ".pyd", ".exe", ".dll", ".so", ".dylib", ".class", ".jar", ".war",
            ".bin", ".iso", ".img", ".log", ".sqlite", ".db", ".zip", ".gz", ".tar",
            ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".lock", ".pdf", ".mp4", ".mp3"
        }

        self.git_rules = self.load_all_gitignores()

    def check_stop(self):
        if self.stop_event.is_set():
            raise InterruptedError("Stopped by user.")

    # -----------------------------
    # Gitignore handling
    # -----------------------------

    def _parse_gitignore_line(self, raw: str) -> Optional[Dict[str, Any]]:
        line = raw.rstrip("\n").strip()
        if not line: return None
        if line.startswith(r"\#"): line = line[1:]
        if line.startswith(r"\!"): line = line[1:]
        if line.startswith("#"): return None

        neg = False
        if line.startswith("!"):
            neg = True
            line = line[1:].strip()
            if not line: return None

        dir_only = line.endswith("/")
        if dir_only: line = line.rstrip("/")

        anchored = line.startswith("/")
        if anchored: line = line.lstrip("/")

        if not line: return None

        return {
            "pattern": line,
            "neg": neg,
            "dir_only": dir_only,
            "anchored": anchored
        }

    def load_all_gitignores(self) -> list:
        rules = []
        self.log("-> Scanning for .gitignore files...")

        count = 0
        for root, dirnames, files in os.walk(self.root_dir, followlinks=True):
            self.check_stop() # Check stop
            current_dir = Path(root).resolve()

            # Filter directories
            safe_dirs = []
            for d in dirnames:
                if d in self.ALWAYS_IGNORE_DIRS: continue
                full_dir = (current_dir / d).resolve()
                if self.is_custom_excluded(full_dir) and self.exclusion_mode == "Fully Exclude":
                    continue
                safe_dirs.append(d)
            dirnames[:] = safe_dirs

            if ".gitignore" in files:
                git_path = (current_dir / ".gitignore").resolve()
                try:
                    with git_path.open("r", encoding="utf-8", errors="replace") as f:
                        for raw in f:
                            parsed = self._parse_gitignore_line(raw)
                            if not parsed: continue
                            parsed["base"] = current_dir
                            rules.append(parsed)
                        count += 1
                except Exception as e:
                    self.log(f"Warn: Could not read {git_path}: {e}")

        self.log(f"-> Loaded {count} .gitignore files ({len(rules)} rules).")
        return rules

    def _rule_applies(self, rule_base: Path, path: Path) -> bool:
        try:
            path.resolve().relative_to(rule_base.resolve())
            return True
        except Exception:
            return False

    def _match_rule(self, rule: Dict[str, Any], path: Path, is_dir: bool) -> bool:
        base: Path = rule["base"]
        try:
            rel_from_base = path.resolve().relative_to(base.resolve()).as_posix()
        except Exception:
            rel_from_base = path.name

        name = path.name
        pat = rule["pattern"]

        if rule["dir_only"]:
            dir_pat = pat
            if rel_from_base == dir_pat: return True
            if rel_from_base.startswith(dir_pat + "/"): return True
            return False

        if rule["anchored"] or ("/" in pat):
            return fnmatch.fnmatch(rel_from_base, pat)

        return fnmatch.fnmatch(name, pat)

    def match_ignore(self, path: Path, is_dir: bool) -> bool:
        ignored = False
        for rule in self.git_rules:
            if not self._rule_applies(rule["base"], path): continue
            if self._match_rule(rule, path, is_dir=is_dir):
                ignored = not rule["neg"]
        return ignored

    # -----------------------------
    # Helpers
    # -----------------------------

    def is_custom_excluded(self, path: Path) -> bool:
        path = path.resolve()
        for exc in self.custom_excludes:
            if path == exc or exc in path.parents:
                return True
        return False

    def get_file_size(self, f: Path) -> int:
        try:
            return f.stat().st_size
        except Exception:
            return 0

    def collect_files_in_folder(self, folder_path: Path, recursive: bool = True) -> List[Path]:
        valid_files: List[Path] = []
        self.log(f"DEBUG: Entering folder: {folder_path.name}") # VERBOSE

        if recursive:
            iterator = os.walk(folder_path, followlinks=True)
        else:
            try:
                iterator = [next(os.walk(folder_path, followlinks=True))]
            except StopIteration:
                return []

        for dirpath, dirnames, filenames in iterator:
            self.check_stop() # Check stop loop
            current_dir = Path(dirpath).resolve()

            # Filter folders
            safe_dirs = []
            for d in dirnames:
                full_dir_path = (current_dir / d).resolve()
                if d in self.ALWAYS_IGNORE_DIRS: 
                    self.log(f"DEBUG: Skipping ignored dir: {d}") # VERBOSE
                    continue
                
                if self.match_ignore(full_dir_path, is_dir=True): 
                    self.log(f"DEBUG: GitIgnore match dir: {d}") # VERBOSE
                    continue
                
                if self.is_custom_excluded(full_dir_path):
                    if self.exclusion_mode == "Fully Exclude":
                        self.log(f"DEBUG: Custom Exclude dir: {d}") # VERBOSE
                        continue

                safe_dirs.append(d)
            dirnames[:] = safe_dirs

            # Filter files
            for f in filenames:
                self.check_stop() # Check stop loop (very tight loop)
                fpath = (current_dir / f).resolve()
                ext = fpath.suffix.lower()

                self.log(f"DEBUG: Checking file: {f}") # VERBOSE

                if ext in self.ALWAYS_IGNORE_EXT: continue
                if self.match_ignore(fpath, is_dir=False): continue

                if self.is_custom_excluded(fpath):
                    if self.exclusion_mode == "Fully Exclude":
                        continue

                if self.only_md:
                    if ext != ".md": continue
                else:
                    if self.ignore_txt and ext == ".txt": continue
                    if self.ignore_md and ext == ".md": continue

                valid_files.append(fpath)

        return valid_files

    def write_volume_json(self, filename: str, files: List[Path], title: str, nav_context: dict) -> Optional[dict]:
        if not files: return None
        self.check_stop()

        out_path = self.output_dir / filename
        
        # Sort files
        try:
            files.sort(key=lambda p: p.relative_to(self.root_dir).as_posix().lower())
        except Exception:
            files.sort(key=lambda p: p.name.lower())

        volume = create_json_volume_structure()
        volume["title"] = title
        volume["root_dir"] = str(self.root_dir)
        
        volume["nav"] = nav_context
        total_size = 0

        self.log(f"-> Writing {filename} ({len(files)} files)...") # VERBOSE

        for f in files:
            self.check_stop()
            try:
                self.log(f"  Reading: {f.name}...") # VERBOSE: SEE EXACT FILE

                rel_path = f.relative_to(self.root_dir).as_posix()
                ext = f.suffix.lower()
                is_excluded_path = self.is_custom_excluded(f)
                
                size_bytes = 0
                line_count = 0
                content = ""
                kind = "source"

                if is_excluded_path:
                    if "Names" in self.exclusion_mode:
                        content = "[NAME_ONLY] Stats and content skipped."
                        kind = "excluded_name"
                    else:
                        size_bytes = self.get_file_size(f)
                        content = "[METADATA_ONLY] Content skipped."
                        kind = "excluded_meta"
                else:
                    size_bytes = self.get_file_size(f)
                    if size_bytes > 5_000_000: # 5MB limit
                        content = f"[SKIPPED] File too large ({size_bytes} bytes)"
                        kind = "oversized"
                    else:
                        content = f.read_text(encoding="utf-8", errors="replace")
                        line_count = len(content.splitlines())
                        kind = "markdown" if ext == ".md" else "source"
                
                total_size += size_bytes

                volume["file_index"].append({
                    "rel_path": rel_path,
                    "size_bytes": int(size_bytes),
                    "line_count": int(line_count),
                    "kind": kind
                })

                volume["files"].append({
                    "rel_path": rel_path,
                    "ext": ext,
                    "size_bytes": int(size_bytes),
                    "kind": kind,
                    "content": content
                })
            except Exception as e:
                self.log(f"  ERROR reading {f.name}: {e}") # VERBOSE ERROR
                error_name = getattr(f, "name", "unknown")
                volume["files"].append({
                    "rel_path": error_name,
                    "ext": "",
                    "size_bytes": 0,
                    "kind": "error",
                    "content": f"Error reading file: {e}"
                })

        size_mb = total_size / (1024 * 1024)
        volume["stats"]["file_count"] = len(files)
        volume["stats"]["total_size_bytes"] = int(total_size)
        volume["stats"]["total_size_mb"] = float(round(size_mb, 4))

        try:
            with out_path.open("w", encoding="utf-8") as out:
                json.dump(volume, out, indent=2, ensure_ascii=False)
            return {
                "filename": filename,
                "title": title,
                "size_mb": size_mb,
                "file_count": len(files),
                "short_title": nav_context.get("short_title", title)
            }
        except Exception as e:
            self.log(f"Error writing JSON file {filename}: {e}")
            return None

    def run(self):
        try:
            self.log(f"Scanning structure of: {self.root_dir}")

            repo_name = self.root_dir.name
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            base_name_pattern = f"{repo_name}_{ts}"

            mode_suffix = "_MD_ONLY" if self.only_md else ""
            run_folder_name = f"{base_name_pattern}_JsonDump{mode_suffix}"
            self.output_dir = (self.output_dir / run_folder_name).resolve()
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"Output Target: {self.output_dir}")

            try:
                _ = self.output_dir.relative_to(self.root_dir)
                if self.output_dir not in self.custom_excludes:
                    self.custom_excludes.append(self.output_dir)
            except Exception:
                pass

            # 1. Gather
            self.check_stop()
            root_files = self.collect_files_in_folder(self.root_dir, recursive=False)

            top_level_items = []
            for item in os.listdir(self.root_dir):
                full_path = (self.root_dir / item).resolve()
                if full_path.is_dir():
                    if item in self.ALWAYS_IGNORE_DIRS: continue
                    if self.match_ignore(full_path, is_dir=True): continue
                    if self.is_custom_excluded(full_path) and self.exclusion_mode == "Fully Exclude":
                        continue
                    top_level_items.append(full_path)

            analyzed_folders = []
            for folder in top_level_items:
                self.check_stop()
                f_files = self.collect_files_in_folder(folder, recursive=True)
                if f_files:
                    size = 0 if self.is_custom_excluded(folder) else sum(self.get_file_size(f) for f in f_files)
                    analyzed_folders.append({"name": folder.name, "files": f_files, "size": size})

            analyzed_folders.sort(key=lambda x: x["size"], reverse=True)

            available_slots = self.max_output_files
            planned_dumps = []

            index_filename = "NoteBookIndex.json"

            if root_files:
                available_slots -= 1
                fname = f"{base_name_pattern}_01_ROOT.json"
                planned_dumps.append({"filename": fname, "files": root_files, "title": "ROOT FILES", "short_title": "Root"})

            start_idx = len(planned_dumps) + 1

            # Planning logic
            if len(analyzed_folders) <= available_slots:
                for i, folder in enumerate(analyzed_folders):
                    idx = start_idx + i
                    fname = f"{base_name_pattern}_{idx:02d}_{folder['name']}.json"
                    planned_dumps.append({
                        "filename": fname,
                        "files": folder["files"],
                        "title": f"FOLDER: {folder['name']}",
                        "short_title": folder["name"]
                    })
            else:
                distinct_count = max(0, available_slots - 1)
                top_folders = analyzed_folders[:distinct_count]
                remaining_folders = analyzed_folders[distinct_count:]

                for i, folder in enumerate(top_folders):
                    idx = start_idx + i
                    fname = f"{base_name_pattern}_{idx:02d}_{folder['name']}.json"
                    planned_dumps.append({
                        "filename": fname,
                        "files": folder["files"],
                        "title": f"FOLDER: {folder['name']}",
                        "short_title": folder["name"]
                    })

                others_files = []
                for folder in remaining_folders:
                    others_files.extend(folder["files"])

                if others_files:
                    fname = f"{base_name_pattern}_99_OTHERS.json"
                    planned_dumps.append({
                        "filename": fname,
                        "files": others_files,
                        "title": "OTHERS (Misc Folders)",
                        "short_title": "Others"
                    })

            # 2. Generate
            self.log(f"Generating {len(planned_dumps)} content volumes...")
            generated_meta = []

            for i, dump in enumerate(planned_dumps):
                self.check_stop()
                prev_d = planned_dumps[i - 1] if i > 0 else None
                next_d = planned_dumps[i + 1] if i < len(planned_dumps) - 1 else None

                nav = {
                    "home_file": index_filename if self.create_index else None,
                    "prev_file": prev_d["filename"] if prev_d else None,
                    "next_file": next_d["filename"] if next_d else None,
                    "prev_title": prev_d["short_title"] if prev_d else "",
                    "next_title": next_d["short_title"] if next_d else "",
                    "short_title": dump["short_title"]
                }

                meta = self.write_volume_json(dump["filename"], dump["files"], dump["title"], nav)
                if meta:
                    generated_meta.append(meta)

            # 3. Index
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
                    index_data = create_json_index_structure()
                    index_data["repo_name"] = repo_name
                    index_data["root_dir"] = str(self.root_dir)

                    for meta in generated_meta:
                        index_data["volumes"].append({
                            "filename": meta["filename"],
                            "title": meta["title"],
                            "short_title": meta.get("short_title", meta["title"]),
                            "size_mb": float(round(meta["size_mb"], 4)),
                            "file_count": int(meta.get("file_count", 0))
                        })

                    with index_path.open("w", encoding="utf-8") as f:
                        json.dump(index_data, f, indent=2, ensure_ascii=False)

                    self.log(f"-> Created Master Index: {index_filename}")

            self.log(f"\nSUCCESS! Completed in:\n{self.output_dir}")

        except InterruptedError:
            self.log("\n!!! PROCESS STOPPED BY USER !!!")
        except Exception as e:
            self.log(f"ERROR: {e}")
            import traceback
            traceback.print_exc()

# --------------------------------------------------------------------
# 3. GUI Application
# --------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Smart Wiki Dumper v12 (Verbose + Stop)")
        self.geometry("600x900") 

        self.last_output_dir: Optional[str] = None
        self.log_queue = queue.Queue()
        self.stop_event = threading.Event() # <--- STOP FLAG

        pad_opts = {"padx": 10, "pady": 5}

        # --- Config ---
        lbl_frame = tk.LabelFrame(self, text="Configuration", padx=10, pady=10)
        lbl_frame.pack(fill="x", **pad_opts)

        tk.Label(lbl_frame, text="Repository Root:").grid(row=0, column=0, sticky="w")
        self.entry_repo = tk.Entry(lbl_frame, width=50)
        self.entry_repo.grid(row=0, column=1, padx=5)
        self.entry_repo.insert(0, os.getcwd())
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

        # Exclude Qty
        tk.Label(self.frame_excludes, text="Quantity to exclude:").grid(row=0, column=0, sticky="w")
        self.spin_exclude_qty = tk.Spinbox(
            self.frame_excludes, from_=0, to=5, width=5, command=self.update_exclusion_widgets
        )
        self.spin_exclude_qty.delete(0, "end")
        self.spin_exclude_qty.insert(0, 0)
        self.spin_exclude_qty.grid(row=0, column=1, sticky="w", padx=5)
        
        # --- NEW DROPDOWN ---
        tk.Label(self.frame_excludes, text="Exclusion Mode:").grid(row=1, column=0, sticky="w", pady=5)
        self.var_exclude_mode = tk.StringVar(value="Fully Exclude")
        self.combo_exclude = ttk.Combobox(
            self.frame_excludes, 
            textvariable=self.var_exclude_mode, 
            state="readonly",
            width=30
        )
        self.combo_exclude['values'] = (
            "Fully Exclude", 
            "Index w/ Metadata (Skip Content)", 
            "List Folders & Files Names"
        )
        self.combo_exclude.grid(row=1, column=1, columnspan=2, sticky="w", padx=5)

        self.frame_dynamic_excludes = tk.Frame(self.frame_excludes)
        self.frame_dynamic_excludes.grid(row=2, column=0, columnspan=3, sticky="we", pady=5)
        self.exclusion_entries = []

        # --- Filters & Index Options ---
        opts_frame = tk.LabelFrame(self, text="Filters & Options", padx=10, pady=10)
        opts_frame.pack(fill="x", **pad_opts)

        self.var_ignore_txt = tk.BooleanVar(value=False)
        self.var_ignore_md = tk.BooleanVar(value=False)
        self.var_only_md = tk.BooleanVar(value=False)
        self.var_create_index = tk.BooleanVar(value=True)

        tk.Checkbutton(opts_frame, text="Ignore .txt files", variable=self.var_ignore_txt).grid(
            row=0, column=0, sticky="w", padx=10
        )
        self.chk_md = tk.Checkbutton(opts_frame, text="Ignore .md files", variable=self.var_ignore_md)
        self.chk_md.grid(row=0, column=1, sticky="w", padx=10)

        tk.Checkbutton(
            opts_frame, text="Scan ONLY .md files", variable=self.var_only_md, command=self.toggle_md_mode
        ).grid(row=1, column=0, sticky="w", padx=10, pady=5)

        tk.Frame(opts_frame, height=1, bg="grey").grid(row=2, column=0, columnspan=2, sticky="we", pady=5)
        tk.Checkbutton(
            opts_frame,
            text="Create Master Index (NoteBookIndex.json)",
            variable=self.var_create_index,
            font=("Arial", 9, "bold"),
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=10)

        # --- Actions ---
        actions = tk.Frame(self)
        actions.pack(fill="x", padx=20, pady=10)

        self.btn_run = tk.Button(
            actions,
            text="GENERATE JSON DUMP & INDEX",
            bg="#4CAF50",
            fg="white",
            font=("Arial", 11, "bold"),
            height=2,
            command=self.start_thread,
        )
        self.btn_run.pack(fill="x")

        # --- STOP BUTTON ---
        self.btn_stop = tk.Button(
            actions,
            text="STOP OPERATION",
            bg="#f44336",
            fg="white",
            font=("Arial", 10, "bold"),
            height=1,
            state="disabled",
            command=self.stop_process
        )
        self.btn_stop.pack(fill="x", pady=(5,0))

        self.btn_open_dest = tk.Button(
            actions,
            text="OPEN DESTINATION FOLDER",
            height=2,
            state="disabled",
            command=self.open_destination_folder,
        )
        self.btn_open_dest.pack(fill="x", pady=(8, 0))

        # --- Log ---
        self.txt_log = scrolledtext.ScrolledText(self, height=12)
        self.txt_log.pack(fill="both", expand=True, padx=10, pady=10)

        # START LOG QUEUE CHECKER
        self.check_log_queue()

    def check_log_queue(self):
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                self.txt_log.insert(tk.END, msg + "\n")
                self.txt_log.see(tk.END)
            except queue.Empty:
                pass
        self.after(100, self.check_log_queue)

    def open_destination_folder(self):
        if not self.last_output_dir or not os.path.isdir(self.last_output_dir):
            messagebox.showerror("Error", "No destination folder available yet.")
            return

        folder = self.last_output_dir

        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open folder:\n{e}")

    def update_exclusion_widgets(self):
        for widget in self.frame_dynamic_excludes.winfo_children():
            widget.destroy()
        self.exclusion_entries.clear()

        try:
            count = int(self.spin_exclude_qty.get())
        except Exception:
            count = 0

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
            if not self.entry_out.get():
                self.entry_out.insert(0, str(Path(d).parent))

    def browse_out(self):
        d = filedialog.askdirectory()
        if d:
            self.entry_out.delete(0, tk.END)
            self.entry_out.insert(0, d)

    def log_thread_safe(self, msg):
        self.log_queue.put(msg)

    def ask_overwrite_thread_safe(self, filename):
        event = threading.Event()
        result_container = {"value": False}
        def show_dialog():
            result_container["value"] = messagebox.askyesno(
                "File Exists", 
                f"The file '{filename}' already exists.\n\nOverwrite it?"
            )
            event.set()
        self.after(0, show_dialog)
        event.wait()
        return result_container["value"]

    def stop_process(self):
        self.stop_event.set()
        self.log_thread_safe("\n... Stopping requested ...")
        self.btn_stop.config(state="disabled", text="Stopping...")

    def start_thread(self):
        repo = self.entry_repo.get()
        out = self.entry_out.get()

        if not repo or not os.path.isdir(repo):
            messagebox.showerror("Error", "Please select a valid repository folder.")
            return
        if not out or not os.path.isdir(out):
            messagebox.showerror("Error", "Please select a valid output folder.")
            return

        try:
            max_files = int(self.spin_split.get())
        except Exception:
            max_files = 10

        custom_excludes_paths = [Path(e.get().strip()) for e in self.exclusion_entries if e.get().strip()]

        self.last_output_dir = None
        self.btn_open_dest.config(state="disabled")
        self.btn_run.config(state="disabled", text="Running...")
        self.btn_stop.config(state="normal", text="STOP OPERATION") # Enable Stop
        self.stop_event.clear() # Reset stop flag
        self.txt_log.delete(1.0, tk.END)

        t = threading.Thread(
            target=self.run_process,
            args=(
                Path(repo),
                Path(out),
                max_files,
                self.var_ignore_txt.get(),
                self.var_ignore_md.get(),
                self.var_only_md.get(),
                self.var_create_index.get(),
                custom_excludes_paths,
                self.var_exclude_mode.get(),
            ),
            daemon=True
        )
        t.start()

    def run_process(self, repo, out, max_files, ign_txt, ign_md, only_md, create_index, custom_excludes, exclude_mode):
        worker = DumpWorker(
            repo, out, max_files, ign_txt, ign_md, only_md, create_index, custom_excludes, 
            exclude_mode,
            self.log_thread_safe,
            self.ask_overwrite_thread_safe,
            self.stop_event # Pass stop event
        )
        worker.run()

        # Update UI safely from the main thread
        out_dir_str = str(worker.output_dir)

        def _finish():
            self.last_output_dir = out_dir_str
            self.btn_open_dest.config(state="normal")
            self.btn_run.config(state="normal", text="GENERATE JSON DUMP & INDEX")
            self.btn_stop.config(state="disabled", text="STOP OPERATION")
            
            # Only show success if not stopped
            if not self.stop_event.is_set():
                messagebox.showinfo("Done", f"JSON dump generated successfully!\n\nFolder:\n{out_dir_str}")

        self.after(0, _finish)

if __name__ == "__main__":
    app = App()
    app.mainloop()