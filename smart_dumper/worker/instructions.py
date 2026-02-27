# worker/instructions.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional


@dataclass(frozen=True)
class InstructionsWriter:
    """
    Extracted from DumpWorker.write_instructions_file().
    Writes the "START HERE" instructions markdown file.
    """

    output_dir: Path
    instructions_filename: str
    output_format: str  # "text" or "xml"
    smartignore_file: Path
    smartignore_patterns: List[str]
    use_smartignore_exclude: bool
    create_smartignore_paths_index: bool

    check_stop: Callable[[], None]
    log: Callable[[str], None]
    ask_overwrite: Callable[[str], bool]

    def write(
        self,
        *,
        index_filename: Optional[str],
        generated_meta: List[dict],
        # Backward compatible: old grouped bundles mapping (CORE/DOCS_TOOLS/TESTS_OTHERS + manifest)
        bundle_artifacts: Optional[Dict[str, str]] = None,
        # New: single upload-helper doc filename (preferred)
        upload_doc_filename: Optional[str] = None,
    ) -> None:
        self.check_stop()

        out_path = self.output_dir / self.instructions_filename
        should_write = True

        if out_path.exists():
            self.log(f"Instructions file {self.instructions_filename} already exists.")
            if not self.ask_overwrite(self.instructions_filename):
                should_write = False
                self.log("Skipping instructions file.")
            else:
                self.log("Overwriting instructions file.")

        if not should_write:
            return

        volumes_list = "\n".join([f"- {m.get('filename','')}  —  {m.get('title','')}" for m in generated_meta])

        # Navigation first-step
        if upload_doc_filename:
            next_step = (
                f"1) Open `{upload_doc_filename}` (single combined upload doc) and search for the path you need.\n"
            )
            if index_filename:
                next_step += f"   (Optional) Use `{index_filename}` to locate the relevant volume faster.\n"
        else:
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

        upload_helpers_block = ""

        # Prefer explicit single-doc arg
        single_doc = upload_doc_filename

        # Fallback: allow passing it through bundle_artifacts (for convenience)
        if not single_doc and bundle_artifacts:
            for k in ("upload_doc", "single_upload_doc", "single", "doc"):
                v = bundle_artifacts.get(k)
                if v:
                    single_doc = v
                    break

        if single_doc:
            upload_helpers_block = (
                "\n## ChatGPT upload helper (single file)\n"
                f"- Upload doc: `{single_doc}`\n"
            )
        else:
            # Legacy grouped bundles + manifest
            if bundle_artifacts:
                lines: List[str] = []
                manifest = bundle_artifacts.get("manifest")
                if manifest:
                    lines.append(f"- Grouped manifest: `{manifest}`")
                for k in ("CORE", "DOCS_TOOLS", "TESTS_OTHERS"):
                    if k in bundle_artifacts:
                        lines.append(f"- Bundle {k}: `{bundle_artifacts[k]}`")
                if lines:
                    upload_helpers_block = "\n## Upload-helper bundles (legacy)\n" + "\n".join(lines) + "\n"

        fmt = (self.output_format or "").strip().lower()
        if fmt == "xml":
            format_notes = "- Use `<file_index>` then search for `<file path=\"...\">`.\n"
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
- Instructions (this): `{self.instructions_filename}`
- Master index: `{index_filename or "(not generated)"}`
- Volumes:
{volumes_list}
{upload_helpers_block}
"""
        with out_path.open("w", encoding="utf-8") as f:
            f.write(text)

        self.log(f"-> Created Instructions File: {self.instructions_filename}")