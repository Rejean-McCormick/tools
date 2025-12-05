import os
import subprocess
import tkinter as tk
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText

# Path to Notepad++
NOTEPADPP_PATH = r"C:\Program Files\Notepad++\notepad++.exe"


def resolve_full_path(base_path, path_str):
    """
    Build a full path from base_path and a user-entered path.

    - Drive-letter paths (C:\..., D:\...) and UNC paths (\\server\share\...)
      are treated as absolute.
    - On Windows, paths that start with a single slash or backslash are treated
      as *relative* to base_path, to be forgiving of extra/missing separators.
    - On non-Windows systems, paths that start with '/' are treated as absolute.
    """
    if path_str is None:
        return None

    path_str = path_str.strip().strip('"')
    if not path_str:
        return None

    # Normalize separators
    path_str = path_str.replace("/", os.sep).replace("\\", os.sep)

    drive, _ = os.path.splitdrive(path_str)
    is_unc = path_str.startswith(os.sep * 2)

    # Truly absolute path:
    if drive or is_unc or (os.name != "nt" and path_str.startswith(os.sep)):
        return os.path.normpath(path_str)

    # Relative or "almost absolute" -> join with base if provided
    if base_path:
        # Avoid dropping base_path if user started with a separator
        relative = path_str.lstrip("/\\")
        return os.path.normpath(os.path.join(base_path, relative))

    return os.path.normpath(path_str)


def open_files():
    base_path = base_entry.get().strip().strip('"')
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

    # Keep all resolved paths in original order
    ordered_paths = []
    missing_files = []

    for p in cleaned_paths:
        full_path = resolve_full_path(base_path, p)
        if not full_path:
            continue

        ordered_paths.append(full_path)

        if not os.path.isfile(full_path):
            missing_files.append(full_path)

    creation_errors = []

    if missing_files:
        create = messagebox.askyesno(
            "Create missing files?",
            "These files do not exist:\n\n"
            + "\n".join(missing_files)
            + "\n\nCreate them as empty files?"
        )
        if create:
            for path in missing_files:
                try:
                    dir_name = os.path.dirname(path)
                    if dir_name and not os.path.isdir(dir_name):
                        os.makedirs(dir_name, exist_ok=True)

                    # Create empty file (or leave existing content untouched)
                    if not os.path.exists(path):
                        with open(path, "w", encoding="utf-8"):
                            pass
                except Exception as e:
                    creation_errors.append(f"{path} -> {e}")

            if creation_errors:
                messagebox.showerror(
                    "Error creating some files",
                    "Some files could not be created:\n\n" + "\n".join(creation_errors)
                )
        else:
            # User chose not to create missing files, just inform which are missing
            messagebox.showwarning(
                "Some files missing",
                "These files could not be found and were not created:\n\n"
                + "\n".join(missing_files)
            )

    # Build final list in the original order, only including files that now exist
    files_to_open = [p for p in ordered_paths if os.path.isfile(p)]

    if not files_to_open:
        messagebox.showerror(
            "No files to open",
            "No existing or newly created files to open."
        )
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
        # Open all files in Notepad++ as tabs, in the original list order
        subprocess.Popen([NOTEPADPP_PATH] + files_to_open)
    except Exception as e:
        messagebox.showerror("Error launching Notepad++", str(e))
        return


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
