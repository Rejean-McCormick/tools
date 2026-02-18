# gitignore_engine.py
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class GitIgnoreEngine:
    """
    Minimal .gitignore/.smartignore parser + matcher, aligned with the original script.

    Notes:
    - Supports comments, negation (!), directory-only rules (trailing /), and anchoring (leading /).
    - Matching uses fnmatch on either relative-from-base (anchored or patterns with '/')
      or on basename (simple patterns).
    - Traversal excludes ALWAYS_IGNORE_DIRS and (optionally) custom-excluded dirs when mode is Fully Exclude.
    """

    def __init__(
        self,
        root_dir: Path,
        always_ignore_dirs: set[str],
        log: Callable[[str], None],
        check_stop: Callable[[], None],
        is_custom_excluded: Callable[[Path], bool],
        exclusion_mode_getter: Callable[[], str],
    ):
        self.root_dir = root_dir.resolve()
        self.ALWAYS_IGNORE_DIRS = always_ignore_dirs
        self.log = log
        self.check_stop = check_stop
        self.is_custom_excluded = is_custom_excluded
        self.exclusion_mode_getter = exclusion_mode_getter
        self.rules: List[Dict[str, Any]] = []

    # -----------------------------
    # Parsing
    # -----------------------------

    def _parse_gitignore_line(self, raw: str) -> Optional[Dict[str, Any]]:
        # Strip line endings
        line = raw.rstrip("\n").rstrip("\r")
        if not line:
            return None

        # BOM safety (some files begin with BOM)
        if line.startswith("\ufeff"):
            line = line.lstrip("\ufeff")

        # Trailing spaces are ignored unless escaped with '\ '
        while line.endswith(" ") and not line.endswith("\\ "):
            line = line[:-1]
        if line.endswith("\\ "):
            line = line[:-2] + " "

        if line.strip() == "":
            return None

        # Comment handling: '#' is comment unless escaped as '\#'
        escaped_prefix = line.startswith("\\#") or line.startswith("\\!")
        if escaped_prefix:
            line = line[1:]
        if line.startswith("#") and not escaped_prefix:
            return None

        # Negation handling: '!' negates unless escaped as '\!'
        neg = False
        if line.startswith("!") and not escaped_prefix:
            neg = True
            line = line[1:]
            if line == "":
                return None

        # Directory-only rules end with '/'
        dir_only = line.endswith("/")
        if dir_only:
            line = line[:-1]

        # Anchored rules start with '/'
        anchored = line.startswith("/")
        if anchored:
            line = line[1:]

        if line == "":
            return None

        return {"pattern": line, "neg": neg, "dir_only": dir_only, "anchored": anchored}

    # -----------------------------
    # Loading
    # -----------------------------

    def load_all_gitignores(self) -> List[Dict[str, Any]]:
        """
        Walk root_dir, find .gitignore and .smartignore files, parse them into rules,
        and store them on self.rules.

        Each parsed rule gets:
        - pattern, neg, dir_only, anchored
        - base: Path of the directory containing the ignore file
        """
        rules: List[Dict[str, Any]] = []
        self.log("-> Scanning for .gitignore and .smartignore files...")
        count = 0

        for root, dirnames, files in os.walk(self.root_dir, followlinks=True):
            self.check_stop()
            current_dir = Path(root).resolve()

            # Prune traversal dirs early
            safe_dirs: List[str] = []
            for d in dirnames:
                if d in self.ALWAYS_IGNORE_DIRS:
                    continue

                full_dir = current_dir / d

                # If custom-excluded and mode is Fully Exclude, skip descent
                if self.is_custom_excluded(full_dir) and self.exclusion_mode_getter() == "Fully Exclude":
                    continue

                safe_dirs.append(d)
            dirnames[:] = safe_dirs

            for ignore_file in (".gitignore", ".smartignore"):
                if ignore_file not in files:
                    continue

                git_path = current_dir / ignore_file
                try:
                    with git_path.open("r", encoding="utf-8-sig", errors="replace") as f:
                        for raw in f:
                            parsed = self._parse_gitignore_line(raw)
                            if not parsed:
                                continue
                            parsed["base"] = current_dir
                            rules.append(parsed)
                    count += 1
                except Exception:
                    # Keep behavior tolerant: ignore unreadable ignore files
                    pass

        self.rules = rules
        self.log(f"-> Loaded {count} ignore files ({len(rules)} rules).")
        return rules

    # -----------------------------
    # Matching
    # -----------------------------

    def _rule_applies(self, rule_base: Path, path: Path) -> bool:
        # Same semantics as original script: rule applies to anything under its base directory.
        return str(path).startswith(str(rule_base))

    def _match_rule(self, rule: Dict[str, Any], path: Path, is_dir: bool) -> bool:
        base: Path = rule["base"]
        try:
            rel_from_base = path.relative_to(base).as_posix()
        except Exception:
            return False

        name = path.name
        pat = rule["pattern"]

        # Directory-only rule
        if rule["dir_only"]:
            if not is_dir:
                return False

            # Anchored or contains '/', match against rel path / prefix
            if rule["anchored"] or ("/" in pat):
                if fnmatch.fnmatch(rel_from_base, pat):
                    return True
                return rel_from_base == pat or rel_from_base.startswith(pat + "/")

            # Otherwise match only directory name
            return fnmatch.fnmatch(name, pat)

        # File/dir rule (non-dir-only)
        if rule["anchored"] or ("/" in pat):
            return fnmatch.fnmatch(rel_from_base, pat)

        return fnmatch.fnmatch(name, pat)

    def match_ignore(self, path: Path, is_dir: bool) -> bool:
        """
        Returns True if the path is ignored by rules, else False.
        Implements "last match wins" semantics with negation.
        """
        ignored = False
        for rule in self.rules:
            if not self._rule_applies(rule["base"], path):
                continue
            if self._match_rule(rule, path, is_dir=is_dir):
                ignored = not rule["neg"]
        return ignored
