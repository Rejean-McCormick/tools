# smart_wiki_dumper/worker/writers_text.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .ai_navigation import build_file_entry, format_chunk_refs


class WritersTextMixin:
    """
    TEXT writer extracted from DumpWorker.

    Requires the host class to provide:
      - self.root_dir: Path
      - self.output_dir: Path
      - self.log: callable(str) -> None
      - self.number_source_lines: bool
      - methods:
          * check_stop() -> None
          * _process_file_content(f: Path) -> Optional[Dict[str, Any]]
    """

    def _collect_file_data_parallel(
        self,
        files: List[Path],
        log_prefix_filename: str,
    ) -> Tuple[List[Dict[str, Any]], float]:
        """
        Collect per-file metadata+content (or chunks) using the host's _process_file_content.
        """
        import concurrent.futures

        total_size = 0
        self.log(f"-> Processing {log_prefix_filename} ({len(files)} files)...")

        max_workers = min(50, len(files) + 1)
        file_data_list: List[Dict[str, Any]] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(self._process_file_content, files)
            for res in results:
                self.check_stop()
                if not res:
                    continue
                file_data_list.append(res)
                total_size += int(res.get("size_bytes", 0) or 0)

        size_mb = total_size / (1024 * 1024)
        return file_data_list, size_mb

    def _text_attr(self, value: Any) -> str:
        """
        Compact single-line text value for FILE_INDEX / FILE BEGIN metadata.
        """
        s = str(value or "")
        s = s.replace("\r", " ").replace("\n", " ").strip()
        s = s.replace('"', "'")
        return s

    def _chunk_refs_from_chunks(self, chunks: List[Dict[str, Any]]) -> List[str]:
        """
        Backward-compatible fallback when FileProcessor did not provide chunk_refs.
        """
        refs: List[str] = []
        for c in chunks:
            start = int(c.get("start_line", c.get("start", 0)) or 0)
            end = int(c.get("end_line", c.get("end", 0)) or 0)
            if start > 0 and end >= start:
                refs.append(f"{start}-{end}")
        return refs

    def _content_for_output(self, f_data: Dict[str, Any]) -> str:
        """
        Use numbered_content only when explicitly requested.
        Keep clean content as the default.
        """
        if bool(getattr(self, "number_source_lines", False)):
            numbered_content = str(f_data.get("numbered_content", "") or "")
            if numbered_content:
                return numbered_content
        return str(f_data.get("content", "") or "")

    def _chunk_text_for_output(self, chunk: Dict[str, Any]) -> str:
        """
        Use numbered chunk text only when available and explicitly requested.
        Falls back to clean chunk text.
        """
        if bool(getattr(self, "number_source_lines", False)):
            numbered_text = str(chunk.get("numbered_text", "") or "")
            if numbered_text:
                return numbered_text
        return str(chunk.get("text", "") or "")

    def write_volume_text(self, filename: str, files: List[Path], title: str, nav_context: dict) -> Optional[dict]:
        """
        Writes a structured plain-text volume file.

        Returns metadata used by the master index and upload helpers.
        Keeps backward-compatible contained_files and adds rich file_entries.
        """
        if not files:
            return None
        self.check_stop()

        out_path = self.output_dir / filename

        try:
            files.sort(key=lambda p: p.relative_to(self.root_dir).as_posix().lower())
        except Exception:
            files.sort(key=lambda p: p.name.lower())

        file_data_list, size_mb = self._collect_file_data_parallel(files, filename)
        file_entries = [build_file_entry(f_data, filename) for f_data in file_data_list]

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
                out.write(f"prev_title: {nav_context.get('prev_title', '')}\n")
                out.write(f"next_title: {nav_context.get('next_title', '')}\n")
                out.write(f"short_title: {nav_context.get('short_title', '')}\n")

                out.write("\n==== FILE_INDEX ====\n")
                for f_data in file_data_list:
                    self.check_stop()

                    rel_path = str(f_data.get("rel_path", ""))
                    kind = str(f_data.get("kind", ""))
                    size_bytes = int(f_data.get("size_bytes", 0) or 0)
                    line_count = int(f_data.get("line_count", 0) or 0)
                    file_id = str(f_data.get("file_id", ""))

                    chunks = f_data.get("chunks") or []
                    chunks = chunks if isinstance(chunks, list) else []
                    chunks_count = len(chunks)

                    line_ref = str(f_data.get("line_ref", "") or "")
                    chunk_refs = f_data.get("chunk_refs") or self._chunk_refs_from_chunks(chunks)
                    chunk_refs_text = format_chunk_refs(chunk_refs)

                    symbols = f_data.get("symbols") or []
                    imports = f_data.get("imports") or []
                    symbols_count = len(symbols) if isinstance(symbols, list) else 0
                    imports_count = len(imports) if isinstance(imports, list) else 0

                    summary = self._text_attr(f_data.get("summary", ""))

                    out.write(
                        "ENTRY "
                        f"id={file_id} "
                        f'path="{rel_path}" '
                        f"kind={kind} "
                        f"size={size_bytes} "
                        f"lines={line_count} "
                        f"line_ref={line_ref} "
                        f"chunks={chunks_count} "
                        f"chunk_refs={chunk_refs_text} "
                        f"symbols={symbols_count} "
                        f"imports={imports_count} "
                        f'summary="{summary}"\n'
                    )

                out.write("\n==== FILES ====\n")
                for f_data in file_data_list:
                    self.check_stop()

                    rel_path = str(f_data.get("rel_path", ""))
                    kind = str(f_data.get("kind", ""))
                    size_bytes = int(f_data.get("size_bytes", 0) or 0)
                    line_count = int(f_data.get("line_count", 0) or 0)
                    file_id = str(f_data.get("file_id", ""))

                    chunks = f_data.get("chunks") or []
                    chunks = chunks if isinstance(chunks, list) else []

                    line_ref = str(f_data.get("line_ref", "") or "")
                    chunk_refs = f_data.get("chunk_refs") or self._chunk_refs_from_chunks(chunks)
                    chunk_refs_text = format_chunk_refs(chunk_refs)
                    summary = self._text_attr(f_data.get("summary", ""))

                    out.write(
                        "\n----- FILE BEGIN -----\n"
                        f'path="{rel_path}"\n'
                        f"id={file_id}\n"
                        f"kind={kind}\n"
                        f"size={size_bytes}\n"
                        f"lines={line_count}\n"
                        f"line_ref={line_ref}\n"
                        f"chunks={len(chunks)}\n"
                        f"chunk_refs={chunk_refs_text}\n"
                        f'summary="{summary}"\n'
                    )

                    if chunks:
                        for c in chunks:
                            self.check_stop()
                            cid = str(c.get("id", ""))
                            sline = int(c.get("start_line", c.get("start", 0)) or 0)
                            eline = int(c.get("end_line", c.get("end", 0)) or 0)
                            text = self._chunk_text_for_output(c)

                            out.write(
                                "\n--- CHUNK BEGIN ---\n"
                                f"id={cid}\n"
                                f"start={sline}\n"
                                f"end={eline}\n"
                                "----\n"
                            )
                            out.write(text)
                            if text and not text.endswith("\n"):
                                out.write("\n")
                            out.write("--- CHUNK END ---\n")
                    else:
                        content = self._content_for_output(f_data)
                        out.write("----\n")
                        out.write(content)
                        if content and not content.endswith("\n"):
                            out.write("\n")

                    out.write("----- FILE END -----\n")

            contained_files = [
                str(entry.get("rel_path", ""))
                for entry in file_data_list
                if entry.get("rel_path")
            ]

            return {
                "filename": filename,
                "title": title,
                "size_mb": size_mb,
                "file_count": len(files),
                "short_title": nav_context.get("short_title", title),
                "contained_files": contained_files,
                "file_entries": file_entries,
            }

        except Exception as e:
            self.log(f"Error writing TEXT file {filename}: {e}")
            return None