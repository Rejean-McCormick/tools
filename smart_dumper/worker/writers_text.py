# smart_wiki_dumper/worker/writers_text.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class WritersTextMixin:
    """
    TEXT writer extracted from DumpWorker.

    Requires the host class to provide:
      - self.root_dir: Path
      - self.output_dir: Path
      - self.log: callable(str) -> None
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

    def write_volume_text(self, filename: str, files: List[Path], title: str, nav_context: dict) -> Optional[dict]:
        """
        Writes a structured plain-text "volume" file.

        Returns a meta dict (same shape as the monolith) or None on failure.
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
                    self.check_stop()
                    rel_path = str(f_data.get("rel_path", ""))
                    kind = str(f_data.get("kind", ""))
                    size_bytes = int(f_data.get("size_bytes", 0) or 0)
                    line_count = int(f_data.get("line_count", 0) or 0)
                    file_id = str(f_data.get("file_id", ""))

                    chunks = f_data.get("chunks") or []
                    chunks_count = len(chunks) if isinstance(chunks, list) else 0

                    out.write(
                        "ENTRY "
                        f"id={file_id} "
                        f'path="{rel_path}" '
                        f"kind={kind} "
                        f"size={size_bytes} "
                        f"lines={line_count} "
                        f"chunks={chunks_count}\n"
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

                    out.write(
                        "\n----- FILE BEGIN -----\n"
                        f'path="{rel_path}"\n'
                        f"id={file_id}\n"
                        f"kind={kind}\n"
                        f"size={size_bytes}\n"
                        f"lines={line_count}\n"
                        f"chunks={len(chunks)}\n"
                    )

                    if chunks:
                        for c in chunks:
                            self.check_stop()
                            cid = str(c.get("id", ""))
                            sline = int(c.get("start_line", 0) or 0)
                            eline = int(c.get("end_line", 0) or 0)
                            text = str(c.get("text", ""))

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
                        content = str(f_data.get("content", "") or "")
                        out.write("----\n")
                        out.write(content)
                        if content and not content.endswith("\n"):
                            out.write("\n")

                    out.write("----- FILE END -----\n")

            contained_files = [str(entry.get("rel_path", "")) for entry in file_data_list if entry.get("rel_path")]
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