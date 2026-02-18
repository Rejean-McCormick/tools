# worker.py
from __future__ import annotations

import concurrent.futures
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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

            # Stable-ish ID: content-based when we have real text; fallback otherwise.
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
                # Avoid duplicating whole file in output once chunked
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

    def write_volume_xml(self, filename: str, files: List[Path], title: str, nav_context: dict) -> Optional[dict]:
        if not files:
            return None
        self.check_stop()

        out_path = self.output_dir / filename

        try:
            files.sort(key=lambda p: p.relative_to(self.root_dir).as_posix().lower())
        except Exception:
            files.sort(key=lambda p: p.name.lower())

        total_size = 0
        self.log(f"-> Processing {filename} ({len(files)} files)...")

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
    # Instructions File
    # -----------------------------

    def write_instructions_file(self, index_filename: Optional[str], generated_meta: List[dict]) -> None:
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

        text = f"""# START HERE — Instructions for AI

You are given a repository codedump split into multiple XML volume files.

## Goal
Answer questions by opening the minimum necessary files, starting from indexes and entry points.

## How to navigate this dump
{next_step}2) For a chosen volume, use `<file_index>` first to find candidate paths (and see `chunks="N"`).
3) Only then open the matching `<file path="...">` blocks.
4) If `chunks="N"` is > 0, prefer reading only the needed `<chunk start=".." end="..">` blocks.
5) Expand cautiously (imports / calls / routes), 1–2 hops unless needed.

## Notes on fidelity
- File contents are stored in CDATA blocks (raw code preserved).
- XML is kept valid even if code contains `]]>` (it is split safely).

## Rules
- Do NOT try to read the entire dump.
- Prefer any docs/diagrams/indices if present.
- Treat binary-like content as non-text.
- When answering, cite file paths and the volume XML filename.

## Files
- Instructions (this): `{self.INSTRUCTIONS_FILENAME}`
- Master index: `{index_filename or "(not generated)"}`
- Volumes:
{volumes_list}
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
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            base_name_pattern = f"{repo_name}_{ts}"

            run_folder_name = f"{base_name_pattern}_XMLDump"
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

            available_slots = self.max_output_files
            planned_dumps: List[Dict[str, Any]] = []
            index_filename = "Index.xml"
            instructions_filename = self.INSTRUCTIONS_FILENAME

            if root_files:
                available_slots -= 1
                fname = f"{base_name_pattern}_01_ROOT.xml"
                planned_dumps.append(
                    {"filename": fname, "files": root_files, "title": "ROOT FILES", "short_title": "Root"}
                )

            start_idx = len(planned_dumps) + 1

            if len(analyzed_folders) <= available_slots:
                for i, folder in enumerate(analyzed_folders):
                    idx = start_idx + i
                    fname = f"{base_name_pattern}_{idx:02d}_{folder['name']}.xml"
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
                    fname = f"{base_name_pattern}_{idx:02d}_{folder['name']}.xml"
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
                    fname = f"{base_name_pattern}_99_OTHERS.xml"
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

                meta = self.write_volume_xml(dump["filename"], dump["files"], dump["title"], nav)
                if meta:
                    generated_meta.append(meta)

            if self.create_index:
                index_path = self.output_dir / index_filename
                should_write = True

                if index_path.exists():
                    self.log(f"Index file {index_filename} already exists.")
                    if not self.ask_overwrite(index_filename):
                        should_write = False
                        self.log("Skipping index.")
                    else:
                        self.log("Overwriting index.")

                if should_write:
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

            self.write_instructions_file(
                index_filename=index_filename if self.create_index else None,
                generated_meta=generated_meta,
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
