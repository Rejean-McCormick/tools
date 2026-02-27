# smart_wiki_dumper/worker/file_collection.py
from __future__ import annotations

import os
from pathlib import Path
from typing import List

from ..constants import ALWAYS_IGNORE_DIRS, ALWAYS_IGNORE_EXT, ALWAYS_IGNORE_FILES


class FileCollectionMixin:
    """
    Mixin extracted from DumpWorker.

    Requires the host class to provide:
      - self.root_dir: Path
      - self.ignore_txt: bool
      - self.ignore_md: bool
      - self.exclusion_mode: str
      - self.tracked_custom_exclusions: list[str]
      - self.smartignore_patterns: list[str]
      - self.use_smartignore_exclude: bool
      - self.gitignore with method match_ignore(path: Path, is_dir: bool) -> bool
      - methods:
          * check_stop() -> None
          * is_custom_excluded(path: Path) -> bool
          * _smartignore_match(rel_posix: str, *, is_dir: bool) -> bool
          * _record_smartignore_match(rel_posix: str, is_dir: bool) -> None
    """

    def collect_files_in_folder(self, folder_path: Path, recursive: bool = True) -> List[Path]:
        valid_files: List[Path] = []

        folder_path = folder_path.resolve()
        if recursive:
            iterator = os.walk(folder_path, followlinks=True)
        else:
            try:
                iterator = [next(os.walk(folder_path, followlinks=True))]
            except StopIteration:
                return []

        for dirpath, dirnames, filenames in iterator:
            self.check_stop()
            current_dir = Path(dirpath).resolve()

            safe_dirs: List[str] = []
            for d in dirnames:
                if d in ALWAYS_IGNORE_DIRS:
                    continue

                full_dir_path = (current_dir / d).resolve()

                # smartignore directory check (relative to repo root when possible)
                try:
                    rel_dir = full_dir_path.relative_to(self.root_dir).as_posix()
                except Exception:
                    rel_dir = full_dir_path.as_posix()

                if self.smartignore_patterns:
                    m = self._smartignore_match(rel_dir, is_dir=True)
                    if m:
                        self._record_smartignore_match(rel_dir, is_dir=True)
                        if self.use_smartignore_exclude:
                            continue

                if self.gitignore.match_ignore(full_dir_path, is_dir=True):
                    continue

                if self.is_custom_excluded(full_dir_path):
                    try:
                        rel = full_dir_path.relative_to(self.root_dir)
                    except Exception:
                        rel = full_dir_path
                    self.tracked_custom_exclusions.append(str(rel) + " (DIR)")
                    if self.exclusion_mode == "Fully Exclude":
                        continue

                safe_dirs.append(d)

            # prune traversal
            dirnames[:] = safe_dirs

            for f in filenames:
                self.check_stop()

                fpath = (current_dir / f).resolve()
                ext = fpath.suffix.lower()

                if f in ALWAYS_IGNORE_FILES:
                    continue
                if ext in ALWAYS_IGNORE_EXT:
                    continue

                # smartignore file check (relative to repo root when possible)
                try:
                    rel_file = fpath.relative_to(self.root_dir).as_posix()
                except Exception:
                    rel_file = fpath.as_posix()

                if self.smartignore_patterns:
                    m = self._smartignore_match(rel_file, is_dir=False)
                    if m:
                        self._record_smartignore_match(rel_file, is_dir=False)
                        if self.use_smartignore_exclude:
                            continue

                if self.gitignore.match_ignore(fpath, is_dir=False):
                    continue

                if self.is_custom_excluded(fpath):
                    try:
                        rel = fpath.relative_to(self.root_dir)
                    except Exception:
                        rel = fpath
                    self.tracked_custom_exclusions.append(str(rel))
                    if self.exclusion_mode == "Fully Exclude":
                        continue

                if self.ignore_txt and ext == ".txt":
                    continue
                if self.ignore_md and ext == ".md":
                    continue

                valid_files.append(fpath)

        return valid_files