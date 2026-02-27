# worker/dump_worker.py
from __future__ import annotations

import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..constants import (
    ALWAYS_IGNORE_DIRS,
    CHUNK_MAX_LINES,
    INSTRUCTIONS_FILENAME,
    OVERSIZE_BYTES,
)
from ..gitignore_engine import GitIgnoreEngine

from .bundles import BundleWriter
from .file_collection import FileCollectionMixin
from .file_processing import FileProcessor
from .index import IndexWriterMixin
from .instructions import InstructionsWriter
from .smartignore import SmartIgnore
from .writers_text import WritersTextMixin
from .writers_xml import (
    index_filename_xml,
    maybe_write_txt_companion,
    normalize_volume_filename_xml,
    write_volume_xml,
)


class DumpWorker(FileCollectionMixin, WritersTextMixin, IndexWriterMixin):
    """
    Orchestrator for repository dumps.

    Output formats:
      - output_format="text": structured plain-text volumes (DEFAULT)
      - output_format="xml" : XML volumes (optional)

    XML txt_mode:
      - "none": .xml only
      - "copy": .xml and also .xml.txt companions (for indexing)
      - "only": .xml.txt only (no .xml)

    Upload helper:
      - create_single_upload_doc=True => one combined file: "Doc<parent_folder><ext>"
      - create_grouped_bundles=True  => legacy grouped bundles + manifest
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
        stop_event: Any,
        *,
        output_format: str = "text",
        txt_mode: str = "copy",
        # Legacy option (kept for backward compatibility)
        create_grouped_bundles: bool = False,
        # Preferred option (single combined upload helper doc)
        create_single_upload_doc: Optional[bool] = None,
        upload_doc_prefix: str = "Doc",
        # .smartignore options
        use_smartignore_exclude: bool = False,
        create_smartignore_paths_index: bool = False,
    ):
        self.root_dir = Path(root_dir).resolve()
        self.output_dir = Path(output_dir).resolve()

        self.max_output_files = max(2, int(max_output_files))
        self.ignore_txt = bool(ignore_txt)
        self.ignore_md = bool(ignore_md)
        self.create_index = bool(create_index)
        self.custom_excludes = [Path(p).resolve() for p in (custom_excludes or [])]
        self.exclusion_mode = str(exclusion_mode or "")

        self.log = log_callback
        self.ask_overwrite = overwrite_callback
        self.stop_event = stop_event

        self.tracked_custom_exclusions: List[str] = []

        # Keep legacy attribute names used by older code
        self.instructions_filename = INSTRUCTIONS_FILENAME
        self.INSTRUCTIONS_FILENAME = self.instructions_filename
        self.chunk_max_lines = int(CHUNK_MAX_LINES)
        self.CHUNK_MAX_LINES = self.chunk_max_lines
        self.oversize_bytes = int(OVERSIZE_BYTES)

        # output format
        self.output_format = (output_format or "text").strip().lower()
        if self.output_format not in ("text", "xml"):
            self.output_format = "text"

        # xml txt_mode
        self.txt_mode = (txt_mode or "none").strip().lower()
        if self.txt_mode not in ("none", "copy", "only"):
            self.txt_mode = "copy"

        # Upload helper mode resolution:
        # - New GUI passes create_single_upload_doc explicitly.
        # - Old GUI uses create_grouped_bundles checkbox: treat that as "create upload helper" and default to single doc.
        if create_single_upload_doc is None:
            self.create_single_upload_doc = bool(create_grouped_bundles)
            self.create_grouped_bundles = False  # legacy grouped output disabled by default
        else:
            self.create_single_upload_doc = bool(create_single_upload_doc)
            self.create_grouped_bundles = bool(create_grouped_bundles)

        self.upload_doc_prefix = (upload_doc_prefix or "Doc").strip() or "Doc"

        # .smartignore
        self.use_smartignore_exclude = bool(use_smartignore_exclude)
        self.create_smartignore_paths_index = bool(create_smartignore_paths_index)
        self.smartignore = SmartIgnore(
            root_dir=self.root_dir,
            log=self.log,
            use_smartignore_exclude=self.use_smartignore_exclude,
            create_smartignore_paths_index=self.create_smartignore_paths_index,
        )
        self.smartignore.load()
        # Compat attributes expected by FileCollectionMixin
        self.smartignore_patterns = self.smartignore.patterns
        self.smartignore_file = self.smartignore.smartignore_file

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

        self.file_processor = FileProcessor(
            root_dir=self.root_dir,
            chunk_max_lines=self.chunk_max_lines,
            oversize_bytes=self.oversize_bytes,
            stop_event=self.stop_event,
            is_custom_excluded=self.is_custom_excluded,
            exclusion_mode_getter=lambda: self.exclusion_mode,
            get_file_size=self.get_file_size,
            check_stop=self.check_stop,
        )

    # -----------------------------
    # Core helpers
    # -----------------------------

    def check_stop(self) -> None:
        if getattr(self.stop_event, "is_set", lambda: False)():
            raise InterruptedError("Stopped by user.")

    def is_custom_excluded(self, path: Path) -> bool:
        if not self.custom_excludes:
            return False
        p = Path(path).resolve()
        for exc in self.custom_excludes:
            if p == exc or exc in p.parents:
                return True
        return False

    def get_file_size(self, f: Path) -> int:
        try:
            return int(Path(f).stat().st_size)
        except Exception:
            return 0

    # -----------------------------
    # .smartignore glue for FileCollectionMixin
    # -----------------------------

    def _smartignore_match(self, rel_posix: str, *, is_dir: bool) -> bool:
        return self.smartignore.match(rel_posix, is_dir=is_dir)

    def _record_smartignore_match(self, rel_posix: str, is_dir: bool) -> None:
        if not self.create_smartignore_paths_index:
            return
        self.smartignore.matched_paths.add(rel_posix)
        if is_dir:
            self.smartignore.matched_dirs.add(rel_posix)

    def write_smartignore_paths_index(self) -> None:
        self.smartignore.write_paths_index(output_dir=self.output_dir, check_stop=self.check_stop)

    # -----------------------------
    # Filename helpers
    # -----------------------------

    def _normalize_volume_filename(self, name: str) -> str:
        """
        Normalize a planned volume filename to the correct extension for the current output mode.
        """
        base = str(name or "").strip()
        for suf in (".xml.txt", ".xml", ".txt", ".md"):
            if base.lower().endswith(suf):
                base = base[: -len(suf)]
                break

        if self.output_format == "xml":
            return normalize_volume_filename_xml(base + ".xml", self.txt_mode)

        return base + ".txt"

    def _index_filename(self) -> str:
        if self.output_format == "xml":
            return index_filename_xml(self.txt_mode)
        return "Index.txt"

    def _maybe_write_txt_companion(self, p: Path) -> None:
        # Used by IndexWriterMixin in xml mode.
        if self.output_format != "xml":
            return
        if (self.txt_mode or "").strip().lower() != "copy":
            return
        if Path(p).suffix.lower() != ".xml":
            return
        maybe_write_txt_companion(
            src_xml_path=Path(p),
            txt_mode=self.txt_mode,
            log=self.log,
            check_stop=self.check_stop,
        )

    # -----------------------------
    # File processing glue for WritersTextMixin
    # -----------------------------

    def _process_file_content(self, f: Path) -> Optional[Dict[str, Any]]:
        return self.file_processor.process_file_content(Path(f))

    # -----------------------------
    # Volume writers
    # -----------------------------

    def write_volume(self, filename: str, files: List[Path], title: str, nav_context: dict) -> Optional[dict]:
        if self.output_format == "xml":
            return self.write_volume_xml(filename, files, title, nav_context)
        return self.write_volume_text(filename, files, title, nav_context)

    def write_volume_xml(self, filename: str, files: List[Path], title: str, nav_context: dict) -> Optional[dict]:
        if not files:
            return None

        self.check_stop()

        # Stable ordering (like legacy)
        try:
            files.sort(key=lambda p: p.relative_to(self.root_dir).as_posix().lower())
        except Exception:
            files.sort(key=lambda p: p.name.lower())

        file_data_list, size_mb = self._collect_file_data_parallel(files, filename)
        return write_volume_xml(
            output_dir=self.output_dir,
            root_dir=self.root_dir,
            filename=filename,
            files=files,
            title=title,
            nav_context=nav_context,
            file_data_list=file_data_list,
            size_mb=size_mb,
            txt_mode=self.txt_mode,
            log=self.log,
            check_stop=self.check_stop,
        )

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

            # Auto-exclude output folder from dumps (if inside repo)
            try:
                _ = self.output_dir.relative_to(self.root_dir)
                if self.output_dir not in self.custom_excludes:
                    self.custom_excludes.append(self.output_dir)
            except Exception:
                pass

            # Phase 1: gather files
            self.check_stop()
            self.log("Phase 1: Finding Files.")
            root_files = self.collect_files_in_folder(self.root_dir, recursive=False)

            top_level_items: List[Path] = []
            for item in os.listdir(self.root_dir):
                self.check_stop()

                full_path = (self.root_dir / item).resolve()
                if not full_path.is_dir():
                    continue

                if item in ALWAYS_IGNORE_DIRS:
                    continue

                # smartignore dir decision at top level too
                if self.smartignore.patterns:
                    rel_dir = self.smartignore.rel_posix(full_path)
                    if self.smartignore.should_exclude(rel_dir, is_dir=True):
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
                    self.log(f"    Scanning folder: {folder.name}.")

                f_files = self.collect_files_in_folder(folder, recursive=True)
                if f_files:
                    size = 0 if self.is_custom_excluded(folder) else sum(self.get_file_size(f) for f in f_files)
                    analyzed_folders.append({"name": folder.name, "files": f_files, "size": int(size)})

            analyzed_folders.sort(key=lambda x: int(x.get("size", 0)), reverse=True)

            planned_dumps: List[Dict[str, Any]] = []
            index_filename = self._index_filename()
            instructions_filename = self.instructions_filename

            # TOTAL desired outputs for: volumes + (index?) + instructions
            available_slots = int(self.max_output_files)
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

            self.log(f"Phase 2: Writing {len(planned_dumps)} volumes.")
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

            # Phase 3: upload helper (single doc preferred)
            bundle_artifacts: Dict[str, str] = {}
            upload_doc_filename: Optional[str] = None
            upload_helper_file_for_index: Optional[str] = None

            if self.create_single_upload_doc or self.create_grouped_bundles:
                self.check_stop()
                bw = BundleWriter(
                    output_dir=self.output_dir,
                    output_format=self.output_format,
                    create_grouped_bundles=self.create_grouped_bundles,
                    check_stop=self.check_stop,
                    log=self.log,
                    create_single_upload_doc=self.create_single_upload_doc,
                    repo_root=self.root_dir,
                    upload_doc_prefix=self.upload_doc_prefix,
                )
                bundle_artifacts = bw.write_upload_helper_artifacts(generated_meta) or {}

                upload_doc_filename = bundle_artifacts.get("single")
                if upload_doc_filename:
                    upload_helper_file_for_index = upload_doc_filename
                else:
                    # Legacy: point index at manifest if available
                    upload_helper_file_for_index = bundle_artifacts.get("manifest")

            # Index
            if self.create_index:
                self.write_index(
                    index_filename,
                    repo_name,
                    instructions_filename,
                    generated_meta,
                    upload_helper_file=upload_helper_file_for_index,
                )

            # smartignore index file (paths matched)
            self.write_smartignore_paths_index()

            # instructions last
            iw = InstructionsWriter(
                output_dir=self.output_dir,
                instructions_filename=instructions_filename,
                output_format=self.output_format,
                smartignore_file=self.smartignore.smartignore_file,
                smartignore_patterns=list(self.smartignore.patterns),
                use_smartignore_exclude=self.use_smartignore_exclude,
                create_smartignore_paths_index=self.create_smartignore_paths_index,
                check_stop=self.check_stop,
                log=self.log,
                ask_overwrite=self.ask_overwrite,
            )
            iw.write(
                index_filename=index_filename if self.create_index else None,
                generated_meta=generated_meta,
                bundle_artifacts=bundle_artifacts if bundle_artifacts else None,
                upload_doc_filename=upload_doc_filename,
            )

            # Excluded files report
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