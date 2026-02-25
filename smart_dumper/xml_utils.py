# xml_utils.py
from __future__ import annotations

import hashlib
from typing import Any, Dict, List
from xml.sax.saxutils import escape


def _is_xml10_char(cp: int) -> bool:
    """
    XML 1.0 (5th ed.) legal characters:
      - 0x9, 0xA, 0xD
      - 0x20..0xD7FF
      - 0xE000..0xFFFD
      - 0x10000..0x10FFFF
    Additionally, exclude Unicode noncharacters ending in FFFE/FFFF for extra parser-compat.
    """
    if cp in (0x9, 0xA, 0xD):
        return True
    if 0x20 <= cp <= 0xD7FF:
        return True
    if 0xE000 <= cp <= 0xFFFD:
        return True
    if 0x10000 <= cp <= 0x10FFFF:
        # Exclude plane noncharacters ...FFFE / ...FFFF
        if (cp & 0xFFFF) in (0xFFFE, 0xFFFF):
            return False
        return True
    return False


def sanitize_xml_text(text: Any) -> str:
    """
    Remove characters illegal in XML 1.0 (does NOT escape markup).
    This makes output robust against:
      - C0/C1 controls
      - unpaired surrogates
      - out-of-range codepoints (defensive)
      - common Unicode noncharacters (...FFFE/...FFFF)
    """
    if text is None:
        return ""

    s = str(text)

    # Fast path: if likely clean ASCII, avoid extra work.
    # (Most paths/metadata are ASCII; large file contents still go through filtering.)
    try:
        s.encode("ascii")
        # ASCII still contains illegal controls; filter quickly.
        out_chars = []
        append = out_chars.append
        for ch in s:
            cp = ord(ch)
            if _is_xml10_char(cp):
                append(ch)
        return "".join(out_chars)
    except Exception:
        pass

    out_chars = []
    append = out_chars.append
    for ch in s:
        cp = ord(ch)
        if _is_xml10_char(cp):
            append(ch)
    return "".join(out_chars)


def escape_xml_text(text: Any) -> str:
    """Sanitize + escape for XML element text nodes (metadata fields)."""
    return escape(sanitize_xml_text(text))


def escape_xml_attr(text: Any) -> str:
    """Sanitize + escape for XML attributes (includes quotes)."""
    if text is None:
        return ""
    return escape(sanitize_xml_text(text), {'"': "&quot;", "'": "&apos;"})


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