# worker/file_processing.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..xml_utils import chunk_lines_keepends, short_sha1
from .ai_navigation import (
    build_chunk_refs,
    build_line_ref,
    extract_python_imports,
    extract_python_symbols,
    number_lines,
    summarize_file,
)


@dataclass(frozen=True)
class FileProcessor:
    """
    Responsible for reading a single file and returning normalized metadata + content/chunks.

    Extracted from DumpWorker._process_file_content(), with improved stop-handling and
    safer rel_path computation.

    AI navigation metadata is intentionally created here so writers and indexes can consume
    one shared file_data shape without recomputing or drifting.
    """

    root_dir: Path
    chunk_max_lines: int
    oversize_bytes: int
    stop_event: Any  # threading.Event-like (needs .is_set())
    is_custom_excluded: Callable[[Path], bool]
    exclusion_mode_getter: Callable[[], str]
    get_file_size: Callable[[Path], int]
    check_stop: Optional[Callable[[], None]] = None  # optional: raise InterruptedError

    ai_navigation: bool = True
    number_source_lines: bool = False
    create_symbol_index: bool = True
    create_import_index: bool = True
    create_file_summaries: bool = True
    line_number_width: int = 6

    def _stop_now(self) -> bool:
        return bool(getattr(self.stop_event, "is_set", lambda: False)())

    def _check_stop(self) -> None:
        if self.check_stop is not None:
            self.check_stop()
            return
        if self._stop_now():
            raise InterruptedError("Stopped by user.")

    def process_file_content(self, f: Path) -> Optional[Dict[str, Any]]:
        """
        Returns:
            dict with keys:
              rel_path, ext, size_bytes, line_count, kind, file_id, chunks, content,
              line_ref, chunk_refs, symbols, imports, summary, numbered_content
            or None if stop_event is already set before starting.
        """
        if self._stop_now():
            return None

        try:
            # Stop-check early for consistent behavior with DumpWorker.check_stop.
            self._check_stop()

            try:
                rel_path = f.relative_to(self.root_dir).as_posix()
            except Exception:
                rel_path = f.as_posix()

            ext = f.suffix.lower()
            is_excluded_path = self.is_custom_excluded(f)
            exclusion_mode = (self.exclusion_mode_getter() or "").strip()

            size_bytes = 0
            line_count = 0
            content = ""
            kind = "source"

            if is_excluded_path:
                if "Names" in exclusion_mode:
                    # "list_name_only": content omitted, only path is meaningful.
                    content = ""
                    kind = "list_name_only"
                    size_bytes = 0
                else:
                    # "metadata_only": size captured, content omitted.
                    size_bytes = int(self.get_file_size(f))
                    content = ""
                    kind = "metadata_only"
            else:
                size_bytes = int(self.get_file_size(f))
                if size_bytes > int(self.oversize_bytes):
                    content = f"SKIPPED_OVERSIZED: {size_bytes} bytes"
                    kind = "oversized"
                else:
                    self._check_stop()
                    content = f.read_text(encoding="utf-8", errors="replace")
                    self._check_stop()
                    line_count = len(content.splitlines())
                    kind = "markdown" if ext == ".md" else "source"

            # Preserve the full clean source before chunking clears content.
            clean_content = content

            # Stable ID: content-hash when content is included, otherwise metadata-hash.
            if kind in ("source", "markdown") and clean_content and size_bytes <= int(self.oversize_bytes):
                file_id = short_sha1(rel_path + "\n" + clean_content)
            else:
                file_id = short_sha1(f"{rel_path}\n{size_bytes}\n{kind}")

            # AI navigation metadata.
            line_ref = ""
            chunk_refs: list[str] = []
            symbols: list[dict] = []
            imports: list[dict] = []
            summary = ""
            numbered_content = ""

            if self.ai_navigation and kind in ("source", "markdown") and clean_content:
                line_ref = build_line_ref(line_count)

                if ext == ".py":
                    if self.create_symbol_index:
                        self._check_stop()
                        symbols = extract_python_symbols(clean_content)

                    if self.create_import_index:
                        self._check_stop()
                        imports = extract_python_imports(clean_content)

                if self.create_file_summaries:
                    self._check_stop()
                    summary = summarize_file(
                        rel_path=rel_path,
                        kind=kind,
                        symbols=symbols,
                        imports=imports,
                    )

            if self.number_source_lines and kind in ("source", "markdown") and clean_content:
                self._check_stop()
                numbered_content = number_lines(clean_content, width=int(self.line_number_width))

            # Chunk big files.
            chunks = None
            if kind in ("source", "markdown") and clean_content and line_count > int(self.chunk_max_lines):
                self._check_stop()
                raw_chunks = chunk_lines_keepends(clean_content, int(self.chunk_max_lines))
                chunks = []

                for c in raw_chunks:
                    self._check_stop()
                    start_line = int(c["start_line"])
                    end_line = int(c["end_line"])
                    chunk_id = f"{file_id}:{start_line}-{end_line}"

                    chunks.append(
                        {
                            "id": chunk_id,
                            "start_line": start_line,
                            "end_line": end_line,
                            "text": c["text"],
                        }
                    )

                chunk_refs = build_chunk_refs(chunks, line_count)
                content = ""  # Content is now carried by chunks.
            else:
                content = clean_content
                chunk_refs = build_chunk_refs(chunks, line_count)

            return {
                "rel_path": rel_path,
                "ext": ext,
                "size_bytes": int(size_bytes),
                "line_count": int(line_count),
                "kind": kind,
                "file_id": file_id,
                "chunks": chunks,
                "content": content,
                "line_ref": line_ref,
                "chunk_refs": chunk_refs,
                "symbols": symbols,
                "imports": imports,
                "summary": summary,
                "numbered_content": numbered_content,
            }

        except InterruptedError:
            return None
        except Exception as e:
            # Keep worker resilient: return an error pseudo-entry.
            safe_name = getattr(f, "name", "unknown")
            return {
                "rel_path": safe_name,
                "ext": "",
                "size_bytes": 0,
                "line_count": 0,
                "kind": "error",
                "file_id": short_sha1(safe_name),
                "chunks": None,
                "content": f"{type(e).__name__}: {e}",
                "line_ref": "",
                "chunk_refs": [],
                "symbols": [],
                "imports": [],
                "summary": "File processing error.",
                "numbered_content": "",
            }