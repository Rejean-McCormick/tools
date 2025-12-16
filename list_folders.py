import tkinter as tk
from tkinter import filedialog, scrolledtext
import os

def list_folders_recursively():
    # Open the folder selection dialog
    root_folder = filedialog.askdirectory()
    
    if not root_folder:
        return # User cancelled
    
    # Clear the text area
    text_area.delete('1.0', tk.END)
    text_area.insert(tk.END, f"Scanning: {root_folder}\n" + "-"*50 + "\n")
    
    # Update the UI to show we are working
    window.update()
    
    # Walk through the directory tree
    try:
        count = 0
        for root, dirs, files in os.walk(root_folder):
            for name in dirs:
                full_path = os.path.join(root, name)
                text_area.insert(tk.END, full_path + "\n")
                count += 1
        
        text_area.insert(tk.END, "\n" + "-"*50 + f"\nFinished. Total folders found: {count}")
    except Exception as e:
        text_area.insert(tk.END, f"\nError: {e}")

# --- UI Setup ---
window = tk.Tk()
window.title("Recursive Folder Lister")
window.geometry("600x400")

# Top Button
btn_select = tk.Button(window, text="Select Root Folder", command=list_folders_recursively, bg="#e1e1e1", pady=5)
btn_select.pack(fill=tk.X, padx=10, pady=5)

# Scrollable Text Area
text_area = scrolledtext.ScrolledText(window, width=70, height=20)
text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

window.mainloop()