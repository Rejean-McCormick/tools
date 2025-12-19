import os
import fnmatch
import json
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
import threading
import subprocess
import sys

# --------------------------------------------------------------------
# 1. JSON Bundle Helpers
# --------------------------------------------------------------------

def create_json_volume_structure():
    return {
        "format": "wiki_dump_json",
        "format_version": 1,
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
        "files": []  # list of {rel_path, ext, size_bytes, kind, content}
    }

def create_json_index_structure():
    return {
        "format": "wiki_dump_index_json",
        "format_version": 1,
        "generated_at": datetime.now().isoformat(timespec="minutes"),
        "repo_name": "",
        "root_dir": "",
        "volumes": [],  # list of {filename, title, short_title, size_mb, file_count}
        "instructions": [
            "Open a volume JSON to view file contents.",
            "Use the nav fields in each volume to jump between files (home/prev/next)."
        ]
    }

# --------------------------------------------------------------------
# 2. Core Logic (The Worker) - JSON OUTPUT
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

        # Always-ignore dirs/extensions
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

        # Gitignore rules:
        # list of dicts:
        # {base: Path, pattern: str, neg: bool, dir_only: bool, anchored: bool}
        self.git_rules = self.load_all_gitignores()

    # -----------------------------
    # Gitignore handling (fixed)
    # -----------------------------

    def _parse_gitignore_line(self, raw: str) -> Optional[Dict[str, Any]]:
        line = raw.rstrip("\n").strip()
        if not line:
            return None

        # Allow escaping leading '#' or '!'
        if line.startswith(r"\#"):
            line = line[1:]
        if line.startswith(r"\!"):
            line = line[1:]

        if line.startswith("#"):
            return None

        neg = False
        if line.startswith("!"):
            neg = True
            line = line[1:].strip()
            if not line:
                return None

        dir_only = line.endswith("/")
        if dir_only:
            line = line.rstrip("/")

        anchored = line.startswith("/")
        if anchored:
            line = line.lstrip("/")

        if not line:
            return None

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
            current_dir = Path(root).resolve()

            # Prune recursion into known junk/vendor dirs and user-excluded paths.
            safe_dirs = []
            for d in dirnames:
                if d in self.ALWAYS_IGNORE_DIRS:
                    continue
                full_dir = (current_dir / d).resolve()
                if self.is_custom_excluded(full_dir):
                    continue
                safe_dirs.append(d)
            dirnames[:] = safe_dirs

            if ".gitignore" in files:
                git_path = (current_dir / ".gitignore").resolve()
                try:
                    with git_path.open("r", encoding="utf-8", errors="replace") as f:
                        for raw in f:
                            parsed = self._parse_gitignore_line(raw)
                            if not parsed:
                                continue
                            parsed["base"] = current_dir
                            rules.append(parsed)
                    count += 1
                except Exception as e:
                    self.log(f"Warn: Could not read {git_path}: {e}")

        self.log(f"-> Loaded {count} .gitignore files ({len(rules)} rules).")
        return rules

    def _rule_applies(self, rule_base: Path, path: Path) -> bool:
        # A gitignore file only applies to files under its directory.
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

        # If rule is dir-only: ignore the directory itself AND everything under it.
        if rule["dir_only"]:
            dir_pat = pat
            if rel_from_base == dir_pat:
                return True
            if rel_from_base.startswith(dir_pat + "/"):
                return True
            return False

        # Anchored or contains '/' => match against relative path from rule base
        if rule["anchored"] or ("/" in pat):
            return fnmatch.fnmatch(rel_from_base, pat)

        # Otherwise match basename anywhere under base
        return fnmatch.fnmatch(name, pat)

    def match_ignore(self, path: Path, is_dir: bool) -> bool:
        # Implements "last matching rule wins" with '!' negation.
        ignored = False
        for rule in self.git_rules:
            if not self._rule_applies(rule["base"], path):
                continue
            if self._match_rule(rule, path, is_dir=is_dir):
                ignored = not rule["neg"]
        return ignored

    # -----------------------------
    # Existing helpers
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

        if recursive:
            iterator = os.walk(folder_path, followlinks=True)
        else:
            try:
                iterator = [next(os.walk(folder_path, followlinks=True))]
            except StopIteration:
                return []

        for dirpath, dirnames, filenames in iterator:
            current_dir = Path(dirpath).resolve()

            # Filter directories in-place to prevent recursion
            safe_dirs = []
            for d in dirnames:
                full_dir_path = (current_dir / d).resolve()

                if d in self.ALWAYS_IGNORE_DIRS:
                    continue
                if self.match_ignore(full_dir_path, is_dir=True):
                    continue
                if self.is_custom_excluded(full_dir_path):
                    continue

                safe_dirs.append(d)

            dirnames[:] = safe_dirs

            # Filter files
            for f in filenames:
                fpath = (current_dir / f).resolve()
                ext = fpath.suffix.lower()

                if ext in self.ALWAYS_IGNORE_EXT:
                    continue
                if self.match_ignore(fpath, is_dir=False):
                    continue
                if self.is_custom_excluded(fpath):
                    continue

                if self.only_md:
                    if ext != ".md":
                        continue
                else:
                    if self.ignore_txt and ext == ".txt":
                        continue
                    if self.ignore_md and ext == ".md":
                        continue

                valid_files.append(fpath)

        return valid_files

    def write_volume_json(self, filename: str, files: List[Path], title: str, nav_context: dict) -> Optional[dict]:
        if not files:
            return None

        out_path = self.output_dir / filename

        total_size = sum(self.get_file_size(f) for f in files)
        size_mb = total_size / (1024 * 1024)

        try:
            files.sort(key=lambda p: p.relative_to(self.root_dir).as_posix().lower())
        except Exception:
            files.sort(key=lambda p: p.name.lower())

        volume = create_json_volume_structure()
        volume["title"] = title
        volume["root_dir"] = str(self.root_dir)

        volume["stats"]["file_count"] = len(files)
        volume["stats"]["total_size_bytes"] = int(total_size)
        volume["stats"]["total_size_mb"] = float(round(size_mb, 4))

        volume["nav"] = {
            "home_file": nav_context.get("home_file"),
            "prev_file": nav_context.get("prev_file"),
            "next_file": nav_context.get("next_file"),
            "prev_title": nav_context.get("prev_title", ""),
            "next_title": nav_context.get("next_title", "")
        }

        for f in files:
            try:
                rel_path = f.relative_to(self.root_dir).as_posix()
                ext = f.suffix.lower()
                size_bytes = self.get_file_size(f)

                content = f.read_text(encoding="utf-8", errors="replace")

                kind = "markdown" if ext == ".md" else "source"

                volume["files"].append({
                    "rel_path": rel_path,
                    "ext": ext,
                    "size_bytes": int(size_bytes),
                    "kind": kind,
                    "content": content
                })
            except Exception as e:
                volume["files"].append({
                    "rel_path": getattr(f, "name", "unknown"),
                    "ext": f.suffix.lower() if hasattr(f, "suffix") else "",
                    "size_bytes": 0,
                    "kind": "error",
                    "content": f"Error reading file: {e}"
                })

        try:
            with out_path.open("w", encoding="utf-8") as out:
                json.dump(volume, out, indent=2, ensure_ascii=False)
            self.log(f"-> Created: {filename}")
            return {
                "filename": filename,
                "title": title,
                "size_mb": size_mb,
                "file_count": len(files),
                "short_title": nav_context.get("short_title", title)
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
            run_folder_name = f"{base_name_pattern}_JsonDump{mode_suffix}"
            self.output_dir = (self.output_dir / run_folder_name).resolve()
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"Output Target: {self.output_dir}")

            # Auto-exclude output folder if it is inside the repo (prevents self-inclusion)
            try:
                _ = self.output_dir.relative_to(self.root_dir)
                if self.output_dir not in self.custom_excludes:
                    self.custom_excludes.append(self.output_dir)
            except Exception:
                pass

            # ----------------------------------------
            # STEP 1: GATHER & PLAN
            # ----------------------------------------
            root_files = self.collect_files_in_folder(self.root_dir, recursive=False)

            top_level_items = []
            for item in os.listdir(self.root_dir):
                full_path = (self.root_dir / item).resolve()
                if full_path.is_dir():
                    if item in self.ALWAYS_IGNORE_DIRS:
                        continue
                    if self.match_ignore(full_path, is_dir=True):
                        continue
                    if self.is_custom_excluded(full_path):
                        continue
                    top_level_items.append(full_path)

            analyzed_folders = []
            for folder in top_level_items:
                f_files = self.collect_files_in_folder(folder, recursive=True)
                if f_files:
                    size = sum(self.get_file_size(f) for f in f_files)
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

            # ----------------------------------------
            # STEP 2: GENERATE VOLUMES
            # ----------------------------------------
            self.log(f"Generating {len(planned_dumps)} content volumes...")
            generated_meta = []

            for i, dump in enumerate(planned_dumps):
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
            messagebox.showinfo("Done", f"JSON dump generated successfully!\n\nFolder:\n{self.output_dir}")

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
        self.title("Smart Wiki Dumper v10 (JSON)")
        self.geometry("600x840")

        self.last_output_dir: Optional[str] = None

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

        tk.Label(self.frame_excludes, text="Quantity to exclude:").grid(row=0, column=0, sticky="w")
        self.spin_exclude_qty = tk.Spinbox(
            self.frame_excludes, from_=0, to=5, width=5, command=self.update_exclusion_widgets
        )
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

        try:
            max_files = int(self.spin_split.get())
        except Exception:
            max_files = 10

        custom_excludes_paths = [Path(e.get().strip()) for e in self.exclusion_entries if e.get().strip()]

        self.last_output_dir = None
        self.btn_open_dest.config(state="disabled")
        self.btn_run.config(state="disabled", text="Running...")
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
            ),
        )
        t.start()

    def run_process(self, repo, out, max_files, ign_txt, ign_md, only_md, create_index, custom_excludes):
        worker = DumpWorker(
            repo, out, max_files, ign_txt, ign_md, only_md, create_index, custom_excludes, self.log, self.safe_ask_overwrite
        )
        worker.run()

        # Update UI safely from the main thread
        out_dir_str = str(worker.output_dir)

        def _finish():
            self.last_output_dir = out_dir_str
            self.btn_open_dest.config(state="normal")
            self.btn_run.config(state="normal", text="GENERATE JSON DUMP & INDEX")

        self.after(0, _finish)

if __name__ == "__main__":
    app = App()
    app.mainloop()
