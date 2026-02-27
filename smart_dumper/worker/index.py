# smart_wiki_dumper/worker/index.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

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

    def write_index(
        self,
        index_filename: str,
        repo_name: str,
        instructions_filename: str,
        generated_meta: List[dict],
        *,
        upload_helper_file: Optional[str] = None,
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

        if self.output_format == "xml":
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
            out.write(f"instructions_file: {instructions_filename}\n")
            out.write(f"upload_helper_file: {upload_helper_file or ''}\n\n")
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