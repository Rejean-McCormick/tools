import os
import json
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

def create_notebook_structure():
    """Returns the JSON structure for a blank Jupyter Notebook."""
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
    """Wraps text content into a Jupyter Markdown cell structure."""
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": content.splitlines(keepends=True)
    }

def generate_notebook(source_folder, output_folder):
    """Scans the source folder and builds the .ipynb file."""
    
    source_path = Path(source_folder)
    output_path = Path(output_folder)
    
    # Name the notebook after the folder name
    notebook_name = f"{source_path.name}.ipynb"
    output_file = output_path / notebook_name

    notebook_data = create_notebook_structure()
    
    # 1. Add a Title Cell
    title_text = f"# 📂 {source_path.name}\n\nGenerated from Markdown files."
    notebook_data["cells"].append(create_markdown_cell(title_text))

    files_processed = 0

    # 2. Walk through the directory
    for root, dirs, files in os.walk(source_path):
        # Sort to keep 01, 02, 03 order
        dirs.sort()
        files.sort()

        # If we are in a subfolder, add a sub-header cell
        rel_path = os.path.relpath(root, source_path)
        if rel_path != ".":
            group_header = f"## 📁 {rel_path.replace(os.sep, ' > ')}"
            notebook_data["cells"].append(create_markdown_cell(group_header))

        for file in files:
            if file.lower().endswith(".md"):
                file_full_path = os.path.join(root, file)
                
                try:
                    with open(file_full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    # Optional: Add filename as a small comment at the top of the cell
                    content_with_meta = f"\n\n{content}"
                    
                    # Add to notebook
                    notebook_data["cells"].append(create_markdown_cell(content_with_meta))
                    files_processed += 1
                except Exception as e:
                    print(f"Skipping {file}: {e}")

    # 3. Write the JSON file
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(notebook_data, f, indent=2)
        return True, str(output_file), files_processed
    except Exception as e:
        return False, str(e), 0

# --- GUI Application ---

class NotebookConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Markdown to Jupyter Notebook Converter")
        self.root.geometry("500x250")

        # Variables
        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar()

        # UI Layout
        pad_opts = {'padx': 10, 'pady': 5}

        # Source Selection
        tk.Label(root, text="Select Source Folder (containing .md files):").pack(anchor="w", **pad_opts)
        src_frame = tk.Frame(root)
        src_frame.pack(fill="x", **pad_opts)
        tk.Entry(src_frame, textvariable=self.source_var).pack(side="left", fill="x", expand=True)
        tk.Button(src_frame, text="Browse...", command=self.select_source).pack(side="right", padx=(5, 0))

        # Output Selection
        tk.Label(root, text="Select Output Folder:").pack(anchor="w", **pad_opts)
        out_frame = tk.Frame(root)
        out_frame.pack(fill="x", **pad_opts)
        tk.Entry(out_frame, textvariable=self.output_var).pack(side="left", fill="x", expand=True)
        tk.Button(out_frame, text="Browse...", command=self.select_output).pack(side="right", padx=(5, 0))

        # Convert Button
        tk.Button(root, text="Generate Notebook", command=self.run_conversion, bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(pady=20)

    def select_source(self):
        folder = filedialog.askdirectory()
        if folder:
            self.source_var.set(folder)
            # Auto-set output to the parent of source if empty
            if not self.output_var.get():
                self.output_var.set(str(Path(folder).parent))

    def select_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_var.set(folder)

    def run_conversion(self):
        src = self.source_var.get()
        out = self.output_var.get()

        if not src or not out:
            messagebox.showwarning("Missing Info", "Please select both folders.")
            return

        success, result_msg, count = generate_notebook(src, out)

        if success:
            messagebox.showinfo("Success", f"Notebook created successfully!\n\nFiles merged: {count}\nSaved to:\n{result_msg}")
        else:
            messagebox.showerror("Error", f"Failed to create notebook:\n{result_msg}")

if __name__ == "__main__":
    root = tk.Tk()
    app = NotebookConverterApp(root)
    root.mainloop()