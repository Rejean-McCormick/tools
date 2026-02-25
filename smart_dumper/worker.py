# worker.py
from __future__ import annotations

import concurrent.futures
import fnmatch
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .constants import (
    ALWAYS_IGNORE_DIRS,
    ALWAYS_IGNORE_EXT,
    ALWAYS_IGNORE_FILES,
    CHUNK_MAX_LINES,
    INSTRUCTIONS_FILENAME,
    OVERSIZE_BYTES,
)
from .gitignore_engine import GitIgnoreEngine
from .xml_utils import (
    chunk_lines_keepends,
    escape_xml_attr,
    escape_xml_text,
    short_sha1,
    wrap_cdata,
)


class DumpWorker:
    """
    Output formats (no JSONL):
      - output_format="text" : structured plain-text volumes (DEFAULT)
      - output_format="xml"  : XML volumes (optional)

    XML-only option:
      - txt_mode:
          * "none": .xml only
          * "copy": .xml and also .xml.txt companions (for indexing)
          * "only": .xml.txt only (no .xml)

    .smartignore options:
      - use_smartignore_exclude:
          excludes any file/dir matching patterns from repo_root/.smartignore
      - create_smartignore_paths_index:
          writes SmartignorePathsIndex.txt listing all matched paths (+ patterns)
          regardless of exclusion mode.
    """

    def __init__(
        self,
        root_dir: Path,
        output_dir: Path,
        max_output_files: int,
        ignore_txt: bool,
        ignore_md: bool,
        create_index: bool,
        custom_excludes: List[Path],
        exclusion_mode: str,
        log_callback: Callable[[str], None],
        overwrite_callback: Callable[[str], bool],
        stop_event,
        *,
        output_format: str = "text",  # DEFAULT = txt structuré
        txt_mode: str = "copy",
        create_grouped_bundles: bool = True,
        use_smartignore_exclude: bool = False,
        create_smartignore_paths_index: bool = False,
    ):
        self.root_dir = root_dir.resolve()
        self.output_dir = output_dir.resolve()
        self.max_output_files = max(2, max_output_files)
        self.ignore_txt = ignore_txt
        self.ignore_md = ignore_md
        self.create_index = create_index
        self.custom_excludes = [p.resolve() for p in custom_excludes]
        self.exclusion_mode = exclusion_mode

        self.log = log_callback
        self.ask_overwrite = overwrite_callback
        self.stop_event = stop_event

        self.tracked_custom_exclusions: List[str] = []

        self.INSTRUCTIONS_FILENAME = INSTRUCTIONS_FILENAME
        self.CHUNK_MAX_LINES = CHUNK_MAX_LINES

        # output format (text default)
        self.output_format = (output_format or "text").strip().lower()
        if self.output_format not in ("text", "xml"):
            self.output_format = "text"

        # xml-only "txt companion" behavior
        self.txt_mode = (txt_mode or "none").strip().lower()
        if self.txt_mode not in ("none", "copy", "only"):
            self.txt_mode = "copy"

        self.create_grouped_bundles = bool(create_grouped_bundles)

        # smartignore
        self.use_smartignore_exclude = bool(use_smartignore_exclude)
        self.create_smartignore_paths_index = bool(create_smartignore_paths_index)
        self.smartignore_patterns: List[str] = []
        self.smartignore_file: Path = self.root_dir / ".smartignore"
        self.smartignore_matched_paths: Set[str] = set()
        self.smartignore_matched_dirs: Set[str] = set()
        self._load_smartignore()

        # If an unexpected error happens in the worker thread, store it so the GUI can show it.
        self.last_exception_traceback: Optional[str] = None

        self.gitignore = GitIgnoreEngine(
            root_dir=self.root_dir,
            always_ignore_dirs=ALWAYS_IGNORE_DIRS,
            log=self.log,
            check_stop=self.check_stop,
            is_custom_excluded=self.is_custom_excluded,
            exclusion_mode_getter=lambda: self.exclusion_mode,
        )
        self.gitignore.load_all_gitignores()

    def check_stop(self) -> None:
        if self.stop_event.is_set():
            raise InterruptedError("Stopped by user.")

    # -----------------------------
    # .smartignore
    # -----------------------------

    def _load_smartignore(self) -> None:
        self.smartignore_patterns.clear()
        if not self.smartignore_file.exists():
            return
        try:
            raw = self.smartignore_file.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in raw:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                # minimal: no negation support; keep predictable
                self.smartignore_patterns.append(s)
        except Exception as e:
            self.log(f"(warn) Could not read .smartignore: {e}")

    def _record_smartignore_match(self, rel_posix: str, is_dir: bool) -> None:
        if not self.create_smartignore_paths_index:
            return
        self.smartignore_matched_paths.add(rel_posix)
        if is_dir:
            self.smartignore_matched_dirs.add(rel_posix)

    def _smartignore_match(self, rel_posix: str, *, is_dir: bool) -> bool:
        """
        Basic glob matching:
          - patterns with trailing "/" apply to directories only
          - leading "/" anchors to repo root
          - patterns without "/" are matched against basename
          - patterns with "/" can match anywhere in path (approx gitignore-ish)
        """
        if not self.smartignore_patterns:
            return False

        path = rel_posix  # already posix
        base = path.rsplit("/", 1)[-1]

        for pat_raw in self.smartignore_patterns:
            pat = pat_raw.strip()

            dir_only = False
            if pat.endswith("/"):
                dir_only = True
                pat = pat[:-1].strip()
                if not pat:
                    continue
                if not is_dir:
                    continue

            anchored = pat.startswith("/")
            if anchored:
                pat2 = pat[1:]
                if fnmatch.fnmatch(path, pat2):
                    return True
                continue

            if "/" not in pat:
                # basename match
                if fnmatch.fnmatch(base, pat):
                    return True
                continue

            # path pattern: try direct match first
            if fnmatch.fnmatch(path, pat):
                return True

            # "match anywhere": try matching against suffixes by segment boundary
            parts = path.split("/")
            for i in range(1, len(parts)):
                suffix = "/".join(parts[i:])
                if fnmatch.fnmatch(suffix, pat):
                    return True

        return False

    def write_smartignore_paths_index(self) -> None:
        if not self.create_smartignore_paths_index:
            return
        self.check_stop()

        out_path = self.output_dir / "SmartignorePathsIndex.txt"
        try:
            with out_path.open("w", encoding="utf-8", errors="replace") as f:
                f.write("==== SMARTIGNORE PATHS INDEX ====\n")
                f.write(f"generated_at: {datetime.now().isoformat()}\n")
                f.write(f"repo_root: {self.root_dir}\n")
                f.write(f"smartignore_file: {self.smartignore_file}\n")
                f.write(f"patterns_count: {len(self.smartignore_patterns)}\n")
                f.write(f"matched_paths_count: {len(self.smartignore_matched_paths)}\n")
                f.write(f"matched_dirs_count: {len(self.smartignore_matched_dirs)}\n\n")

                f.write("==== PATTERNS (.smartignore) ====\n")
                for p in self.smartignore_patterns:
                    f.write(p + "\n")

                f.write("\n==== MATCHED DIRECTORIES ====\n")
                for p in sorted(self.smartignore_matched_dirs):
                    f.write(p + "\n")

                f.write("\n==== MATCHED PATHS (FILES + DIRS) ====\n")
                for p in sorted(self.smartignore_matched_paths):
                    f.write(p + "\n")

            self.log("-> Created SmartignorePathsIndex.txt")
        except Exception as e:
            self.log(f"(warn) Could not write SmartignorePathsIndex.txt: {e}")

    # -----------------------------
    # Helpers
    # -----------------------------

    def is_custom_excluded(self, path: Path) -> bool:
        if not self.custom_excludes:
            return False
        for exc in self.custom_excludes:
            if path == exc or exc in path.parents:
                return True
        return False

    def get_file_size(self, f: Path) -> int:
        try:
            return f.stat().st_size
        except Exception:
            return 0

    def _txt_companion_path(self, p: Path) -> Path:
        return p.with_suffix(p.suffix + ".txt")

    def _maybe_write_txt_companion(self, p: Path) -> None:
        if self.output_format != "xml" or self.txt_mode != "copy":
            return
        try:
            self.check_stop()
            src = p
            dst = self._txt_companion_path(p)
            with src.open("rb") as rf, dst.open("wb") as wf:
                while True:
                    self.check_stop()
                    chunk = rf.read(1024 * 1024)
                    if not chunk:
                        break
                    wf.write(chunk)
            self.log(f"    -> Wrote companion: {dst.name}")
        except Exception as e:
            self.log(f"    (warn) Could not write txt companion for {p.name}: {e}")

    def _normalize_volume_filename(self, name: str) -> str:
        """
        Input base naming uses .xml convention; normalize to final extension.
        """
        base = name
        for suf in (".xml.txt", ".xml", ".txt", ".md"):
            if base.lower().endswith(suf):
                base = base[: -len(suf)]
                break

        if self.output_format == "xml":
            fname = base + ".xml"
            if self.txt_mode == "only":
                return fname + ".txt"
            return fname

        # text format
        return base + ".txt"

    def _index_filename(self) -> str:
        if self.output_format == "xml":
            if self.txt_mode == "only":
                return "Index.xml.txt"
            return "Index.xml"
        return "Index.txt"

    def _bundle_extension(self) -> str:
        # bundles are upload-helper text
        if self.output_format == "xml":
            return ".xml.txt"
        return ".txt"

    # -----------------------------
    # File collection
    # -----------------------------

    def collect_files_in_folder(self, folder_path: Path, recursive: bool = True) -> List[Path]:
        valid_files: List[Path] = []

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

                full_dir_path = current_dir / d
                # smartignore directory check
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

            dirnames[:] = safe_dirs

            for f in filenames:
                fpath = current_dir / f
                ext = fpath.suffix.lower()

                if f in ALWAYS_IGNORE_FILES:
                    continue
                if ext in ALWAYS_IGNORE_EXT:
                    continue

                # smartignore file check
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

    # -----------------------------
    # Parallel File Processing
    # -----------------------------

    def _process_file_content(self, f: Path) -> Optional[Dict[str, Any]]:
        if self.stop_event.is_set():
            return None

        try:
            rel_path = f.relative_to(self.root_dir).as_posix()
            ext = f.suffix.lower()
            is_excluded_path = self.is_custom_excluded(f)

            size_bytes = 0
            line_count = 0
            content = ""
            kind = "source"

            if is_excluded_path:
                if "Names" in self.exclusion_mode:
                    content = ""
                    kind = "list_name_only"
                    size_bytes = 0
                else:
                    size_bytes = self.get_file_size(f)
                    content = ""
                    kind = "metadata_only"
            else:
                size_bytes = self.get_file_size(f)
                if size_bytes > OVERSIZE_BYTES:
                    content = f"SKIPPED_OVERSIZED: {size_bytes} bytes"
                    kind = "oversized"
                else:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    line_count = len(content.splitlines())
                    kind = "markdown" if ext == ".md" else "source"

            if kind in ("source", "markdown") and content and size_bytes <= OVERSIZE_BYTES:
                file_id = short_sha1(rel_path + "\n" + content)
            else:
                file_id = short_sha1(f"{rel_path}\n{size_bytes}\n{kind}")

            chunks = None
            if kind in ("source", "markdown") and content and line_count > self.CHUNK_MAX_LINES:
                raw_chunks = chunk_lines_keepends(content, self.CHUNK_MAX_LINES)
                chunks = []
                for c in raw_chunks:
                    chunk_id = f"{file_id}:{c['start_line']}-{c['end_line']}"
                    chunks.append(
                        {
                            "id": chunk_id,
                            "start_line": int(c["start_line"]),
                            "end_line": int(c["end_line"]),
                            "text": c["text"],
                        }
                    )
                content = ""

            return {
                "rel_path": rel_path,
                "ext": ext,
                "size_bytes": int(size_bytes),
                "line_count": int(line_count),
                "kind": kind,
                "file_id": file_id,
                "chunks": chunks,
                "content": content,
            }

        except Exception as e:
            return {
                "rel_path": f.name,
                "ext": "",
                "size_bytes": 0,
                "line_count": 0,
                "kind": "error",
                "file_id": short_sha1(f.name),
                "chunks": None,
                "content": f"Error: {e}",
            }

    # -----------------------------
    # Writers (TEXT default, XML optional)
    # -----------------------------

    def write_volume(self, filename: str, files: List[Path], title: str, nav_context: dict) -> Optional[dict]:
        if self.output_format == "xml":
            return self.write_volume_xml(filename, files, title, nav_context)
        return self.write_volume_text(filename, files, title, nav_context)

    def _collect_file_data_parallel(self, files: List[Path], log_prefix_filename: str) -> tuple[list[dict], float]:
        total_size = 0
        self.log(f"-> Processing {log_prefix_filename} ({len(files)} files)...")

        max_workers = min(50, len(files) + 1)
        file_data_list: List[Dict[str, Any]] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(self._process_file_content, files)
            for res in results:
                self.check_stop()
                if res is None:
                    continue
                file_data_list.append(res)
                total_size += int(res["size_bytes"])

        size_mb = total_size / (1024 * 1024)
        return file_data_list, size_mb

    def write_volume_text(self, filename: str, files: List[Path], title: str, nav_context: dict) -> Optional[dict]:
        if not files:
            return None
        self.check_stop()

        out_path = self.output_dir / filename

        try:
            files.sort(key=lambda p: p.relative_to(self.root_dir).as_posix().lower())
        except Exception:
            files.sort(key=lambda p: p.name.lower())

        file_data_list, size_mb = self._collect_file_data_parallel(files, filename)

        try:
            self.log("    Writing TEXT to disk...")
            with out_path.open("w", encoding="utf-8", errors="replace") as out:
                out.write("==== VOLUME META ====\n")
                out.write(f"generated_at: {datetime.now().isoformat()}\n")
                out.write(f"title: {title}\n")
                out.write(f"root_dir: {self.root_dir}\n")
                out.write(f"file_count: {len(files)}\n")
                out.write(f"total_size_mb: {round(size_mb, 4)}\n")
                if nav_context.get("home_file"):
                    out.write(f"home: {nav_context['home_file']}\n")
                if nav_context.get("prev_file"):
                    out.write(f"prev_volume: {nav_context['prev_file']}\n")
                if nav_context.get("next_file"):
                    out.write(f"next_volume: {nav_context['next_file']}\n")
                out.write(f"prev_title: {nav_context.get('prev_title','')}\n")
                out.write(f"next_title: {nav_context.get('next_title','')}\n")
                out.write(f"short_title: {nav_context.get('short_title','')}\n")

                out.write("\n==== FILE_INDEX ====\n")
                for f_data in file_data_list:
                    chunks_count = len(f_data["chunks"]) if f_data.get("chunks") else 0
                    out.write(
                        "ENTRY "
                        f"id={f_data.get('file_id','')} "
                        f'path="{f_data["rel_path"]}" '
                        f"kind={f_data['kind']} "
                        f"size={f_data['size_bytes']} "
                        f"lines={f_data['line_count']} "
                        f"chunks={chunks_count}\n"
                    )

                out.write("\n==== FILES ====\n")
                for f_data in file_data_list:
                    chunks = f_data.get("chunks") or []
                    out.write(
                        "\n----- FILE BEGIN -----\n"
                        f'path="{f_data["rel_path"]}"\n'
                        f"id={f_data.get('file_id','')}\n"
                        f"kind={f_data['kind']}\n"
                        f"size={f_data['size_bytes']}\n"
                        f"lines={f_data['line_count']}\n"
                        f"chunks={len(chunks)}\n"
                    )
                    if chunks:
                        for c in chunks:
                            out.write(
                                "\n--- CHUNK BEGIN ---\n"
                                f"id={c['id']}\n"
                                f"start={c['start_line']}\n"
                                f"end={c['end_line']}\n"
                                "----\n"
                            )
                            out.write(c["text"])
                            if not c["text"].endswith("\n"):
                                out.write("\n")
                            out.write("--- CHUNK END ---\n")
                    else:
                        out.write("----\n")
                        out.write(f_data["content"])
                        if f_data["content"] and not f_data["content"].endswith("\n"):
                            out.write("\n")
                    out.write("----- FILE END -----\n")

            contained_files = [entry["rel_path"] for entry in file_data_list]
            return {
                "filename": filename,
                "title": title,
                "size_mb": size_mb,
                "file_count": len(files),
                "short_title": nav_context.get("short_title", title),
                "contained_files": contained_files,
            }
        except Exception as e:
            self.log(f"Error writing TEXT file {filename}: {e}")
            return None

    def write_volume_xml(self, filename: str, files: List[Path], title: str, nav_context: dict) -> Optional[dict]:
        if not files:
            return None
        self.check_stop()

        out_path = self.output_dir / filename

        try:
            files.sort(key=lambda p: p.relative_to(self.root_dir).as_posix().lower())
        except Exception:
            files.sort(key=lambda p: p.name.lower())

        file_data_list, size_mb = self._collect_file_data_parallel(files, filename)

        try:
            self.log("    Writing XML to disk...")
            with out_path.open("w", encoding="utf-8") as out:
                out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                out.write("<volume>\n")

                out.write("  <meta>\n")
                out.write(f"    <generated_at>{datetime.now().isoformat()}</generated_at>\n")
                out.write(f"    <title>{escape_xml_text(title)}</title>\n")
                out.write(f"    <root_dir>{escape_xml_text(str(self.root_dir))}</root_dir>\n")
                out.write(f"    <file_count>{len(files)}</file_count>\n")
                out.write(f"    <total_size_mb>{round(size_mb, 4)}</total_size_mb>\n")

                if nav_context.get("home_file"):
                    out.write(f'    <home>{escape_xml_text(nav_context["home_file"])}</home>\n')
                if nav_context.get("next_file"):
                    out.write(f'    <next_volume>{escape_xml_text(nav_context["next_file"])}</next_volume>\n')
                if nav_context.get("prev_file"):
                    out.write(f'    <prev_volume>{escape_xml_text(nav_context["prev_file"])}</prev_volume>\n')

                out.write(f'    <prev_title>{escape_xml_text(nav_context.get("prev_title", ""))}</prev_title>\n')
                out.write(f'    <next_title>{escape_xml_text(nav_context.get("next_title", ""))}</next_title>\n')
                out.write(f'    <short_title>{escape_xml_text(nav_context.get("short_title", ""))}</short_title>\n')
                out.write("  </meta>\n")

                out.write("  <file_index>\n")
                for f_data in file_data_list:
                    p = escape_xml_attr(f_data["rel_path"])
                    k = escape_xml_attr(f_data["kind"])
                    fid = escape_xml_attr(f_data.get("file_id", ""))
                    chunks_count = len(f_data["chunks"]) if f_data.get("chunks") else 0
                    out.write(
                        f'    <entry id="{fid}" path="{p}" kind="{k}" '
                        f'size="{f_data["size_bytes"]}" lines="{f_data["line_count"]}" '
                        f'chunks="{chunks_count}" />\n'
                    )
                out.write("  </file_index>\n")

                out.write("  <files>\n")
                for f_data in file_data_list:
                    path_attr = escape_xml_attr(f_data["rel_path"])
                    kind_attr = escape_xml_attr(f_data["kind"])
                    file_id_attr = escape_xml_attr(f_data.get("file_id", ""))

                    if f_data.get("chunks"):
                        out.write(
                            f'    <file id="{file_id_attr}" path="{path_attr}" size="{f_data["size_bytes"]}" '
                            f'lines="{f_data["line_count"]}" kind="{kind_attr}">\n'
                        )
                        for c in f_data["chunks"]:
                            cid = escape_xml_attr(c["id"])
                            sline = int(c["start_line"])
                            eline = int(c["end_line"])
                            out.write(
                                f'      <chunk id="{cid}" start="{sline}" end="{eline}">{wrap_cdata(c["text"])}</chunk>\n'
                            )
                        out.write("    </file>\n")
                    else:
                        out.write(
                            f'    <file id="{file_id_attr}" path="{path_attr}" size="{f_data["size_bytes"]}" '
                            f'lines="{f_data["line_count"]}" kind="{kind_attr}">{wrap_cdata(f_data["content"])}</file>\n'
                        )

                out.write("  </files>\n")
                out.write("</volume>\n")

            self._maybe_write_txt_companion(out_path)

            contained_files = [entry["rel_path"] for entry in file_data_list]
            return {
                "filename": filename,
                "title": title,
                "size_mb": size_mb,
                "file_count": len(files),
                "short_title": nav_context.get("short_title", title),
                "contained_files": contained_files,
            }

        except Exception as e:
            self.log(f"Error writing XML file {filename}: {e}")
            return None

    # -----------------------------
    # Bundles + Manifest (file-count limits)
    # -----------------------------

    def _classify_volume_group(self, meta: dict) -> str:
        s = " ".join(
            [
                str(meta.get("short_title", "")),
                str(meta.get("title", "")),
                str(meta.get("filename", "")),
            ]
        ).lower()

        if any(k in s for k in ("app", "frontend", "ui", "client", "schema", "schemas", "core")):
            return "CORE"
        if any(k in s for k in ("doc", "docs", "readme", "guide", "manual", "tool", "tools", "script", "scripts")):
            return "DOCS_TOOLS"
        return "TESTS_OTHERS"

    def write_grouped_bundles(self, generated_meta: List[dict]) -> Dict[str, str]:
        if not self.create_grouped_bundles or not generated_meta:
            return {}

        self.check_stop()
        self.log("Phase 3: Writing grouped bundles (upload helpers)...")

        groups: Dict[str, List[dict]] = {"CORE": [], "DOCS_TOOLS": [], "TESTS_OTHERS": []}
        for meta in generated_meta:
            self.check_stop()
            g = self._classify_volume_group(meta)
            groups.setdefault(g, []).append(meta)

        artifacts: Dict[str, str] = {}
        ext = self._bundle_extension()

        for gname, metas in groups.items():
            self.check_stop()
            metas = [m for m in metas if m.get("filename")]
            if not metas:
                continue

            out_name = f"REPO_{gname}{ext}"
            out_path = self.output_dir / out_name

            try:
                with out_path.open("w", encoding="utf-8", errors="replace") as out:
                    for m in metas:
                        self.check_stop()
                        vol_file = self.output_dir / m["filename"]
                        out.write("\n\n")
                        out.write(f"===== BEGIN VOLUME {m['filename']} :: {m.get('title','')} =====\n")
                        with vol_file.open("r", encoding="utf-8", errors="replace") as vf:
                            for line in vf:
                                self.check_stop()
                                out.write(line)
                        out.write(f"\n===== END VOLUME {m['filename']} =====\n")
                artifacts[gname] = out_name
                self.log(f"    -> Created bundle: {out_name}")
            except Exception as e:
                self.log(f"    (warn) Could not create bundle {out_name}: {e}")

        manifest_name = "REPO_MANIFEST_GROUPED.md"
        manifest_path = self.output_dir / manifest_name

        try:
            with manifest_path.open("w", encoding="utf-8") as mf:
                mf.write("# Repo bundle (grouped for file upload limits)\n\n")
                mf.write("## Upload these (recommended)\n")
                mf.write(f"- `{manifest_name}`\n")
                for k in ("CORE", "DOCS_TOOLS", "TESTS_OTHERS"):
                    if k in artifacts:
                        mf.write(f"- `{artifacts[k]}`\n")

                mf.write("\n## How to navigate\n")
                mf.write("1) Search in this manifest for the file path you need.\n")
                mf.write("2) Note the `volume` and `bundle`.\n")
                if self.output_format == "xml":
                    mf.write("3) Open the bundle file and search for `<file path=\"...\">`.\n")
                else:
                    mf.write("3) Open the bundle file and search for `path=\"...\"` under `----- FILE BEGIN -----`.\n")
                mf.write("4) Read the relevant content / chunk(s).\n\n")

                mf.write("## File locator index (path → volume → bundle)\n")
                mf.write("```text\n")
                for meta in generated_meta:
                    self.check_stop()
                    vol = meta.get("filename", "")
                    grp = self._classify_volume_group(meta)
                    bundle = artifacts.get(grp, "")
                    for p in meta.get("contained_files", []) or []:
                        self.check_stop()
                        mf.write(f"{p}\tvolume={vol}\tbundle={bundle or '(none)'}\n")
                mf.write("```\n")

            artifacts["manifest"] = manifest_name
            self.log(f"    -> Created manifest: {manifest_name}")
        except Exception as e:
            self.log(f"    (warn) Could not create manifest {manifest_name}: {e}")

        return artifacts

    # -----------------------------
    # Index
    # -----------------------------

    def write_index(self, index_filename: str, repo_name: str, instructions_filename: str, generated_meta: List[dict]) -> None:
        index_path = self.output_dir / index_filename
        should_write = True

        if index_path.exists():
            self.log(f"Index file {index_filename} already exists.")
            if not self.ask_overwrite(index_filename):
                should_write = False
                self.log("Skipping index.")
            else:
                self.log("Overwriting index.")

        if not should_write:
            return

        if self.output_format == "xml":
            with index_path.open("w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write("<index>\n")
                f.write(f"  <repo_name>{escape_xml_text(repo_name)}</repo_name>\n")
                f.write(f"  <root_dir>{escape_xml_text(str(self.root_dir))}</root_dir>\n")
                f.write(f"  <generated_at>{datetime.now().isoformat()}</generated_at>\n")
                f.write(f"  <instructions_file>{escape_xml_text(instructions_filename)}</instructions_file>\n")
                f.write("  <volumes>\n")
                for meta in generated_meta:
                    f.write("    <volume>\n")
                    f.write(f"      <filename>{escape_xml_text(meta['filename'])}</filename>\n")
                    f.write(f"      <title>{escape_xml_text(meta['title'])}</title>\n")
                    f.write(f"      <short_title>{escape_xml_text(meta.get('short_title',''))}</short_title>\n")
                    f.write(f"      <size_mb>{round(meta['size_mb'], 4)}</size_mb>\n")
                    f.write(f"      <file_count>{meta['file_count']}</file_count>\n")
                    f.write("      <contained_files>\n")
                    for cfile in meta["contained_files"]:
                        f.write(f"        <file>{escape_xml_text(cfile)}</file>\n")
                    f.write("      </contained_files>\n")
                    f.write("    </volume>\n")
                f.write("  </volumes>\n")
                f.write("</index>\n")

            self.log(f"-> Created Master Index: {index_filename}")
            self._maybe_write_txt_companion(index_path)
            return

        # text index
        with index_path.open("w", encoding="utf-8", errors="replace") as out:
            out.write("==== MASTER INDEX ====\n")
            out.write(f"repo_name: {repo_name}\n")
            out.write(f"root_dir: {self.root_dir}\n")
            out.write(f"generated_at: {datetime.now().isoformat()}\n")
            out.write(f"instructions_file: {instructions_filename}\n\n")
            out.write("==== VOLUMES ====\n")
            for meta in generated_meta:
                out.write(
                    f"- filename={meta.get('filename','')} | title={meta.get('title','')} | "
                    f"short_title={meta.get('short_title','')} | files={meta.get('file_count',0)} | "
                    f"size_mb={round(meta.get('size_mb',0.0),4)}\n"
                )
            out.write("\n==== FILE LOCATOR (path -> volume) ====\n")
            for meta in generated_meta:
                vol = meta.get("filename", "")
                for p in meta.get("contained_files", []) or []:
                    out.write(f"{p}\tvolume={vol}\n")

        self.log(f"-> Created Master Index: {index_filename}")

    # -----------------------------
    # Instructions File
    # -----------------------------

    def write_instructions_file(
        self,
        index_filename: Optional[str],
        generated_meta: List[dict],
        bundle_artifacts: Optional[Dict[str, str]] = None,
    ) -> None:
        self.check_stop()

        out_path = self.output_dir / self.INSTRUCTIONS_FILENAME
        should_write = True

        if out_path.exists():
            self.log(f"Instructions file {self.INSTRUCTIONS_FILENAME} already exists.")
            if not self.ask_overwrite(self.INSTRUCTIONS_FILENAME):
                should_write = False
                self.log("Skipping instructions file.")
            else:
                self.log("Overwriting instructions file.")

        if not should_write:
            return

        volumes_list = "\n".join([f"- {m.get('filename','')}  —  {m.get('title','')}" for m in generated_meta])

        if index_filename:
            next_step = f"1) Open `{index_filename}` (master index) and use it to locate the right volume.\n"
        else:
            next_step = "1) No master index was generated. Use the volume files directly.\n"

        smartignore_block = ""
        if self.smartignore_patterns:
            smartignore_block = (
                "\n## .smartignore\n"
                f"- Found `{self.smartignore_file.name}` with {len(self.smartignore_patterns)} pattern(s).\n"
                f"- Exclusion enabled: {self.use_smartignore_exclude}\n"
                f"- Smartignore index enabled: {self.create_smartignore_paths_index}\n"
                f"- Smartignore paths index file: `SmartignorePathsIndex.txt` (if enabled)\n"
            )

        bundles_block = ""
        if bundle_artifacts:
            lines = []
            manifest = bundle_artifacts.get("manifest")
            if manifest:
                lines.append(f"- Grouped manifest: `{manifest}`")
            for k in ("CORE", "DOCS_TOOLS", "TESTS_OTHERS"):
                if k in bundle_artifacts:
                    lines.append(f"- Bundle {k}: `{bundle_artifacts[k]}`")
            if lines:
                bundles_block = "\n## Upload-helper bundles (optional)\n" + "\n".join(lines) + "\n"

        format_notes = ""
        if self.output_format == "xml":
            format_notes = "- Use `<file_index>` then `<file path=\"...\">`.\n"
        else:
            format_notes = (
                "- Use `==== FILE_INDEX ====` first (lines starting with `ENTRY`).\n"
                "- Then jump to `----- FILE BEGIN -----` with matching `path=\"...\"`.\n"
                "- For big files, prefer `--- CHUNK BEGIN ---` blocks.\n"
            )

        text = f"""# START HERE — Instructions for AI

You are given a repository codedump split into multiple volume files.

## Goal
Answer questions by opening the minimum necessary content.

## Format notes
{format_notes}
{smartignore_block}
## How to navigate this dump
{next_step}2) Pick the relevant volume file.
3) Use the per-volume index section to locate the path.
4) Read the exact file content (or required chunks only).
5) Expand cautiously (imports / calls / routes), 1–2 hops unless needed.

## Rules
- Do NOT try to read the entire dump.
- Prefer docs/diagrams/indices if present.
- When answering, cite file paths and the volume filename.

## Files
- Instructions (this): `{self.INSTRUCTIONS_FILENAME}`
- Master index: `{index_filename or "(not generated)"}`
- Volumes:
{volumes_list}
{bundles_block}
"""
        with out_path.open("w", encoding="utf-8") as f:
            f.write(text)

        self.log(f"-> Created Instructions File: {self.INSTRUCTIONS_FILENAME}")

    # -----------------------------
    # Main
    # -----------------------------

    def run(self) -> None:
        try:
            self.log(f"Scanning structure of: {self.root_dir}")

            repo_name = self.root_dir.name
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name_pattern = f"{repo_name}_{ts}"

            run_folder_name = f"{base_name_pattern}_Dump"
            self.output_dir = (self.output_dir / run_folder_name).resolve()
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"Output Target: {self.output_dir}")

            # Auto-exclude output folder from dumps
            try:
                _ = self.output_dir.relative_to(self.root_dir)
                if self.output_dir not in self.custom_excludes:
                    self.custom_excludes.append(self.output_dir)
            except Exception:
                pass

            self.check_stop()
            self.log("Phase 1: Finding Files...")
            root_files = self.collect_files_in_folder(self.root_dir, recursive=False)

            top_level_items: List[Path] = []
            for item in os.listdir(self.root_dir):
                full_path = (self.root_dir / item).resolve()
                if full_path.is_dir():
                    if item in ALWAYS_IGNORE_DIRS:
                        continue

                    # smartignore dir decision at top level too
                    try:
                        rel_dir = full_path.relative_to(self.root_dir).as_posix()
                    except Exception:
                        rel_dir = full_path.as_posix()

                    if self.smartignore_patterns:
                        m = self._smartignore_match(rel_dir, is_dir=True)
                        if m:
                            self._record_smartignore_match(rel_dir, is_dir=True)
                            if self.use_smartignore_exclude:
                                continue

                    if self.gitignore.match_ignore(full_path, is_dir=True):
                        continue

                    if self.is_custom_excluded(full_path):
                        try:
                            rel = full_path.relative_to(self.root_dir)
                        except Exception:
                            rel = full_path
                        self.tracked_custom_exclusions.append(str(rel) + " (DIR)")
                        if self.exclusion_mode == "Fully Exclude":
                            continue

                    top_level_items.append(full_path)

            analyzed_folders: List[Dict[str, Any]] = []
            for i, folder in enumerate(top_level_items):
                self.check_stop()
                if i % 5 == 0:
                    self.log(f"    Scanning folder: {folder.name}...")

                f_files = self.collect_files_in_folder(folder, recursive=True)
                if f_files:
                    size = 0 if self.is_custom_excluded(folder) else sum(self.get_file_size(f) for f in f_files)
                    analyzed_folders.append({"name": folder.name, "files": f_files, "size": size})

            analyzed_folders.sort(key=lambda x: x["size"], reverse=True)

            planned_dumps: List[Dict[str, Any]] = []
            index_filename = self._index_filename()
            instructions_filename = self.INSTRUCTIONS_FILENAME

            # TOTAL desired outputs for: volumes + (index?) + instructions
            available_slots = self.max_output_files
            available_slots -= 1  # instructions
            if self.create_index:
                available_slots -= 1  # index
            if available_slots < 1:
                available_slots = 1
                self.log("Note: max_output_files is very small; forcing at least 1 volume.")

            if root_files and available_slots > 0:
                available_slots -= 1
                fname = self._normalize_volume_filename(f"{base_name_pattern}_01_ROOT.xml")
                planned_dumps.append(
                    {"filename": fname, "files": root_files, "title": "ROOT FILES", "short_title": "Root"}
                )

            start_idx = len(planned_dumps) + 1

            if len(analyzed_folders) <= available_slots:
                for i, folder in enumerate(analyzed_folders):
                    idx = start_idx + i
                    fname = self._normalize_volume_filename(f"{base_name_pattern}_{idx:02d}_{folder['name']}.xml")
                    planned_dumps.append(
                        {
                            "filename": fname,
                            "files": folder["files"],
                            "title": f"FOLDER: {folder['name']}",
                            "short_title": folder["name"],
                        }
                    )
            else:
                distinct_count = max(0, available_slots - 1)
                top_folders = analyzed_folders[:distinct_count]
                remaining_folders = analyzed_folders[distinct_count:]

                for i, folder in enumerate(top_folders):
                    idx = start_idx + i
                    fname = self._normalize_volume_filename(f"{base_name_pattern}_{idx:02d}_{folder['name']}.xml")
                    planned_dumps.append(
                        {
                            "filename": fname,
                            "files": folder["files"],
                            "title": f"FOLDER: {folder['name']}",
                            "short_title": folder["name"],
                        }
                    )

                others_files: List[Path] = []
                for folder in remaining_folders:
                    others_files.extend(folder["files"])

                if others_files:
                    fname = self._normalize_volume_filename(f"{base_name_pattern}_99_OTHERS.xml")
                    planned_dumps.append(
                        {
                            "filename": fname,
                            "files": others_files,
                            "title": "OTHERS (Misc Folders)",
                            "short_title": "Others",
                        }
                    )

            self.log(f"Phase 2: Writing {len(planned_dumps)} volumes...")
            generated_meta: List[dict] = []

            for i, dump in enumerate(planned_dumps):
                self.check_stop()
                prev_d = planned_dumps[i - 1] if i > 0 else None
                next_d = planned_dumps[i + 1] if i < len(planned_dumps) - 1 else None

                nav = {
                    "home_file": instructions_filename,
                    "prev_file": prev_d["filename"] if prev_d else None,
                    "next_file": next_d["filename"] if next_d else None,
                    "prev_title": prev_d["short_title"] if prev_d else "",
                    "next_title": next_d["short_title"] if next_d else "",
                    "short_title": dump["short_title"],
                }

                meta = self.write_volume(dump["filename"], dump["files"], dump["title"], nav)
                if meta:
                    generated_meta.append(meta)

            if self.create_index:
                self.write_index(index_filename, repo_name, instructions_filename, generated_meta)

            bundle_artifacts = self.write_grouped_bundles(generated_meta)

            # smartignore index file (paths matched)
            self.write_smartignore_paths_index()

            # instructions last
            self.write_instructions_file(
                index_filename=index_filename if self.create_index else None,
                generated_meta=generated_meta,
                bundle_artifacts=bundle_artifacts if bundle_artifacts else None,
            )

            if self.tracked_custom_exclusions:
                report_path = self.output_dir / "ExcludedFilesReport.txt"
                try:
                    unique_exclusions = sorted(set(self.tracked_custom_exclusions))
                    with report_path.open("w", encoding="utf-8") as rf:
                        rf.write(f" EXCLUDED FILES REPORT - {datetime.now()}\n")
                        rf.write(" Excluded by 'Custom Path Exclusions'.\n\n")
                        for line in unique_exclusions:
                            rf.write(f"{line}\n")
                    self.log("-> Created Exclusion Report.")
                except Exception as e:
                    self.log(f"Could not write exclusion report: {e}")

            self.log(f"\nSUCCESS! Completed in:\n{self.output_dir}")

        except InterruptedError:
            self.log("\n!!! PROCESS STOPPED BY USER !!!")
        except Exception:
            self.last_exception_traceback = traceback.format_exc()
            self.log("ERROR: Unhandled exception in DumpWorker.")
            self.log(self.last_exception_traceback)