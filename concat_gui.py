#!/usr/bin/env python3
"""
concat_gui.py

Concatenate all text-like files from a chosen folder (and subfolders)
into a single .txt file with an index (TOC) at the top.

Usage:
  python concat_gui.py
  (or double-click in a GUI environment)
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from datetime import datetime
from typing import Iterable, List, Set, Optional

import tkinter as tk
from tkinter import filedialog, messagebox

# ---------------------------------------------------------------------------
# Configuration / filters
# ---------------------------------------------------------------------------

# Same spirit as your existing script: extensions considered as "likely text"
ALLOWED_EXTS: Set[str] = {
    ".txt", ".md", ".markdown",
    ".json", ".yaml", ".yml", ".xml", ".toml", ".ini", ".cfg", ".conf", ".properties",
    ".html", ".htm", ".css", ".scss", ".less",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".py", ".pyi",
    ".java", ".kt", ".swift", ".rb", ".php", ".go", ".rs",
    ".c", ".h", ".cpp", ".cc", ".hpp", ".cs",
    ".sql",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat",
    ".tex", ".bib",
    ".graphql", ".gql",
    ".gradle",
    ".pl", ".lua", ".r",
    ".env",
}

# Files without extension that should still be treated as text
NAMES_WITHOUT_EXT: Set[str] = {
    "Dockerfile", "Makefile", "CMakeLists.txt",
    ".gitignore", ".gitattributes", ".editorconfig",
    "Procfile", "requirements.txt", "Pipfile", "poetry.lock",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "tsconfig.json", ".eslintrc", ".prettierrc", "eslint.config.js",
}

# Directories to skip completely when walking
EXCLUDE_DIRS: Set[str] = {
    ".git", ".hg", ".svn",
    "node_modules", ".next", ".nuxt",
    "dist", "build", "out", "coverage", ".cache",
    ".venv", "venv", "__pycache__",
    "target", "bin", "obj",
}

# Max size per source file (bytes). Adjust if needed.
MAX_FILE_SIZE = 2_000_000  # 2 MB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def to_rel(base: Path, p: Path) -> str:
    """Return a path relative to base, with forward slashes."""
    try:
        r = p.relative_to(base)
    except Exception:
        r = p
    return str(r).replace("\\", "/")


def is_text_file(path: Path) -> bool:
    """
    Heuristic to decide if a file is text:
    - Known extension or name OR
    - No NUL bytes in the first chunk and low control-char ratio.
    """
    if path.suffix.lower() in ALLOWED_EXTS or path.name in NAMES_WITHOUT_EXT:
        return True

    try:
        with path.open("rb") as f:
            sample = f.read(32768)
    except Exception:
        return False

    if b"\x00" in sample:
        return False

    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        ctrl = sum(1 for b in sample if b < 32 and b not in (9, 10, 13))
        return (ctrl / max(1, len(sample))) < 0.01


def pick_encoding(path: Path) -> Optional[str]:
    """Try a few encodings and return the first one that works."""
    for enc in ("utf-8", "utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            with path.open("r", encoding=enc) as f:
                f.read(2048)
            return enc
        except Exception:
            continue
    return "latin-1"  # fallback


def matches_any(rel: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def collect_files(base: Path, out_path: Path,
                  max_size: int = MAX_FILE_SIZE) -> List[Path]:
    """
    Walk base and return a sorted list of text-like files, excluding:
      - large files (> max_size)
      - binary files
      - the output file itself
      - some build/cache directories
    """
    files: List[Path] = []

    for root, dirs, filenames in os.walk(base, followlinks=False):
        # Filter directories in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        root_path = Path(root)
        for name in filenames:
            p = root_path / name

            if not p.is_file() or p.is_symlink():
                continue

            # Skip the output file itself if it's inside base
            if p.resolve() == out_path.resolve():
                continue

            try:
                if max_size and p.stat().st_size > max_size:
                    continue
            except OSError:
                continue

            if not is_text_file(p):
                continue

            files.append(p)

    files.sort(key=lambda q: to_rel(base, q).lower())
    return files


def write_toc(out_fp, files: List[Path], base: Path) -> None:
    """Write a simple TOC/index at the top of the output file."""
    out_fp.write(f"===== TOC ({len(files)} files) =====\n")
    for i, p in enumerate(files, 1):
        rel = to_rel(base, p)
        out_fp.write(f"{i:04d}  {rel}\n")
    out_fp.write("===== END TOC =====\n\n")


def concatenate_folder(base: Path, out_path: Path,
                       max_size: int = MAX_FILE_SIZE) -> int:
    """
    Concatenate all selected files into out_path.
    Returns the number of files written.
    """
    files = collect_files(base, out_path, max_size=max_size)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8", newline="\n") as out:
        # Index at the top
        write_toc(out, files, base)

        # Body: BEGIN/END blocks per file
        for idx, p in enumerate(files, 1):
            enc = pick_encoding(p) or "utf-8"
            rel = to_rel(base, p)

            out.write(f"\n===== BEGIN {rel} (#{idx:04d}) =====\n")

            try:
                with p.open("r", encoding=enc, errors="strict") as f:
                    for line in f:
                        out.write(line)
            except UnicodeDecodeError:
                # Fallback with replacement characters
                with p.open("r", encoding="latin-1", errors="replace") as f:
                    for line in f:
                        out.write(line)

            out.write(f"\n===== END {rel} (#{idx:04d}) =====\n")

    return len(files)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

def main() -> None:
    root = tk.Tk()
    root.withdraw()  # no main window, just dialogs

    # 1) Ask for base folder
    base_dir = filedialog.askdirectory(
        title="Select the root folder to concatenate"
    )
    if not base_dir:
        messagebox.showinfo("Cancelled", "No folder selected.")
        return

    base = Path(base_dir)

    # 2) Ask where to save the output .txt
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_name = f"concat_{stamp}.txt"

    out_file = filedialog.asksaveasfilename(
        title="Choose output text file",
        defaultextension=".txt",
        initialfile=default_name,
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    if not out_file:
        messagebox.showinfo("Cancelled", "No output file selected.")
        return

    out_path = Path(out_file)

    # 3) Run concatenation
    try:
        count = concatenate_folder(base, out_path)
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred:\n{e}")
        return

    messagebox.showinfo(
        "Done",
        f"Concatenation finished.\n\n"
        f"Folder: {base}\n"
        f"Output: {out_path}\n"
        f"Files included: {count}"
    )


if __name__ == "__main__":
    main()
