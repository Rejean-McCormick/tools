# worker/writers_xml.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..xml_utils import escape_xml_attr, escape_xml_text, wrap_cdata
from .ai_navigation import build_file_entry, format_chunk_refs


@dataclass(frozen=True)
class XmlWriterConfig:
    """
    XML writer options.

    txt_mode:
      - "none": write .xml only
      - "copy": write .xml plus .xml.txt companion copies
      - "only": write .xml.txt only (no .xml)
    """

    txt_mode: str = "copy"  # "none" | "copy" | "only"


def index_filename_xml(txt_mode: str) -> str:
    if (txt_mode or "").strip().lower() == "only":
        return "Index.xml.txt"
    return "Index.xml"


def normalize_volume_filename_xml(name: str, txt_mode: str) -> str:
    """
    Input base naming uses .xml convention; normalize to final extension.
    If txt_mode == "only" => returns .xml.txt, else returns .xml.
    """
    base = name
    for suf in (".xml.txt", ".xml", ".txt", ".md"):
        if base.lower().endswith(suf):
            base = base[: -len(suf)]
            break

    txt_mode_norm = (txt_mode or "copy").strip().lower()
    fname = base + ".xml"
    if txt_mode_norm == "only":
        return fname + ".txt"
    return fname


def _txt_companion_path(p: Path) -> Path:
    return p.with_suffix(p.suffix + ".txt")


def maybe_write_txt_companion(
    *,
    src_xml_path: Path,
    txt_mode: str,
    log: Callable[[str], None],
    check_stop: Callable[[], None],
) -> None:
    """
    If txt_mode == "copy", create an identical .xml.txt companion next to .xml.
    """
    if (txt_mode or "").strip().lower() != "copy":
        return

    try:
        check_stop()
        dst = _txt_companion_path(src_xml_path)
        with src_xml_path.open("rb") as rf, dst.open("wb") as wf:
            while True:
                check_stop()
                chunk = rf.read(1024 * 1024)
                if not chunk:
                    break
                wf.write(chunk)
        log(f"    -> Wrote companion: {dst.name}")
    except Exception as e:
        log(f"    (warn) Could not write txt companion for {src_xml_path.name}: {e}")


def bundle_extension_xml() -> str:
    # upload-helper artifacts (bundles/single-doc) are text files containing XML payload
    return ".xml.txt"


def upload_helper_extension_xml() -> str:
    """
    Extension for upload-helper outputs in XML workflow.
    Always '.xml.txt' (even if txt_mode == 'none') because the helper is a text artifact.
    """
    return ".xml.txt"


def normalize_upload_helper_filename_xml(name: str) -> str:
    """
    Normalize any base name to the upload-helper extension '.xml.txt'.
    """
    base = (name or "").strip()
    for suf in (".xml.txt", ".xml", ".txt", ".md"):
        if base.lower().endswith(suf):
            base = base[: -len(suf)]
            break
    return base + upload_helper_extension_xml()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _xml_attr_join(values: list[str]) -> str:
    return escape_xml_attr(format_chunk_refs(values))


def _get_chunk_refs(f_data: Dict[str, Any]) -> list[str]:
    chunk_refs = f_data.get("chunk_refs") or []
    if isinstance(chunk_refs, str):
        return [part.strip() for part in chunk_refs.split(",") if part.strip()]
    if isinstance(chunk_refs, list):
        return [str(part).strip() for part in chunk_refs if str(part).strip()]
    return []


def _get_symbols(f_data: Dict[str, Any]) -> list[dict]:
    symbols = f_data.get("symbols") or []
    return symbols if isinstance(symbols, list) else []


def _get_imports(f_data: Dict[str, Any]) -> list[dict]:
    imports = f_data.get("imports") or []
    return imports if isinstance(imports, list) else []


def _content_for_output(f_data: Dict[str, Any]) -> str:
    """
    Use numbered content when FileProcessor supplied it, otherwise clean content.

    FileProcessor must keep clean `content` internally and expose `numbered_content`
    separately so writers can choose without mutating source metadata.
    """
    numbered = str(f_data.get("numbered_content", "") or "")
    if numbered:
        return numbered
    return str(f_data.get("content", "") or "")


def _chunk_text_for_output(chunk: Dict[str, Any]) -> str:
    numbered = str(chunk.get("numbered_text", "") or "")
    if numbered:
        return numbered
    return str(chunk.get("text", "") or "")


def _write_summary_xml(out: Any, summary: str, indent: str = "      ") -> None:
    if summary:
        out.write(f"{indent}<summary>{escape_xml_text(summary)}</summary>\n")


def _write_symbols_xml(out: Any, symbols: list[dict], indent: str = "      ") -> None:
    if not symbols:
        return

    out.write(f"{indent}<symbols>\n")
    child_indent = indent + "  "
    for sym in symbols:
        typ = escape_xml_attr(str(sym.get("type", "")))
        name = escape_xml_attr(str(sym.get("name", "")))
        qualname = escape_xml_attr(str(sym.get("qualname", sym.get("name", ""))))
        line = _safe_int(sym.get("line", 0))
        end_line = _safe_int(sym.get("end_line", line))
        out.write(
            f'{child_indent}<symbol type="{typ}" name="{name}" qualname="{qualname}" '
            f'line="{line}" end_line="{end_line}" />\n'
        )
    out.write(f"{indent}</symbols>\n")


def _write_imports_xml(out: Any, imports: list[dict], indent: str = "      ") -> None:
    if not imports:
        return

    out.write(f"{indent}<imports>\n")
    child_indent = indent + "  "
    for imp in imports:
        kind = escape_xml_attr(str(imp.get("kind", "")))
        module = escape_xml_attr(str(imp.get("module", "")))
        name = escape_xml_attr(str(imp.get("name", "")))
        alias = escape_xml_attr(str(imp.get("alias", "")))
        line = _safe_int(imp.get("line", 0))
        out.write(
            f'{child_indent}<import kind="{kind}" module="{module}" name="{name}" '
            f'alias="{alias}" line="{line}" />\n'
        )
    out.write(f"{indent}</imports>\n")


def write_volume_xml(
    *,
    output_dir: Path,
    root_dir: Path,
    filename: str,
    files: List[Path],
    title: str,
    nav_context: Dict[str, Any],
    file_data_list: List[Dict[str, Any]],
    size_mb: float,
    txt_mode: str,
    log: Callable[[str], None],
    check_stop: Callable[[], None],
) -> Optional[dict]:
    """
    Writes an XML volume and returns meta.

    Expects file_data_list already prepared by FileProcessor, including:
      - rel_path, chunks, content, kind, file_id
      - optional AI-navigation keys:
        line_ref, chunk_refs, symbols, imports, summary, numbered_content
    """
    if not files:
        return None

    check_stop()
    out_path = (output_dir / filename).resolve()

    try:
        log("    Writing XML to disk...")
        # When txt_mode == "only", we still write to `out_path` which is expected to be ".xml.txt"
        with out_path.open("w", encoding="utf-8") as out:
            out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            out.write("<volume>\n")

            out.write("  <meta>\n")
            out.write(f"    <generated_at>{datetime.now().isoformat()}</generated_at>\n")
            out.write(f"    <title>{escape_xml_text(title)}</title>\n")
            out.write(f"    <root_dir>{escape_xml_text(str(root_dir))}</root_dir>\n")
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
                check_stop()

                rel_path = str(f_data.get("rel_path", ""))
                kind = str(f_data.get("kind", ""))
                file_id = str(f_data.get("file_id", ""))
                size_bytes = _safe_int(f_data.get("size_bytes", 0))
                line_count = _safe_int(f_data.get("line_count", 0))
                chunks = f_data.get("chunks") or []
                chunks_count = len(chunks) if isinstance(chunks, list) else 0

                line_ref = str(f_data.get("line_ref", "") or "")
                chunk_refs = _get_chunk_refs(f_data)
                symbols = _get_symbols(f_data)
                imports = _get_imports(f_data)
                summary = str(f_data.get("summary", "") or "")

                out.write(
                    f'    <entry id="{escape_xml_attr(file_id)}" '
                    f'path="{escape_xml_attr(rel_path)}" '
                    f'kind="{escape_xml_attr(kind)}" '
                    f'size="{size_bytes}" '
                    f'lines="{line_count}" '
                    f'line_ref="{escape_xml_attr(line_ref)}" '
                    f'chunk_refs="{_xml_attr_join(chunk_refs)}" '
                    f'chunks="{chunks_count}" '
                    f'symbols="{len(symbols)}" '
                    f'imports="{len(imports)}" '
                    f'summary="{escape_xml_attr(summary)}" />\n'
                )
            out.write("  </file_index>\n")

            out.write("  <files>\n")
            for f_data in file_data_list:
                check_stop()

                rel_path = str(f_data.get("rel_path", ""))
                kind = str(f_data.get("kind", ""))
                file_id = str(f_data.get("file_id", ""))
                size_bytes = _safe_int(f_data.get("size_bytes", 0))
                line_count = _safe_int(f_data.get("line_count", 0))
                line_ref = str(f_data.get("line_ref", "") or "")
                chunk_refs = _get_chunk_refs(f_data)
                symbols = _get_symbols(f_data)
                imports = _get_imports(f_data)
                summary = str(f_data.get("summary", "") or "")

                out.write(
                    f'    <file id="{escape_xml_attr(file_id)}" '
                    f'path="{escape_xml_attr(rel_path)}" '
                    f'size="{size_bytes}" '
                    f'lines="{line_count}" '
                    f'kind="{escape_xml_attr(kind)}" '
                    f'line_ref="{escape_xml_attr(line_ref)}" '
                    f'chunk_refs="{_xml_attr_join(chunk_refs)}">\n'
                )

                _write_summary_xml(out, summary)
                _write_symbols_xml(out, symbols)
                _write_imports_xml(out, imports)

                chunks = f_data.get("chunks") or []
                chunks = chunks if isinstance(chunks, list) else []

                if chunks:
                    out.write("      <chunks>\n")
                    for c in chunks:
                        check_stop()

                        cid = escape_xml_attr(str(c.get("id", "")))
                        sline = _safe_int(c.get("start_line", 0))
                        eline = _safe_int(c.get("end_line", 0))
                        text = _chunk_text_for_output(c)

                        out.write(
                            f'        <chunk id="{cid}" start="{sline}" end="{eline}">'
                            f'{wrap_cdata(text)}</chunk>\n'
                        )
                    out.write("      </chunks>\n")
                else:
                    content = _content_for_output(f_data)
                    out.write(f"      <content>{wrap_cdata(content)}</content>\n")

                out.write("    </file>\n")

            out.write("  </files>\n")
            out.write("</volume>\n")

        # Companion behavior:
        # - If we wrote a real .xml and txt_mode=="copy", also create .xml.txt copy.
        # - If txt_mode=="only", out_path is already .xml.txt and no companion is needed.
        if (txt_mode or "").strip().lower() == "copy" and out_path.suffix.lower() == ".xml":
            maybe_write_txt_companion(src_xml_path=out_path, txt_mode=txt_mode, log=log, check_stop=check_stop)

        contained_files = [str(entry.get("rel_path", "")) for entry in file_data_list if entry.get("rel_path")]
        file_entries = [
            build_file_entry(entry, filename)
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
        log(f"Error writing XML file {filename}: {e}")
        return None
