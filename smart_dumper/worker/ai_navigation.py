# worker/ai_navigation.py
from __future__ import annotations

import ast
from typing import Any, Dict, Iterable, List, Optional, Tuple


# Single source of truth for AI-navigation metadata names.
AI_FILE_ENTRY_KEYS: Tuple[str, ...] = (
    "path",
    "volume",
    "id",
    "kind",
    "size_bytes",
    "line_count",
    "line_ref",
    "chunk_refs",
    "symbols",
    "imports",
    "summary",
)

AI_FILE_DATA_KEYS: Tuple[str, ...] = (
    "line_ref",
    "chunk_refs",
    "symbols",
    "imports",
    "summary",
    "numbered_content",
)

AI_OPTION_KEYS: Tuple[str, ...] = (
    "ai_navigation",
    "number_source_lines",
    "create_symbol_index",
    "create_import_index",
    "create_file_summaries",
    "create_patch_targets",
    "line_number_width",
)


def build_line_ref(line_count: int) -> str:
    """
    Return the full 1-based line range for a file.

    Examples:
        0   -> ""
        1   -> "1-1"
        526 -> "1-526"
    """
    try:
        n = int(line_count)
    except Exception:
        n = 0

    if n <= 0:
        return ""
    return f"1-{n}"


def _chunk_start_end(chunk: Dict[str, Any]) -> tuple[int, int]:
    """
    Accept both current chunk keys and possible serialized variants.

    Current FileProcessor chunks use:
        start_line
        end_line

    Existing text dumps serialize those as:
        start
        end
    """
    start = chunk.get("start_line", chunk.get("start", 0))
    end = chunk.get("end_line", chunk.get("end", 0))

    try:
        start_i = int(start or 0)
    except Exception:
        start_i = 0

    try:
        end_i = int(end or 0)
    except Exception:
        end_i = 0

    return start_i, end_i


def build_chunk_refs(chunks: Optional[Iterable[Dict[str, Any]]], line_count: int = 0) -> List[str]:
    """
    Return compact line ranges for chunks.

    Example:
        [{"start_line": 1, "end_line": 350}, {"start_line": 351, "end_line": 526}]
        -> ["1-350", "351-526"]
    """
    if not chunks:
        return []

    refs: List[str] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue

        start, end = _chunk_start_end(chunk)
        if start > 0 and end >= start:
            refs.append(f"{start}-{end}")

    return refs


def format_chunk_refs(chunk_refs: Optional[Iterable[str]]) -> str:
    """
    Serialize chunk refs for text/XML attributes.
    """
    if not chunk_refs:
        return ""
    return ",".join(str(ref) for ref in chunk_refs if str(ref).strip())


def parse_chunk_refs(value: str) -> List[str]:
    """
    Parse serialized chunk refs back into a list.
    """
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def number_lines(text: str, width: int = 6) -> str:
    """
    Prefix source lines with physical line numbers.

    This is optional output. Do not replace clean `content` with this value.
    """
    try:
        width_i = max(1, int(width))
    except Exception:
        width_i = 6

    lines = str(text or "").splitlines(keepends=True)
    return "".join(f"{idx:0{width_i}d} | {line}" for idx, line in enumerate(lines, start=1))


def _parse_python_ast(content: str) -> Optional[ast.AST]:
    try:
        return ast.parse(content or "")
    except SyntaxError:
        return None
    except Exception:
        return None


def extract_python_symbols(content: str) -> List[Dict[str, Any]]:
    """
    Extract Python classes/functions with stable field names.

    Returned symbol shape:
        {
            "type": "class" | "def" | "async def",
            "name": "DumpWorker",
            "qualname": "DumpWorker.run",
            "line": 27,
            "end_line": 526,
        }
    """
    tree = _parse_python_ast(content)
    if tree is None:
        return []

    symbols: List[Dict[str, Any]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: List[str] = []

        def _add_symbol(self, node: ast.AST, symbol_type: str, name: str) -> None:
            qualname = ".".join(self.stack + [name])
            line = int(getattr(node, "lineno", 0) or 0)
            end_line = int(getattr(node, "end_lineno", line) or line)

            symbols.append(
                {
                    "type": symbol_type,
                    "name": name,
                    "qualname": qualname,
                    "line": line,
                    "end_line": end_line,
                }
            )

        def visit_ClassDef(self, node: ast.ClassDef) -> Any:
            self._add_symbol(node, "class", node.name)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
            self._add_symbol(node, "def", node.name)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
            self._add_symbol(node, "async def", node.name)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

    Visitor().visit(tree)
    symbols.sort(key=lambda item: (int(item.get("line", 0) or 0), str(item.get("qualname", ""))))
    return symbols


def extract_python_imports(content: str) -> List[Dict[str, Any]]:
    """
    Extract Python imports with stable field names.

    Returned import shape:
        {
            "kind": "import" | "from",
            "module": "pathlib",
            "name": "Path",
            "alias": "",
            "line": 5,
            "text": "from pathlib import Path",
        }
    """
    tree = _parse_python_ast(content)
    if tree is None:
        return []

    imports: List[Dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            line = int(getattr(node, "lineno", 0) or 0)
            for alias in node.names:
                module = str(alias.name or "")
                alias_name = str(alias.asname or "")
                text = f"import {module}"
                if alias_name:
                    text += f" as {alias_name}"

                imports.append(
                    {
                        "kind": "import",
                        "module": module,
                        "name": "",
                        "alias": alias_name,
                        "line": line,
                        "text": text,
                    }
                )

        elif isinstance(node, ast.ImportFrom):
            line = int(getattr(node, "lineno", 0) or 0)
            module = "." * int(node.level or 0) + str(node.module or "")

            for alias in node.names:
                name = str(alias.name or "")
                alias_name = str(alias.asname or "")
                text = f"from {module} import {name}"
                if alias_name:
                    text += f" as {alias_name}"

                imports.append(
                    {
                        "kind": "from",
                        "module": module,
                        "name": name,
                        "alias": alias_name,
                        "line": line,
                        "text": text,
                    }
                )

    imports.sort(key=lambda item: (int(item.get("line", 0) or 0), str(item.get("text", ""))))
    return imports


def summarize_file(
    rel_path: str,
    kind: str,
    symbols: Optional[List[Dict[str, Any]]] = None,
    imports: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Build a short deterministic summary without calling external services.
    """
    path = str(rel_path or "")
    kind_s = str(kind or "")
    symbols = symbols or []
    imports = imports or []

    if kind_s == "list_name_only":
        return "Path listed without content."
    if kind_s == "metadata_only":
        return "Metadata-only entry; content omitted."
    if kind_s == "oversized":
        return "Oversized file; content omitted."
    if kind_s == "error":
        return "File processing error entry."

    if path.endswith(".md") or kind_s == "markdown":
        return "Markdown documentation."

    if path.endswith(".py"):
        class_count = sum(1 for s in symbols if s.get("type") == "class")
        def_count = sum(1 for s in symbols if s.get("type") in ("def", "async def"))

        if class_count and def_count:
            return f"Python module with {class_count} class(es) and {def_count} function(s)."
        if class_count:
            return f"Python module with {class_count} class(es)."
        if def_count:
            return f"Python module with {def_count} function(s)."
        if imports:
            return "Python module with imports and top-level code."
        return "Python module."

    if kind_s == "source":
        return "Source file."

    return kind_s.replace("_", " ").strip() or "File."


def enrich_file_data(
    file_data: Dict[str, Any],
    *,
    source_content: str,
    ai_navigation: bool = True,
    number_source_lines: bool = False,
    create_symbol_index: bool = True,
    create_import_index: bool = True,
    create_file_summaries: bool = True,
    line_number_width: int = 6,
) -> Dict[str, Any]:
    """
    Return a copy of file_data with AI-navigation fields added.

    Use this inside FileProcessor before clearing `content` for chunked files.
    """
    out = dict(file_data)

    rel_path = str(out.get("rel_path", "") or "")
    kind = str(out.get("kind", "") or "")
    ext = str(out.get("ext", "") or "")
    line_count = int(out.get("line_count", 0) or 0)
    chunks = out.get("chunks") or []

    line_ref = build_line_ref(line_count) if ai_navigation else ""
    chunk_refs = build_chunk_refs(chunks, line_count) if ai_navigation else []

    should_parse_python = bool(
        ai_navigation
        and kind in ("source", "markdown")
        and ext == ".py"
        and source_content
    )

    symbols: List[Dict[str, Any]] = []
    imports: List[Dict[str, Any]] = []

    if should_parse_python and create_symbol_index:
        symbols = extract_python_symbols(source_content)

    if should_parse_python and create_import_index:
        imports = extract_python_imports(source_content)

    summary = ""
    if ai_navigation and create_file_summaries:
        summary = summarize_file(rel_path, kind, symbols, imports)

    numbered_content = ""
    if number_source_lines and source_content and kind in ("source", "markdown"):
        numbered_content = number_lines(source_content, line_number_width)

    out["line_ref"] = line_ref
    out["chunk_refs"] = chunk_refs
    out["symbols"] = symbols
    out["imports"] = imports
    out["summary"] = summary
    out["numbered_content"] = numbered_content

    return out


def build_file_entry(file_data: Dict[str, Any], volume_filename: str) -> Dict[str, Any]:
    """
    Build the normalized metadata entry used by writers and the master index.
    """
    return {
        "path": str(file_data.get("rel_path", "") or ""),
        "volume": str(volume_filename or ""),
        "id": str(file_data.get("file_id", "") or ""),
        "kind": str(file_data.get("kind", "") or ""),
        "size_bytes": int(file_data.get("size_bytes", 0) or 0),
        "line_count": int(file_data.get("line_count", 0) or 0),
        "line_ref": str(file_data.get("line_ref", "") or ""),
        "chunk_refs": list(file_data.get("chunk_refs", []) or []),
        "symbols": list(file_data.get("symbols", []) or []),
        "imports": list(file_data.get("imports", []) or []),
        "summary": str(file_data.get("summary", "") or ""),
    }


def build_file_entries(file_data_list: Iterable[Dict[str, Any]], volume_filename: str) -> List[Dict[str, Any]]:
    """
    Build normalized entries for a full volume.
    """
    return [build_file_entry(file_data, volume_filename) for file_data in file_data_list]


def symbol_count(file_data_or_entry: Dict[str, Any]) -> int:
    return len(file_data_or_entry.get("symbols") or [])


def import_count(file_data_or_entry: Dict[str, Any]) -> int:
    return len(file_data_or_entry.get("imports") or [])


def compact_summary(summary: str) -> str:
    """
    Keep single-line metadata safe for FILE_INDEX style lines.
    """
    return " ".join(str(summary or "").replace('"', "'").split())


def format_import_text(import_entry: Dict[str, Any]) -> str:
    """
    Prefer prebuilt import text, but rebuild it if missing.
    """
    text = str(import_entry.get("text", "") or "").strip()
    if text:
        return text

    kind = str(import_entry.get("kind", "") or "")
    module = str(import_entry.get("module", "") or "")
    name = str(import_entry.get("name", "") or "")
    alias = str(import_entry.get("alias", "") or "")

    if kind == "from":
        text = f"from {module} import {name}".strip()
    else:
        text = f"import {module}".strip()

    if alias:
        text += f" as {alias}"

    return text
