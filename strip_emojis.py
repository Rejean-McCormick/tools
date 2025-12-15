#!/usr/bin/env python3
"""
Strip icons (emoji/pictographs) from Markdown files recursively.

Usage:
  python strip_icons_md.py /path/to/repo
  python strip_icons_md.py . --dry-run
"""

from __future__ import annotations
import argparse
import os
import re
from pathlib import Path

# Broad emoji / pictograph coverage (keeps accents/normal unicode letters).
EMOJI_RE = re.compile(
    "["

    # Emoticons
    "\U0001F600-\U0001F64F"

    # Misc Symbols and Pictographs
    "\U0001F300-\U0001F5FF"

    # Transport and Map
    "\U0001F680-\U0001F6FF"

    # Supplemental Symbols and Pictographs
    "\U0001F900-\U0001F9FF"

    # Symbols and Pictographs Extended-A
    "\U0001FA70-\U0001FAFF"

    # Flags
    "\U0001F1E6-\U0001F1FF"

    # Misc symbols + Dingbats (☑ ✓ ✨ etc.)
    "\u2600-\u26FF"
    "\u2700-\u27BF"

    # Variation selectors, ZWJ, keycap combining mark
    "\uFE0F"  # VS16
    "\u200D"  # ZWJ
    "\u20E3"  # keycap
    "]"
)

SKIN_TONE_RE = re.compile("[\U0001F3FB-\U0001F3FF]")

DEFAULT_SKIP_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "dist", "build", "out",
    "_book", ".next", ".cache",
    ".venv", "venv", "__pycache__",
}

def strip_icons(text: str) -> str:
    text = EMOJI_RE.sub("", text)
    text = SKIN_TONE_RE.sub("", text)
    return text

def process_file(path: Path, dry_run: bool) -> bool:
    try:
        original = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # If a file isn't UTF-8, skip it safely.
        return False

    cleaned = strip_icons(original)
    if cleaned == original:
        return False

    if not dry_run:
        path.write_text(cleaned, encoding="utf-8")

    return True

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=str, help="Root folder to process")
    ap.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    ap.add_argument("--skip-dir", action="append", default=[], help="Additional directory name(s) to skip")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    skip_dirs = DEFAULT_SKIP_DIRS.union(args.skip_dir)

    changed = 0
    scanned = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # In-place prune skipped dirs
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]

        for fn in filenames:
            if not fn.lower().endswith(".md"):
                continue
            scanned += 1
            p = Path(dirpath) / fn
            if process_file(p, args.dry_run):
                changed += 1
                print(("DRY " if args.dry_run else "") + f"CHANGED: {p}")

    print(f"\nScanned .md files: {scanned}")
    print(f"Changed files:     {changed}" + (" (dry-run)" if args.dry_run else ""))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
