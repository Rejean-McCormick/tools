import os
import subprocess
import tkinter as tk
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText

# Path to Notepad++
NOTEPADPP_PATH = r"C:\Program Files\Notepad++\notepad++.exe"


def open_files():
    base_path = base_entry.get().strip()
    if base_path:
        base_path = os.path.normpath(base_path)

    # Get all lines from the multiline box
    raw_text = paths_text.get("1.0", tk.END)
    raw_lines = raw_text.splitlines()

    # Clean paths: remove empty lines, whitespace, and surrounding quotes
    cleaned_paths = [line.strip().strip('"') for line in raw_lines if line.strip()]

    if not cleaned_paths:
        messagebox.showwarning("No paths", "Please enter at least one file path.")
        return

    # If base path is given but not a directory, ask whether to continue anyway
    if base_path and not os.path.isdir(base_path):
        answer = messagebox.askyesno(
            "Base path not found",
            f"Base path does not exist:\n{base_path}\n\nContinue anyway?"
        )
        if not answer:
            return

    files_to_open = []
    missing_files = []

    for p in cleaned_paths:
        # If path is absolute, use as-is; otherwise join with base path (if any)
        if os.path.isabs(p) or not base_path:
            full_path = os.path.normpath(p)
        else:
            full_path = os.path.normpath(os.path.join(base_path, p))

        if os.path.isfile(full_path):
            files_to_open.append(full_path)
        else:
            missing_files.append(full_path)

    if not files_to_open:
        messagebox.showerror("No valid files", "None of the given paths point to existing files.")
        return

    # Check Notepad++ path
    if not os.path.isfile(NOTEPADPP_PATH):
        messagebox.showerror(
            "Notepad++ not found",
            f"Notepad++ not found at:\n{NOTEPADPP_PATH}\n\n"
            "Update NOTEPADPP_PATH in the script if it is installed elsewhere."
        )
        return

    try:
        # Open all files in Notepad++ as tabs, in order
        subprocess.Popen([NOTEPADPP_PATH] + files_to_open)
    except Exception as e:
        messagebox.showerror("Error launching Notepad++", str(e))
        return

    if missing_files:
        messagebox.showwarning(
            "Some files missing",
            "These files could not be found:\n\n" + "\n".join(missing_files)
        )


def main():
    global base_entry, paths_text

    root = tk.Tk()
    root.title("Open Files in Notepad++")

    # Base path
    base_label = tk.Label(root, text="Base path (folder):")
    base_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)

    base_entry = tk.Entry(root, width=80)
    base_entry.grid(row=0, column=1, columnspan=2, sticky="we", padx=5, pady=5)

    # Paths area
    paths_label = tk.Label(root, text="File paths (one per line):")
    paths_label.grid(row=1, column=0, sticky="nw", padx=5, pady=5)

    paths_text = ScrolledText(root, width=80, height=15)
    paths_text.grid(row=1, column=1, columnspan=2, sticky="nsew", padx=5, pady=5)

    # Buttons
    open_button = tk.Button(root, text="Open in Notepad++", command=open_files)
    open_button.grid(row=2, column=1, sticky="e", padx=5, pady=10)

    quit_button = tk.Button(root, text="Quit", command=root.destroy)
    quit_button.grid(row=2, column=2, sticky="w", padx=5, pady=10)

    # Make the window resize nicely
    root.columnconfigure(1, weight=1)
    root.rowconfigure(1, weight=1)

    root.mainloop()


if __name__ == "__main__":
    main()
