import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import os
import traceback
import re

DEBUG = True


def log(msg):
    if DEBUG:
        print(msg, flush=True)


def build_ws_insensitive_pattern(text: str) -> str:
    """
    Turn user text into a regex that:
    - Escapes all non-whitespace characters literally.
    - Collapses any run of whitespace (spaces/tabs/newlines) into '\\s+'.
    This makes matching tolerant to spaces/tab/newline differences.
    """
    parts = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        if ch.isspace():
            # Collapse any run of whitespace into \s+
            while i < n and text[i].isspace():
                i += 1
            parts.append(r"\s+")
        else:
            # Collect a run of non-whitespace and escape it
            j = i
            while j < n and not text[j].isspace():
                j += 1
            parts.append(re.escape(text[i:j]))
            i = j

    return "".join(parts)


def find_consecutive_blocks_ws_insensitive(content: str, block1: str, block3: str):
    """
    Search 'content' for Block1 immediately followed by Block3,
    using whitespace-insensitive matching.

    Returns:
        dict with keys: start, end, orig_block1, between_ws, orig_block3
        or None if not found.
    """
    log("Building whitespace-insensitive pattern for Block1 + Block3")

    pat1 = build_ws_insensitive_pattern(block1)
    pat3 = build_ws_insensitive_pattern(block3)

    if not pat1 or not pat3:
        log("Empty pattern generated (one of the blocks is effectively empty)")
        return None

    # Capture:
    #  group 1: the actual text in the file matching Block1
    #  group 2: the whitespace between them (if any)
    #  group 3: the actual text in the file matching Block3
    combined_pattern = f"({pat1})(\\s*)({pat3})"

    truncated = combined_pattern[:200]
    if len(combined_pattern) > 200:
        truncated += "..."
    log(f"Combined regex (truncated): {truncated}")

    try:
        regex = re.compile(combined_pattern, re.DOTALL)
    except re.error as e:
        log(f"Regex compile error: {e}")
        return None

    m = regex.search(content)
    if not m:
        log("No match found for Block1 + Block3 with whitespace-insensitive search")
        return None

    result = {
        "start": m.start(1),
        "end": m.end(3),
        "orig_block1": m.group(1),
        "between_ws": m.group(2),
        "orig_block3": m.group(3),
    }
    log(f"Match found at indexes [{result['start']}, {result['end']})")
    return result


class CodeBlockInserterApp:
    def __init__(self, root):
        log("Initializing CodeBlockInserterApp")
        self.root = root
        self.root.title("Code Block Inserter (Whitespace-tolerant, Debug)")
        self.create_widgets()
        log("GUI initialized")

    def create_widgets(self):
        # File selection frame
        file_frame = tk.Frame(self.root)
        file_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(file_frame, text="File path:").pack(side="left")

        self.file_path_var = tk.StringVar()
        self.file_entry = tk.Entry(file_frame, textvariable=self.file_path_var, width=60)
        self.file_entry.pack(side="left", padx=5)

        browse_btn = tk.Button(file_frame, text="Browse...", command=self.browse_file)
        browse_btn.pack(side="left")

        # Text areas frame
        text_frame = tk.Frame(self.root)
        text_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Block 1 (before)
        block1_frame = tk.LabelFrame(text_frame, text="Block 1 (before)")
        block1_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.block1_text = scrolledtext.ScrolledText(block1_frame, wrap="none", height=7)
        self.block1_text.pack(fill="both", expand=True)

        # Block 2 (to insert)
        block2_frame = tk.LabelFrame(text_frame, text="Block 2 (to insert)")
        block2_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.block2_text = scrolledtext.ScrolledText(block2_frame, wrap="none", height=7)
        self.block2_text.pack(fill="both", expand=True)

        # Block 3 (after)
        block3_frame = tk.LabelFrame(text_frame, text="Block 3 (after)")
        block3_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.block3_text = scrolledtext.ScrolledText(block3_frame, wrap="none", height=7)
        self.block3_text.pack(fill="both", expand=True)

        # Buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=5)

        validate_btn = tk.Button(btn_frame, text="Validate", command=self.validate_blocks)
        validate_btn.pack(side="left", padx=5)

        insert_btn = tk.Button(btn_frame, text="Insert and Save", command=self.insert_and_save)
        insert_btn.pack(side="left", padx=5)

        # Status label
        self.status_var = tk.StringVar()
        self.status_label = tk.Label(self.root, textvariable=self.status_var, anchor="w", fg="blue")
        self.status_label.pack(fill="x", padx=10, pady=5)

    def browse_file(self):
        log("Browse button clicked")
        # All files first so it's the default view
        path = filedialog.askopenfilename(
            title="Select code file",
            filetypes=[
                ("All files", "*.*"),
                ("TypeScript files", "*.ts"),
                ("JavaScript files", "*.js"),
            ],
        )
        if path:
            log(f"File selected: {path}")
            self.file_path_var.set(path)
            self.status_var.set(f"Selected file: {path}")
        else:
            log("No file selected")

    def read_file_content(self):
        path = self.file_path_var.get().strip()
        log(f"read_file_content called, path='{path}'")

        if not path:
            log("Error: No file selected")
            messagebox.showerror("Error", "No file selected.")
            return None, None

        if not os.path.isfile(path):
            log(f"Error: File not found: {path}")
            messagebox.showerror("Error", f"File not found:\n{path}")
            return None, None

        try:
            log(f"Reading file (utf-8): {path}")
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            log(f"File read OK (len={len(content)})")
        except UnicodeDecodeError:
            log("UnicodeDecodeError with utf-8, retrying latin-1")
            try:
                with open(path, "r", encoding="latin-1") as f:
                    content = f.read()
                log(f"File read OK with latin-1 (len={len(content)})")
            except Exception as e:
                log(f"Error reading file with latin-1: {e}")
                traceback.print_exc()
                messagebox.showerror("Error", f"Failed to read file:\n{e}")
                return None, None
        except Exception as e:
            log(f"Error reading file: {e}")
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to read file:\n{e}")
            return None, None

        return path, content

    def get_blocks(self):
        block1 = self.block1_text.get("1.0", "end-1c")
        block2 = self.block2_text.get("1.0", "end-1c")
        block3 = self.block3_text.get("1.0", "end-1c")

        log(
            f"Block lengths (raw): B1={len(block1)}, B2={len(block2)}, B3={len(block3)}; "
            f"B1_stripped={len(block1.strip())}, B3_stripped={len(block3.strip())}"
        )
        return block1, block2, block3

    def validate_blocks(self):
        log("Validate button clicked")
        path, content = self.read_file_content()
        if content is None:
            log("validate_blocks aborted: no content")
            return

        block1, _, block3 = self.get_blocks()

        # Require some non-whitespace content in both blocks
        if not block1.strip() or not block3.strip():
            log("Validation error: Block 1 or Block 3 effectively empty")
            messagebox.showerror("Error", "Block 1 and Block 3 must not be empty (not just whitespace).")
            return

        match_info = find_consecutive_blocks_ws_insensitive(content, block1, block3)

        if match_info:
            log("Validation success: whitespace-insensitive consecutive match found")
            self.status_var.set(
                "Validation OK: Block 1 and Block 3 were found consecutively (whitespace-insensitive)."
            )
            messagebox.showinfo(
                "Validation",
                "Success: The two blocks were found one after the other (ignoring whitespace differences)."
            )
        else:
            log("Validation failed: no whitespace-insensitive consecutive match")
            self.status_var.set("Validation FAILED: The blocks were not found consecutively.")
            messagebox.showwarning(
                "Validation",
                "The file does not contain Block 1 immediately followed by Block 3 "
                "(even when ignoring spaces/tabs/newlines)."
            )

    def insert_and_save(self):
        log("Insert button clicked")
        path, content = self.read_file_content()
        if content is None:
            log("insert_and_save aborted: no content")
            return

        block1, block2, block3 = self.get_blocks()

        if not block1.strip() or not block3.strip():
            log("Insert error: Block 1 or Block 3 effectively empty")
            messagebox.showerror("Error", "Block 1 and Block 3 must not be empty (not just whitespace).")
            return

        match_info = find_consecutive_blocks_ws_insensitive(content, block1, block3)

        if not match_info:
            log("Insert failed: no whitespace-insensitive consecutive match for Block1+Block3")
            messagebox.showerror(
                "Error",
                "Cannot insert: the file does not contain Block 1 immediately followed by Block 3 "
                "(even when ignoring spaces/tabs/newlines)."
            )
            self.status_var.set("Insert failed: consecutive Block 1 + Block 3 not found.")
            return

        start = match_info["start"]
        end = match_info["end"]
        orig_block1 = match_info["orig_block1"]
        orig_block3 = match_info["orig_block3"]

        log(f"Preparing new content with insertion between indexes [{start}, {end})")
        log(
            f"Original matched lengths: orig_block1={len(orig_block1)}, "
            f"orig_block3={len(orig_block3)}, block2_to_insert={len(block2)}"
        )

        # Detect file newline style for the extra line after Block2
        newline = "\r\n" if "\r\n" in content else "\n"
        # Ensure exactly one newline after the inserted block
        block2_with_newline = block2.rstrip("\r\n") + newline

        # Keep Block1 and Block3 exactly as in the file; insert Block2 (with one trailing newline) between them
        new_combined = orig_block1 + block2_with_newline + orig_block3
        new_content = content[:start] + new_combined + content[end:]

        # Backup original file
        backup_path = path + ".bak"
        try:
            if not os.path.exists(backup_path):
                log(f"Creating backup file: {backup_path}")
                with open(backup_path, "w", encoding="utf-8") as backup_file:
                    backup_file.write(content)
                log("Backup created successfully")
            else:
                log("Backup file already exists; not overwriting")
        except Exception as e:
            log(f"Warning: could not create backup file: {e}")
            traceback.print_exc()
            messagebox.showwarning(
                "Warning",
                f"Could not create backup file:\n{backup_path}\n\nError: {e}\n"
                "Continuing without backup."
            )

        # Write new content
        try:
            log(f"Writing modified content back to original file: {path}")
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            log("File write successful")
        except Exception as e:
            log(f"Error writing modified file: {e}")
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to write modified file:\n{e}")
            self.status_var.set("Insert failed: error while saving file.")
            return

        self.status_var.set(f"Insert successful. File overwritten: {path}")
        messagebox.showinfo("Insert", "Insert successful. File has been updated.")
        log("Insert operation completed successfully")


def main():
    log("Starting application (main)")
    try:
        root = tk.Tk()
        app = CodeBlockInserterApp(root)
        log("Entering Tk mainloop")
        root.mainloop()
        log("Tk mainloop exited normally")
    except Exception as e:
        log(f"FATAL error in main: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
