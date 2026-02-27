# worker/smartignore.py
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Set


@dataclass
class SmartIgnore:
    """
    Minimal .smartignore support (intentionally simple/predictable):
      - ignores blank lines and comments (#...)
      - NO negation support
      - patterns are glob-like (fnmatch)
      - trailing "/" means "directory-only"
      - leading "/" anchors to repo root
      - patterns without "/" match basename only
      - patterns with "/" may match full path OR any suffix segment ("match anywhere-ish")

    Also supports optional "matched paths index" generation:
      - records all matched paths (files + dirs) and matched dirs
      - can write SmartignorePathsIndex.txt into output_dir
    """

    root_dir: Path
    log: Callable[[str], None]

    use_smartignore_exclude: bool = False
    create_smartignore_paths_index: bool = False

    smartignore_filename: str = ".smartignore"
    patterns: List[str] = field(default_factory=list)

    matched_paths: Set[str] = field(default_factory=set)
    matched_dirs: Set[str] = field(default_factory=set)

    @property
    def smartignore_file(self) -> Path:
        return (self.root_dir / self.smartignore_filename).resolve()

    def load(self) -> None:
        """Load patterns from repo_root/.smartignore and reset match tracking."""
        self.patterns.clear()
        self.matched_paths.clear()
        self.matched_dirs.clear()

        p = self.smartignore_file
        if not p.exists():
            return

        try:
            raw_lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in raw_lines:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                # minimal: no negation support; keep predictable
                self.patterns.append(s)
        except Exception as e:
            self.log(f"(warn) Could not read {self.smartignore_filename}: {e}")

    def rel_posix(self, path: Path) -> str:
        """Best-effort: path relative to root_dir as posix; fallback to absolute posix."""
        try:
            return path.resolve().relative_to(self.root_dir.resolve()).as_posix()
        except Exception:
            try:
                return path.resolve().as_posix()
            except Exception:
                return str(path).replace("\\", "/")

    def _record_match(self, rel_posix: str, is_dir: bool) -> None:
        if not self.create_smartignore_paths_index:
            return
        self.matched_paths.add(rel_posix)
        if is_dir:
            self.matched_dirs.add(rel_posix)

    def match(self, rel_posix: str, *, is_dir: bool) -> bool:
        """
        Returns True if rel_posix matches any smartignore pattern.
        rel_posix MUST be a posix-style relative path (e.g. "src/app/main.py").
        """
        if not self.patterns:
            return False

        path = rel_posix
        base = path.rsplit("/", 1)[-1]

        for pat_raw in self.patterns:
            pat = pat_raw.strip()
            if not pat:
                continue

            # directory-only
            if pat.endswith("/"):
                pat = pat[:-1].strip()
                if not pat:
                    continue
                if not is_dir:
                    continue

            # anchored
            if pat.startswith("/"):
                pat2 = pat[1:]
                if fnmatch.fnmatch(path, pat2):
                    self._record_match(rel_posix, is_dir=is_dir)
                    return True
                continue

            # basename-only
            if "/" not in pat:
                if fnmatch.fnmatch(base, pat):
                    self._record_match(rel_posix, is_dir=is_dir)
                    return True
                continue

            # direct path match
            if fnmatch.fnmatch(path, pat):
                self._record_match(rel_posix, is_dir=is_dir)
                return True

            # "match anywhere": try matching against suffixes by segment boundary
            parts = path.split("/")
            for i in range(1, len(parts)):
                suffix = "/".join(parts[i:])
                if fnmatch.fnmatch(suffix, pat):
                    self._record_match(rel_posix, is_dir=is_dir)
                    return True

        return False

    def should_exclude(self, rel_posix: str, *, is_dir: bool) -> bool:
        """
        Returns True iff the path matches AND use_smartignore_exclude is enabled.
        (Always records matches if create_smartignore_paths_index is enabled.)
        """
        m = self.match(rel_posix, is_dir=is_dir)
        return bool(m and self.use_smartignore_exclude)

    def write_paths_index(
        self,
        *,
        output_dir: Path,
        check_stop: Callable[[], None],
    ) -> None:
        """Write SmartignorePathsIndex.txt in output_dir (if enabled)."""
        if not self.create_smartignore_paths_index:
            return

        check_stop()
        out_path = (output_dir / "SmartignorePathsIndex.txt").resolve()

        try:
            with out_path.open("w", encoding="utf-8", errors="replace") as f:
                f.write("==== SMARTIGNORE PATHS INDEX ====\n")
                f.write(f"generated_at: {datetime.now().isoformat()}\n")
                f.write(f"repo_root: {self.root_dir}\n")
                f.write(f"smartignore_file: {self.smartignore_file}\n")
                f.write(f"patterns_count: {len(self.patterns)}\n")
                f.write(f"matched_paths_count: {len(self.matched_paths)}\n")
                f.write(f"matched_dirs_count: {len(self.matched_dirs)}\n\n")

                f.write("==== PATTERNS (.smartignore) ====\n")
                for p in self.patterns:
                    f.write(p + "\n")

                f.write("\n==== MATCHED DIRECTORIES ====\n")
                for p in sorted(self.matched_dirs):
                    f.write(p + "\n")

                f.write("\n==== MATCHED PATHS (FILES + DIRS) ====\n")
                for p in sorted(self.matched_paths):
                    f.write(p + "\n")

            self.log("-> Created SmartignorePathsIndex.txt")
        except Exception as e:
            self.log(f"(warn) Could not write SmartignorePathsIndex.txt: {e}")