import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
import os
import subprocess  # <--- NEW IMPORT

def browse_base_path():
    """Opens a directory selector and sets the base path entry."""
    folder_selected = filedialog.askdirectory()
    if folder_selected:
        base_path_var.set(folder_selected)

def get_file_list():
    """Helper to parse paths from input and resolve against base_path."""
    base_dir = base_path_var.get().strip()
    raw_input = input_area.get("1.0", tk.END)
    
    # Split lines and clean quotes
    paths = [line.strip().strip('"').strip("'") for line in raw_input.splitlines() if line.strip()]
    
    resolved_files = []
    
    for path_entry in paths:
        if base_dir:
            full_path = os.path.join(base_dir, path_entry)
        else:
            full_path = path_entry
            
        resolved_files.append(full_path)
        
    return resolved_files

def open_in_npp():
    """Opens all valid files from the input list in Notepad++."""
    files_to_open = get_file_list()
    
    if not files_to_open:
        messagebox.showwarning("Input Error", "Please enter at least one file path.")
        return

    npp_path = r"C:\Program Files\Notepad++\notepad++.exe"
    
    if not os.path.exists(npp_path):
        messagebox.showerror("Error", f"Notepad++ not found at:\n{npp_path}")
        return

    # Filter for files that actually exist before trying to open them
    existing_files = [f for f in files_to_open if os.path.isfile(f)]
    
    if not existing_files:
        status_label.config(text="No valid files found to open.", fg="red")
        return

    try:
        # We pass the executable path + the list of files as arguments
        # This opens all files in one Notepad++ instance
        cmd = [npp_path] + existing_files
        subprocess.Popen(cmd)
        status_label.config(text=f"Opened {len(existing_files)} files in Notepad++", fg="green")
    except Exception as e:
        messagebox.showerror("Execution Error", str(e))

def process_paths():
    """Reads paths from the input area and dumps content to the log window."""
    paths = get_file_list() # Re-using the helper function
    
    if not paths:
        messagebox.showwarning("Input Error", "Please enter at least one file path.")
        return

    # Prepare Output Window
    log_window.config(state=tk.NORMAL)
    log_window.delete(1.0, tk.END) # Clear previous output
    
    success_count = 0
    
    for full_path in paths:
        filename = os.path.basename(full_path)
        
        # Header for visual separation
        header = f"\n{'='*10} FILE: {filename} {'='*10}\n"
        log_window.insert(tk.END, header, "header_tag")
        log_window.insert(tk.END, f"Path: {full_path}\n\n", "path_tag")
        
        try:
            if os.path.isdir(full_path):
                 log_window.insert(tk.END, "[Skipped: This is a folder, not a file]\n", "error_tag")
            else:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    log_window.insert(tk.END, content + "\n")
                    success_count += 1
        except FileNotFoundError:
            log_window.insert(tk.END, "[Error: File not found]\n", "error_tag")
        except PermissionError:
            log_window.insert(tk.END, "[Error: Permission denied]\n", "error_tag")
        except Exception as e:
            log_window.insert(tk.END, f"[Error: {str(e)}]\n", "error_tag")
            
        log_window.insert(tk.END, "-"*40 + "\n") # Divider

    log_window.config(state=tk.DISABLED)
    status_label.config(text=f"Processed {len(paths)} paths. Loaded {success_count} successfully.", fg="blue")

def copy_to_clipboard():
    """Copies output log to clipboard."""
    content = log_window.get(1.0, tk.END).strip()
    if content:
        root.clipboard_clear()
        root.clipboard_append(content)
        root.update()
        status_label.config(text="Output copied to clipboard!", fg="green")

def clear_input():
    """Clears the input text area."""
    input_area.delete(1.0, tk.END)

# --- GUI Setup ---
root = tk.Tk()
root.title("File Content Aggregator")
root.geometry("800x750")

# 1. Input Area (Top)
input_frame = tk.LabelFrame(root, text="File Selection", padx=10, pady=10)
input_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)

# --- Base Path Section ---
base_path_frame = tk.Frame(input_frame)
base_path_frame.pack(fill=tk.X, pady=(0, 5)) # Fixed packing error here

tk.Label(base_path_frame, text="Base Path (Optional): ").pack(side=tk.LEFT)

base_path_var = tk.StringVar()
base_path_entry = tk.Entry(base_path_frame, textvariable=base_path_var)
base_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

browse_btn = tk.Button(base_path_frame, text="Browse Folder...", command=browse_base_path)
browse_btn.pack(side=tk.LEFT)
# ------------------------------

tk.Label(input_frame, text="Enter File Names (One per line):").pack(anchor=tk.W)

input_area = scrolledtext.ScrolledText(input_frame, height=8)
input_area.pack(fill=tk.BOTH, expand=True)

# 2. Button Controls (Middle)
btn_frame = tk.Frame(root, pady=5)
btn_frame.pack(fill=tk.X, padx=10)

process_btn = tk.Button(btn_frame, text="Process Paths", command=process_paths, bg="#dddddd", height=2, width=15)
process_btn.pack(side=tk.LEFT, padx=(0, 5))

# --- NEW BUTTON ---
npp_btn = tk.Button(btn_frame, text="Open in Notepad++", command=open_in_npp, bg="#fffacd", height=2, width=18)
npp_btn.pack(side=tk.LEFT, padx=5)
# ------------------

clear_btn = tk.Button(btn_frame, text="Clear Input", command=clear_input, height=2)
clear_btn.pack(side=tk.LEFT, padx=5)

copy_btn = tk.Button(btn_frame, text="Copy Output", command=copy_to_clipboard, bg="#add8e6", height=2, width=15)
copy_btn.pack(side=tk.RIGHT)

# 3. Output Log (Bottom)
output_frame = tk.LabelFrame(root, text="Output Log", padx=10, pady=10)
output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

log_window = scrolledtext.ScrolledText(output_frame, state=tk.DISABLED)
log_window.pack(fill=tk.BOTH, expand=True)

# Styling tags
log_window.tag_config("header_tag", background="#e1e1e1", foreground="black", font=("Arial", 10, "bold"))
log_window.tag_config("path_tag", foreground="gray", font=("Arial", 8, "italic"))
log_window.tag_config("error_tag", foreground="red")

# Status Bar
status_label = tk.Label(root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
status_label.pack(side=tk.BOTTOM, fill=tk.X)

root.mainloop()