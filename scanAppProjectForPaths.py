#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

# Folders that will NOT be scanned (by name only, not by full path).
EXCLUDED_DIRS = {
    # VCS / tooling
    ".git", ".hg", ".svn",
    ".idea", ".vscode",

    # Node / frontend
    "node_modules", "bower_components", "dist", "build",
    ".next", ".turbo", "storybook-static", ".storybook",

    # Python / virtualenv
    "env", ".envs", "venv", ".venv", "__pycache__",

    # Test / coverage / artifacts
    "coverage", ".pytest_cache", ".nyc_output",
    "test-results", "test-output",

    # Misc / static / binaries
    "static", "staticfiles", "lib", "libraries", "bin",
}

EXCLUDED_FILES = {
    ".DS_Store",
}


def scan_paths(root: Path) -> list[str]:
    """
    Return a sorted list of all relative paths (dirs + files)
    under 'root', excluding EXCLUDED_DIRS and EXCLUDED_FILES.
    """
    root = root.resolve()
    results: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # Filter directories in-place so os.walk does not descend into them
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        dirnames.sort()

        # Filter files
        filenames[:] = [f for f in filenames if f not in EXCLUDED_FILES]
        filenames.sort()

        current_dir = Path(dirpath)

        # Add directory itself (relative), except the root itself
        rel_dir = current_dir.relative_to(root)
        if rel_dir != Path("."):
            results.append(rel_dir.as_posix())

        # Add files in this directory
        for filename in filenames:
            rel_file = (current_dir / filename).relative_to(root)
            results.append(rel_file.as_posix())

    return results


def main() -> None:
    # Initialize a minimal Tk root just to use dialogs
    root = tk.Tk()
    root.withdraw()  # Hide the main window

    # 1) Pick the project folder
    project_dir = filedialog.askdirectory(
        title="Select project folder to scan"
    )
    if not project_dir:
        return  # user cancelled

    project_dir_path = Path(project_dir).resolve()

    # 2) Choose where to save the path list
    save_path = filedialog.asksaveasfilename(
        title="Save path list as",
        defaultextension=".txt",
        initialfile="paths.txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
    )
    if not save_path:
        return  # user cancelled

    save_path = Path(save_path)

    # 3) Scan and collect paths
    paths = scan_paths(project_dir_path)

    # 4) Write base path on first line, then each relative path on its own line
    with save_path.open("w", encoding="utf-8", newline="\n") as f:
        # First line: absolute base path
        f.write(str(project_dir_path) + "\n")
        # Following lines: relative paths (dirs + files)
        for p in paths:
            f.write(p + "\n")

    messagebox.showinfo(
        "Scan complete",
        f"Base path:\n{project_dir_path}\n\n"
        f"Found {len(paths)} paths.\n"
        f"Saved to:\n{save_path}"
    )

    root.destroy()


if __name__ == "__main__":
    main()
