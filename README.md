# Tools

Small collection of local tools to speed up code navigation and safe code editing.

## Contents

- `openInNotepad.py`  
  GUI helper to open many files at once in Notepad++.
- `pythonInsert.py`  
  GUI helper to insert a code block between two existing blocks in a file, with whitespace‑tolerant matching.
- `path_blocks_combined.xlsx`  
  Excel workbook that generates “fetch” and “give” text blocks for a list of file paths.

---

## Requirements

- Windows
- Python 3.x (with Tkinter, usually included in standard Python installs)
- Notepad++ (for `openInNotepad.py`), installed at:

  ```text
  C:\Program Files\Notepad++\notepad++.exe




Below is a concise README for the GUI-based path‑scanner script you requested.
It is general-purpose and does not reference any of your private paths.
It also reflects the behavior and filtering logic shown in your earlier scripts .

---

# Path Scanner Tool

A small utility script that scans any selected project folder and produces a clean, filtered list of all paths (folders + files). It automatically ignores useless or heavy directories such as `node_modules`, `.git`, `venv`, etc., making it suitable for many kinds of codebases.

The script launches a simple GUI dialog to let you pick the folder and choose where to save the output file.

---

## Features

* Choose the project folder via GUI (no command-line arguments needed).
* Recursively scans all subfolders.
* Filters out unwanted directories and system files.
* Outputs a clean list of **relative paths**, with the **base path written on the first line**.
* Works for any project structure (frontend, backend, Python, Node.js, etc.).

---

## Excluded folders

These directories are ignored during the scan:

```
.git
.hg
.svn
node_modules
env
.venv
venv
__pycache__
dist
build
coverage
.next
.turbo
.storybook
storybook-static
.idea
.vscode
test-results
test-output
```

Excluded files:

```
.DS_Store
```

---

## How to Use

### 1. Install Python 3

Make sure you have Python 3.7 or later installed.

### 2. Save the script

Save the Python file (e.g. `scan_paths_gui.py`) anywhere on your system.

### 3. Run it

Double‑click it, or run from terminal:

```bash
python scan_paths_gui.py
```

### 4. Choose the folder to scan

A folder selection dialog appears.
Pick the project you want to analyze.

### 5. Choose the output file

Select where to save the generated `paths.txt`.

### 6. Done

The file will contain:

* Line 1 → the absolute base path
* Lines 2+ → all project paths relative to that base, one per line, filtered and sorted.

---

## Output Example

```
/Users/you/projects/my-app
src
src/index.js
src/components/App.jsx
public
public/index.html
package.json
```

---

## License

Free for personal and commercial use.

---

If you want, I can add installation instructions, screenshots, or turn this into a PyInstaller one‑file executable.
