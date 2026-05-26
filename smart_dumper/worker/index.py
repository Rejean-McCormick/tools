# smart_wiki_dumper/worker/index.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..xml_utils import escape_xml_text


class IndexWriterMixin:
    """
    Index writer extracted from DumpWorker.

    Requires the host class to provide:
      - self.root_dir: Path
      - self.output_dir: Path
      - self.output_format: str  ("text" or "xml")
      - self.txt_mode: str       ("none" | "copy" | "only")  [used indirectly by _maybe_write_txt_companion]
      - self.log: callable(str) -> None
      - self.ask_overwrite: callable(str) -> bool
      - methods:
          * check_stop() -> None
          * _maybe_write_txt_companion(path: Path) -> None
    """

    # -----------------------------
    # AI navigation helpers
    # -----------------------------

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _as_list(self, value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            return [part.strip() for part in value.split(",") if part.strip()]
        return []

    def _format_chunk_refs(self, chunk_refs: Any) -> str:
        refs = self._as_list(chunk_refs)
        return ",".join(str(ref) for ref in refs if str(ref).strip())

    def _normalize_file_entry(self, raw: Dict[str, Any], volume_filename: str) -> Dict[str, Any]:
        path = str(raw.get("path") or raw.get("rel_path") or "")
        line_count = self._safe_int(raw.get("line_count", raw.get("lines", 0)))

        return {
            "path": path,
            "volume": str(raw.get("volume") or volume_filename or ""),
            "id": str(raw.get("id") or raw.get("file_id") or ""),
            "kind": str(raw.get("kind") or ""),
            "size_bytes": self._safe_int(raw.get("size_bytes", raw.get("size", 0))),
            "line_count": line_count,
            "line_ref": str(raw.get("line_ref") or (f"1-{line_count}" if line_count > 0 else "")),
            "chunk_refs": self._as_list(raw.get("chunk_refs")),
            "symbols": self._as_list(raw.get("symbols")),
            "imports": self._as_list(raw.get("imports")),
            "summary": str(raw.get("summary") or ""),
        }

    def _collect_file_entries(self, generated_meta: List[dict]) -> List[Dict[str, Any]]:
        """
        Preferred source: meta["file_entries"] from volume writers.

        Backward-compatible fallback:
        if a volume has no file_entries yet, create minimal entries from contained_files.
        """
        entries: List[Dict[str, Any]] = []

        for meta in generated_meta:
            self.check_stop()
            volume_filename = str(meta.get("filename", ""))

            file_entries = meta.get("file_entries") or []
            if isinstance(file_entries, list) and file_entries:
                for raw in file_entries:
                    self.check_stop()
                    if isinstance(raw, dict):
                        entry = self._normalize_file_entry(raw, volume_filename)
                        if entry["path"]:
                            entries.append(entry)
                continue

            for path in meta.get("contained_files", []) or []:
                self.check_stop()
                entries.append(
                    {
                        "path": str(path),
                        "volume": volume_filename,
                        "id": "",
                        "kind": "",
                        "size_bytes": 0,
                        "line_count": 0,
                        "line_ref": "",
                        "chunk_refs": [],
                        "symbols": [],
                        "imports": [],
                        "summary": "",
                    }
                )

        return entries

    def _format_import_statement(self, imp: Dict[str, Any]) -> str:
        kind = str(imp.get("kind") or "").strip()
        module = str(imp.get("module") or "").strip()
        name = str(imp.get("name") or "").strip()
        alias = str(imp.get("alias") or "").strip()

        if kind == "from" or name:
            stmt = f"from {module} import {name}".strip()
        else:
            stmt = f"import {module}".strip()

        if alias:
            stmt += f" as {alias}"

        return stmt

    def _build_patch_targets(self, file_entries: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        present_paths = {str(entry.get("path", "")) for entry in file_entries}

        candidates = [
            ("GUI options", "gui.py"),
            ("Worker orchestration", "worker/dump_worker.py"),
            ("Per-file metadata", "worker/file_processing.py"),
            ("Text output format", "worker/writers_text.py"),
            ("XML output format", "worker/writers_xml.py"),
            ("Master index format", "worker/index.py"),
            ("Generated AI instructions", "worker/instructions.py"),
            ("Defaults/constants", "constants.py"),
            ("AI navigation helpers", "worker/ai_navigation.py"),
        ]

        targets: List[Dict[str, str]] = []
        for label, path in candidates:
            if path in present_paths:
                targets.append({"label": label, "path": path})

        return targets

    # -----------------------------
    # Main writer
    # -----------------------------

    def write_index(
        self,
        index_filename: str,
        repo_name: str,
        instructions_filename: str,
        generated_meta: List[dict],
        *,
        upload_helper_file: Optional[str] = None,
        create_patch_targets: bool = True,
    ) -> None:
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

        file_entries = self._collect_file_entries(generated_meta)
        patch_targets = self._build_patch_targets(file_entries) if create_patch_targets else []

        if self.output_format == "xml":
            self._write_index_xml(
                index_path=index_path,
                index_filename=index_filename,
                repo_name=repo_name,
                instructions_filename=instructions_filename,
                generated_meta=generated_meta,
                upload_helper_file=upload_helper_file,
                file_entries=file_entries,
                patch_targets=patch_targets,
            )
            return

        self._write_index_text(
            index_path=index_path,
            index_filename=index_filename,
            repo_name=repo_name,
            instructions_filename=instructions_filename,
            generated_meta=generated_meta,
            upload_helper_file=upload_helper_file,
            file_entries=file_entries,
            patch_targets=patch_targets,
        )

    # -----------------------------
    # XML index
    # -----------------------------

    def _write_index_xml(
        self,
        *,
        index_path: Path,
        index_filename: str,
        repo_name: str,
        instructions_filename: str,
        generated_meta: List[dict],
        upload_helper_file: Optional[str],
        file_entries: List[Dict[str, Any]],
        patch_targets: List[Dict[str, str]],
    ) -> None:
        with index_path.open("w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write("<index>\n")
            f.write(f"  <repo_name>{escape_xml_text(repo_name)}</repo_name>\n")
            f.write(f"  <root_dir>{escape_xml_text(str(self.root_dir))}</root_dir>\n")
            f.write(f"  <generated_at>{datetime.now().isoformat()}</generated_at>\n")
            f.write(f"  <instructions_file>{escape_xml_text(instructions_filename)}</instructions_file>\n")
            if upload_helper_file:
                f.write(f"  <upload_helper_file>{escape_xml_text(upload_helper_file)}</upload_helper_file>\n")

            f.write("  <volumes>\n")
            for meta in generated_meta:
                self.check_stop()
                f.write("    <volume>\n")
                f.write(f"      <filename>{escape_xml_text(str(meta.get('filename', '')))}</filename>\n")
                f.write(f"      <title>{escape_xml_text(str(meta.get('title', '')))}</title>\n")
                f.write(f"      <short_title>{escape_xml_text(str(meta.get('short_title', '')))}</short_title>\n")
                f.write(f"      <size_mb>{round(float(meta.get('size_mb', 0.0) or 0.0), 4)}</size_mb>\n")
                f.write(f"      <file_count>{self._safe_int(meta.get('file_count', 0))}</file_count>\n")
                f.write("      <contained_files>\n")
                for cfile in meta.get("contained_files", []) or []:
                    self.check_stop()
                    f.write(f"        <file>{escape_xml_text(str(cfile))}</file>\n")
                f.write("      </contained_files>\n")
                f.write("    </volume>\n")
            f.write("  </volumes>\n")

            f.write("  <file_detail_index>\n")
            for entry in file_entries:
                self.check_stop()
                f.write("    <file>\n")
                f.write(f"      <path>{escape_xml_text(str(entry.get('path', '')))}</path>\n")
                f.write(f"      <volume>{escape_xml_text(str(entry.get('volume', '')))}</volume>\n")
                f.write(f"      <id>{escape_xml_text(str(entry.get('id', '')))}</id>\n")
                f.write(f"      <kind>{escape_xml_text(str(entry.get('kind', '')))}</kind>\n")
                f.write(f"      <size_bytes>{self._safe_int(entry.get('size_bytes', 0))}</size_bytes>\n")
                f.write(f"      <line_count>{self._safe_int(entry.get('line_count', 0))}</line_count>\n")
                f.write(f"      <line_ref>{escape_xml_text(str(entry.get('line_ref', '')))}</line_ref>\n")
                f.write(f"      <chunk_refs>{escape_xml_text(self._format_chunk_refs(entry.get('chunk_refs')))}</chunk_refs>\n")
                f.write(f"      <symbols>{len(self._as_list(entry.get('symbols')))}</symbols>\n")
                f.write(f"      <imports>{len(self._as_list(entry.get('imports')))}</imports>\n")
                f.write(f"      <summary>{escape_xml_text(str(entry.get('summary', '')))}</summary>\n")
                f.write("    </file>\n")
            f.write("  </file_detail_index>\n")

            f.write("  <symbol_index>\n")
            for entry in file_entries:
                path = str(entry.get("path", ""))
                volume = str(entry.get("volume", ""))
                for symbol in self._as_list(entry.get("symbols")):
                    self.check_stop()
                    if not isinstance(symbol, dict):
                        continue
                    f.write("    <symbol>\n")
                    f.write(f"      <type>{escape_xml_text(str(symbol.get('type', '')))}</type>\n")
                    f.write(f"      <name>{escape_xml_text(str(symbol.get('name', '')))}</name>\n")
                    f.write(f"      <qualname>{escape_xml_text(str(symbol.get('qualname', '')))}</qualname>\n")
                    f.write(f"      <path>{escape_xml_text(path)}</path>\n")
                    f.write(f"      <volume>{escape_xml_text(volume)}</volume>\n")
                    f.write(f"      <line>{self._safe_int(symbol.get('line', 0))}</line>\n")
                    f.write(f"      <end_line>{self._safe_int(symbol.get('end_line', 0))}</end_line>\n")
                    f.write("    </symbol>\n")
            f.write("  </symbol_index>\n")

            f.write("  <import_index>\n")
            for entry in file_entries:
                path = str(entry.get("path", ""))
                volume = str(entry.get("volume", ""))
                for imp in self._as_list(entry.get("imports")):
                    self.check_stop()
                    if not isinstance(imp, dict):
                        continue
                    f.write("    <import>\n")
                    f.write(f"      <path>{escape_xml_text(path)}</path>\n")
                    f.write(f"      <volume>{escape_xml_text(volume)}</volume>\n")
                    f.write(f"      <statement>{escape_xml_text(self._format_import_statement(imp))}</statement>\n")
                    f.write(f"      <module>{escape_xml_text(str(imp.get('module', '')))}</module>\n")
                    f.write(f"      <name>{escape_xml_text(str(imp.get('name', '')))}</name>\n")
                    f.write(f"      <alias>{escape_xml_text(str(imp.get('alias', '')))}</alias>\n")
                    f.write(f"      <line>{self._safe_int(imp.get('line', 0))}</line>\n")
                    f.write("    </import>\n")
            f.write("  </import_index>\n")

            f.write("  <patch_targets>\n")
            for target in patch_targets:
                self.check_stop()
                f.write("    <target>\n")
                f.write(f"      <label>{escape_xml_text(str(target.get('label', '')))}</label>\n")
                f.write(f"      <path>{escape_xml_text(str(target.get('path', '')))}</path>\n")
                f.write("    </target>\n")
            f.write("  </patch_targets>\n")

            f.write("</index>\n")

        self.log(f"-> Created Master Index: {index_filename}")
        self._maybe_write_txt_companion(index_path)

    # -----------------------------
    # Text index
    # -----------------------------

    def _write_index_text(
        self,
        *,
        index_path: Path,
        index_filename: str,
        repo_name: str,
        instructions_filename: str,
        generated_meta: List[dict],
        upload_helper_file: Optional[str],
        file_entries: List[Dict[str, Any]],
        patch_targets: List[Dict[str, str]],
    ) -> None:
        with index_path.open("w", encoding="utf-8", errors="replace") as out:
            out.write("==== MASTER INDEX ====\n")
            out.write(f"repo_name: {repo_name}\n")
            out.write(f"root_dir: {self.root_dir}\n")
            out.write(f"generated_at: {datetime.now().isoformat()}\n")
            out.write(f"instructions_file: {instructions_filename}\n")
            out.write(f"upload_helper_file: {upload_helper_file or ''}\n\n")

            out.write("==== VOLUMES ====\n")
            for meta in generated_meta:
                self.check_stop()
                out.write(
                    f"- filename={meta.get('filename','')} | title={meta.get('title','')} | "
                    f"short_title={meta.get('short_title','')} | files={meta.get('file_count',0)} | "
                    f"size_mb={round(float(meta.get('size_mb',0.0) or 0.0),4)}\n"
                )

            out.write("\n==== FILE LOCATOR (path -> volume) ====\n")
            for meta in generated_meta:
                self.check_stop()
                vol = meta.get("filename", "")
                for p in meta.get("contained_files", []) or []:
                    self.check_stop()
                    out.write(f"{p}\tvolume={vol}\n")

            out.write("\n==== FILE DETAIL INDEX ====\n")
            for entry in file_entries:
                self.check_stop()
                path = str(entry.get("path", ""))
                if not path:
                    continue

                out.write(f"{path}\n")
                out.write(f"  volume={entry.get('volume', '')}\n")
                out.write(f"  id={entry.get('id', '')}\n")
                out.write(f"  kind={entry.get('kind', '')}\n")
                out.write(f"  size_bytes={self._safe_int(entry.get('size_bytes', 0))}\n")
                out.write(f"  lines={self._safe_int(entry.get('line_count', 0))}\n")
                out.write(f"  line_ref={entry.get('line_ref', '')}\n")
                out.write(f"  chunk_refs={self._format_chunk_refs(entry.get('chunk_refs'))}\n")
                out.write(f"  symbols={len(self._as_list(entry.get('symbols')))}\n")
                out.write(f"  imports={len(self._as_list(entry.get('imports')))}\n")
                out.write(f"  summary={entry.get('summary', '')}\n")

            out.write("\n==== SYMBOL INDEX ====\n")
            wrote_symbol = False
            for entry in file_entries:
                path = str(entry.get("path", ""))
                volume = str(entry.get("volume", ""))
                for symbol in self._as_list(entry.get("symbols")):
                    self.check_stop()
                    if not isinstance(symbol, dict):
                        continue

                    typ = str(symbol.get("type", ""))
                    name = str(symbol.get("qualname") or symbol.get("name") or "")
                    line = self._safe_int(symbol.get("line", 0))
                    end_line = self._safe_int(symbol.get("end_line", 0))

                    out.write(
                        f"{typ} {name}".strip()
                        + f"\tpath={path}"
                        + f"\tvolume={volume}"
                        + f"\tline={line}"
                        + f"\tend_line={end_line}\n"
                    )
                    wrote_symbol = True

            if not wrote_symbol:
                out.write("(none)\n")

            out.write("\n==== IMPORT INDEX ====\n")
            wrote_import = False
            for entry in file_entries:
                path = str(entry.get("path", ""))
                volume = str(entry.get("volume", ""))
                for imp in self._as_list(entry.get("imports")):
                    self.check_stop()
                    if not isinstance(imp, dict):
                        continue

                    statement = self._format_import_statement(imp)
                    line = self._safe_int(imp.get("line", 0))

                    out.write(f"{path}\t{statement}\tvolume={volume}\tline={line}\n")
                    wrote_import = True

            if not wrote_import:
                out.write("(none)\n")

            out.write("\n==== PATCH TARGETS ====\n")
            if patch_targets:
                for target in patch_targets:
                    self.check_stop()
                    out.write(f"{target.get('label', '')}\tpath={target.get('path', '')}\n")
            else:
                out.write("(none)\n")

        self.log(f"-> Created Master Index: {index_filename}")