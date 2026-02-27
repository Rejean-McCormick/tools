# worker/file_processing.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..xml_utils import chunk_lines_keepends, short_sha1


@dataclass(frozen=True)
class FileProcessor:
    """
    Responsible for reading a single file and returning normalized metadata + content/chunks.

    Extracted from DumpWorker._process_file_content(), with improved stop-handling and
    safer rel_path computation.
    """

    root_dir: Path
    chunk_max_lines: int
    oversize_bytes: int
    stop_event: Any  # threading.Event-like (needs .is_set())
    is_custom_excluded: Callable[[Path], bool]
    exclusion_mode_getter: Callable[[], str]
    get_file_size: Callable[[Path], int]
    check_stop: Optional[Callable[[], None]] = None  # optional: raise InterruptedError

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
              rel_path, ext, size_bytes, line_count, kind, file_id, chunks, content
            or None if stop_event is already set before starting.
        """
        if self._stop_now():
            return None

        try:
            # Stop-check early (for consistent behavior with DumpWorker.check_stop)
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
                    # "list_name_only": content omitted, only path is meaningful
                    content = ""
                    kind = "list_name_only"
                    size_bytes = 0
                else:
                    # "metadata_only": size captured, content omitted
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

            # Stable ID (content-hash when we actually include content, otherwise metadata-hash)
            if kind in ("source", "markdown") and content and size_bytes <= int(self.oversize_bytes):
                file_id = short_sha1(rel_path + "\n" + content)
            else:
                file_id = short_sha1(f"{rel_path}\n{size_bytes}\n{kind}")

            # Chunk big files
            chunks = None
            if kind in ("source", "markdown") and content and line_count > int(self.chunk_max_lines):
                self._check_stop()
                raw_chunks = chunk_lines_keepends(content, int(self.chunk_max_lines))
                chunks = []
                for c in raw_chunks:
                    self._check_stop()
                    chunk_id = f"{file_id}:{c['start_line']}-{c['end_line']}"
                    chunks.append(
                        {
                            "id": chunk_id,
                            "start_line": int(c["start_line"]),
                            "end_line": int(c["end_line"]),
                            "text": c["text"],
                        }
                    )
                content = ""  # content is now carried by chunks

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

        except InterruptedError:
            return None
        except Exception as e:
            # Keep worker resilient: return an error pseudo-entry
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
            }