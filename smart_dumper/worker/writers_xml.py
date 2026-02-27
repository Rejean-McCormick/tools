# worker/writers_xml.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..xml_utils import escape_xml_attr, escape_xml_text, wrap_cdata


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
    Writes an XML volume and returns meta (same shape as legacy worker.py).
    Expects file_data_list already prepared (incl chunks/content/kind/file_id).
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

        # Companion behavior:
        # - If we wrote a real .xml and txt_mode=="copy", also create .xml.txt copy.
        # - If txt_mode=="only", out_path is already .xml.txt and no companion is needed.
        if (txt_mode or "").strip().lower() == "copy" and out_path.suffix.lower() == ".xml":
            maybe_write_txt_companion(src_xml_path=out_path, txt_mode=txt_mode, log=log, check_stop=check_stop)

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
        log(f"Error writing XML file {filename}: {e}")
        return None