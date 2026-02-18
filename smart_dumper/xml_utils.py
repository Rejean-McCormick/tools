# xml_utils.py
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List
from xml.sax.saxutils import escape


def escape_xml_attr(text: Any) -> str:
    """Escapes characters unsafe for XML attributes (includes quotes)."""
    if text is None:
        return ""
    return escape(str(text), {'"': "&quot;", "'": "&apos;"})


# Illegal XML 1.0 characters:
# - C0 controls: 0x00-0x08, 0x0B-0x0C, 0x0E-0x1F
# - C1 controls: 0x7F-0x84, 0x86-0x9F
_ILLEGAL_XML_1_0_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x84\x86-\x9F]")


def sanitize_xml_text(text: Any) -> str:
    """Remove characters that are illegal in XML 1.0 (does NOT escape markup)."""
    if text is None:
        return ""
    return _ILLEGAL_XML_1_0_RE.sub("", str(text))


def escape_xml_text(text: Any) -> str:
    """Sanitize + escape for XML element text nodes (metadata fields)."""
    return escape(sanitize_xml_text(text))


def cdata_safe(text: Any) -> str:
    """
    Sanitize + make safe for CDATA by splitting any occurrence of ']]>'.
    Preserves original text content while keeping XML well-formed.
    """
    s = sanitize_xml_text(text)
    return s.replace("]]>", "]]]]><![CDATA[>")


def wrap_cdata(text: Any) -> str:
    """Return a CDATA block with safe content."""
    return "<![CDATA[" + cdata_safe(text) + "]]>"


def short_sha1(s: str, n: int = 12) -> str:
    """Short SHA1 hex digest for stable-ish IDs."""
    return hashlib.sha1(s.encode("utf-8", errors="replace")).hexdigest()[:n]


def chunk_lines_keepends(text: str, max_lines: int) -> List[Dict[str, Any]]:
    """
    Split text into chunks of <= max_lines while preserving exact newlines.
    Returns list of {start_line, end_line, text}.
    """
    if not text:
        return [{"start_line": 1, "end_line": 0, "text": ""}]

    lines = text.splitlines(True)  # keep line endings
    out: List[Dict[str, Any]] = []
    start = 1
    i = 0
    while i < len(lines):
        part = lines[i : i + max_lines]
        end = start + len(part) - 1
        out.append({"start_line": start, "end_line": end, "text": "".join(part)})
        i += max_lines
        start = end + 1
    return out
