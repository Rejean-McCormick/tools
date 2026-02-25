# gui.py
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Optional

from .constants import DEFAULT_CREATE_GROUPED_BUNDLES, DEFAULT_TXT_MODE
from .worker import DumpWorker


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Smart Wiki Dumper")
        self.geometry("600x1020")

        self.last_output_dir: Optional[str] = None
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.stop_event = threading.Event()

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

        tk.Label(lbl_frame, text="Max Output Files:").grid(row=2, column=0, sticky="w")
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

        tk.Label(self.frame_excludes, text="Exclusion Mode:").grid(row=1, column=0, sticky="w", pady=5)
        self.var_exclude_mode = tk.StringVar(value="Fully Exclude")
        self.combo_exclude = ttk.Combobox(
            self.frame_excludes,
            textvariable=self.var_exclude_mode,
            state="readonly",
            width=30,
        )
        self.combo_exclude["values"] = (
            "Fully Exclude",
            "Index w/ Metadata (Skip Content)",
            "List Folders & Files Names",
        )
        self.combo_exclude.grid(row=1, column=1, columnspan=2, sticky="w", padx=5)

        self.frame_dynamic_excludes = tk.Frame(self.frame_excludes)
        self.frame_dynamic_excludes.grid(row=2, column=0, columnspan=3, sticky="we", pady=5)
        self.exclusion_entries: list[tk.Entry] = []

        # --- Filters & Options ---
        opts_frame = tk.LabelFrame(self, text="Filters & Options", padx=10, pady=10)
        opts_frame.pack(fill="x", **pad_opts)

        self.var_ignore_txt = tk.BooleanVar(value=False)
        self.var_ignore_md = tk.BooleanVar(value=False)
        self.var_create_index = tk.BooleanVar(value=True)

        tk.Checkbutton(opts_frame, text="Ignore .txt files", variable=self.var_ignore_txt).grid(
            row=0, column=0, sticky="w", padx=10
        )
        tk.Checkbutton(opts_frame, text="Ignore .md files", variable=self.var_ignore_md).grid(
            row=0, column=1, sticky="w", padx=10
        )

        tk.Frame(opts_frame, height=1, bg="grey").grid(row=1, column=0, columnspan=2, sticky="we", pady=6)

        tk.Checkbutton(
            opts_frame,
            text="Create Master Index (Index.*)",
            variable=self.var_create_index,
            font=("Arial", 9, "bold"),
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=10)

        # --- Output Format (txt default) ---
        format_frame = tk.LabelFrame(self, text="Output Format", padx=10, pady=10)
        format_frame.pack(fill="x", **pad_opts)

        tk.Label(format_frame, text="Format:").grid(row=0, column=0, sticky="w")
        self.var_output_format = tk.StringVar(value="text (structured .txt) [default]")
        self.combo_output_format = ttk.Combobox(
            format_frame,
            textvariable=self.var_output_format,
            state="readonly",
            width=35,
            values=(
                "text (structured .txt) [default]",
                "xml (.xml)",
            ),
        )
        self.combo_output_format.grid(row=0, column=1, sticky="w", padx=5)

        # --- .smartignore options (NEW) ---
        smart_frame = tk.LabelFrame(self, text=".smartignore", padx=10, pady=10)
        smart_frame.pack(fill="x", **pad_opts)

        self.var_use_smartignore_exclude = tk.BooleanVar(value=False)
        self.var_smartignore_index = tk.BooleanVar(value=False)

        tk.Checkbutton(
            smart_frame,
            text="Exclude what is listed in .smartignore",
            variable=self.var_use_smartignore_exclude,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10)

        tk.Checkbutton(
            smart_frame,
            text="Create index of paths matched by .smartignore (SmartignorePathsIndex.txt)",
            variable=self.var_smartignore_index,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 0))

        # --- ChatGPT helpers ---
        chatgpt_frame = tk.LabelFrame(self, text="ChatGPT Upload Helpers", padx=10, pady=10)
        chatgpt_frame.pack(fill="x", **pad_opts)

        tk.Label(chatgpt_frame, text="XML txt_mode:").grid(row=0, column=0, sticky="w")
        self.var_txt_mode = tk.StringVar(value=DEFAULT_TXT_MODE)
        self.combo_txt_mode = ttk.Combobox(
            chatgpt_frame,
            textvariable=self.var_txt_mode,
            state="readonly",
            width=30,
            values=(
                "none (only .xml)",
                "copy (.xml + .xml.txt)",
                "only (only .xml.txt)",
            ),
        )
        self.combo_txt_mode.grid(row=0, column=1, sticky="w", padx=5)

        self.var_create_bundles = tk.BooleanVar(value=DEFAULT_CREATE_GROUPED_BUNDLES)
        tk.Checkbutton(
            chatgpt_frame,
            text="Create grouped bundles + manifest (recommended when upload limit is tight)",
            variable=self.var_create_bundles,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 0))

        self.combo_output_format.bind("<<ComboboxSelected>>", lambda _e: self._sync_controls())
        self._sync_controls()

        # --- Actions ---
        actions = tk.Frame(self)
        actions.pack(fill="x", padx=20, pady=10)

        self.btn_run = tk.Button(
            actions,
            text="GENERATE DUMP",
            bg="#4CAF50",
            fg="white",
            font=("Arial", 11, "bold"),
            height=2,
            command=self.start_thread,
        )
        self.btn_run.pack(fill="x")

        self.btn_stop = tk.Button(
            actions,
            text="STOP OPERATION",
            bg="#f44336",
            fg="white",
            font=("Arial", 10, "bold"),
            height=1,
            state="disabled",
            command=self.stop_process,
        )
        self.btn_stop.pack(fill="x", pady=(5, 0))

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

        self.check_log_queue()

    def _resolve_output_format(self) -> str:
        raw = (self.var_output_format.get() or "").lower().strip()
        if raw.startswith("xml"):
            return "xml"
        return "text"

    def _sync_controls(self):
        fmt = self._resolve_output_format()
        if fmt == "xml":
            self.combo_txt_mode.config(state="readonly")
        else:
            self.combo_txt_mode.config(state="disabled")

    def report_callback_exception(self, exc, val, tb):
        import traceback

        tb_text = "".join(traceback.format_exception(exc, val, tb))
        try:
            messagebox.showerror("Unhandled UI exception", tb_text)
        except Exception:
            print(tb_text, file=sys.stderr)

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

    def browse_exclusion(self, e: tk.Entry):
        d = filedialog.askdirectory()
        if d:
            e.delete(0, tk.END)
            e.insert(0, d)

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

    def log_thread_safe(self, msg: str):
        self.log_queue.put(msg)

    def ask_overwrite_thread_safe(self, filename: str) -> bool:
        event = threading.Event()
        result_container = {"value": False}

        def show_dialog():
            result_container["value"] = messagebox.askyesno(
                "File Exists",
                f"The file '{filename}' already exists.\n\nOverwrite it?",
            )
            event.set()

        self.after(0, show_dialog)
        event.wait()
        return bool(result_container["value"])

    def stop_process(self):
        self.stop_event.set()
        self.log_thread_safe("\n... Stopping requested ...")
        self.btn_stop.config(state="disabled", text="Stopping...")

    def _resolve_txt_mode(self) -> str:
        raw = (self.var_txt_mode.get() or "").lower().strip()
        if raw.startswith("none"):
            return "none"
        if raw.startswith("only"):
            return "only"
        return "copy"

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

        output_format = self._resolve_output_format()
        txt_mode = self._resolve_txt_mode()
        create_bundles = bool(self.var_create_bundles.get())

        use_smartignore_exclude = bool(self.var_use_smartignore_exclude.get())
        smartignore_index = bool(self.var_smartignore_index.get())

        self.last_output_dir = None
        self.btn_open_dest.config(state="disabled")
        self.btn_run.config(state="disabled", text="Running...")
        self.btn_stop.config(state="normal", text="STOP OPERATION")
        self.stop_event.clear()
        self.txt_log.delete(1.0, tk.END)

        t = threading.Thread(
            target=self.run_process,
            args=(
                Path(repo),
                Path(out),
                max_files,
                self.var_ignore_txt.get(),
                self.var_ignore_md.get(),
                self.var_create_index.get(),
                custom_excludes_paths,
                self.var_exclude_mode.get(),
                output_format,
                txt_mode,
                create_bundles,
                use_smartignore_exclude,
                smartignore_index,
            ),
            daemon=True,
        )
        t.start()

    def run_process(
        self,
        repo: Path,
        out: Path,
        max_files: int,
        ign_txt: bool,
        ign_md: bool,
        create_index: bool,
        custom_excludes: list[Path],
        exclude_mode: str,
        output_format: str,
        txt_mode: str,
        create_bundles: bool,
        use_smartignore_exclude: bool,
        smartignore_index: bool,
    ):
        worker = DumpWorker(
            repo,
            out,
            max_files,
            ign_txt,
            ign_md,
            create_index,
            custom_excludes,
            exclude_mode,
            self.log_thread_safe,
            self.ask_overwrite_thread_safe,
            self.stop_event,
            output_format=output_format,
            txt_mode=txt_mode,
            create_grouped_bundles=create_bundles,
            use_smartignore_exclude=use_smartignore_exclude,
            create_smartignore_paths_index=smartignore_index,
        )
        worker.run()

        out_dir_str = str(worker.output_dir)
        err_tb = worker.last_exception_traceback

        def _finish():
            self.last_output_dir = out_dir_str
            self.btn_open_dest.config(state="normal")
            self.btn_run.config(state="normal", text="GENERATE DUMP")
            self.btn_stop.config(state="disabled", text="STOP OPERATION")

            if self.stop_event.is_set():
                return

            if err_tb:
                messagebox.showerror("Error", f"Dump failed with an exception:\n\n{err_tb}")
            else:
                messagebox.showinfo("Done", f"Dump generated successfully!\n\nFolder:\n{out_dir_str}")

        self.after(0, _finish)