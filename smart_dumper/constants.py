# smart_wiki_dumper/constants.py
from __future__ import annotations

# -----------------------------
# Scanning / filtering defaults
# -----------------------------

# Folders always excluded from scanning
ALWAYS_IGNORE_DIRS: set[str] = {
    ".git",
    ".svn",
    ".hg",
    ".idea",
    ".vscode",
    ".ipynb_checkpoints",
    "node_modules",
    "venv",
    ".venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    "coverage",
    "target",
    "out",
    "abstract_wiki_architect.egg-info",
    "WEB-INF",
    "classes",
    "lib",
    "bin",
    "obj",
}

# Extensions always excluded from dumping
ALWAYS_IGNORE_EXT: set[str] = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".class",
    ".jar",
    ".war",
    ".bin",
    ".iso",
    ".img",
    ".log",
    ".sqlite",
    ".db",
    ".zip",
    ".gz",
    ".tar",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".lock",
    ".pdf",
    ".mp4",
    ".mp3",
}

# Specific filenames always excluded
ALWAYS_IGNORE_FILES: set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "composer.lock",
    "Gemfile.lock",
    "poetry.lock",
    "Cargo.lock",
    ".DS_Store",
    "Thumbs.db",
    # Domain-specific generated artifacts / noisy files
    "Entity",
    "Fact",
    "Modifier",
    "Predicate",
    "Property",
}

# -----------------------------
# Output naming / AI navigation
# -----------------------------

# Name chosen to sort first + be explicit
INSTRUCTIONS_FILENAME: str = "00_START_HERE.instructions.md"

# Master index base name (DumpWorker decides actual filename based on output_format/txt_mode)
INDEX_FILENAME_TEXT: str = "Index.txt"
INDEX_FILENAME_XML: str = "Index.xml"
INDEX_FILENAME: str = INDEX_FILENAME_TEXT

# -----------------------------
# ChatGPT Upload Helper (single doc)
# -----------------------------
# Goal: 1 file that regroups everything, named: "Doc" + <parent folder name>
#
# Notes:
# - "parent folder name" should be computed by the worker from the selected repo root:
#     parent_name = root_dir.parent.name
# - Filename should be built as:
#     f"{UPLOAD_HELPER_DOC_PREFIX}{UPLOAD_HELPER_DOC_JOINER}{parent_name}{ext}"
#   where ext depends on output mode (text vs xml+txt).

UPLOAD_HELPER_DOC_PREFIX: str = "Doc"
# Empty string => exact "Doc"+"ParentName" concatenation
UPLOAD_HELPER_DOC_JOINER: str = ""
# Base template without extension
UPLOAD_HELPER_DOC_BASENAME_TEMPLATE: str = "{prefix}{joiner}{parent_name}"

# Default UI/worker option: create the single upload-helper doc
DEFAULT_CREATE_SINGLE_UPLOAD_DOC: bool = False

# -----------------------------
# Legacy: Grouped bundle artifacts (deprecated)
# -----------------------------
# Kept for backward compatibility while the codebase transitions to the single-doc helper.

GROUPED_MANIFEST_FILENAME: str = "REPO_MANIFEST_GROUPED.md"

BUNDLE_GROUPS: tuple[str, ...] = ("CORE", "DOCS_TOOLS", "TESTS_OTHERS")

BUNDLE_BASENAMES: dict[str, str] = {
    "CORE": "REPO_CORE",
    "DOCS_TOOLS": "REPO_DOCS_TOOLS",
    "TESTS_OTHERS": "REPO_TESTS_OTHERS",
}

# Convenient per-mode filenames (some legacy code assumed .xml.txt)
BUNDLE_FILENAMES_TEXT: dict[str, str] = {k: f"{v}.txt" for k, v in BUNDLE_BASENAMES.items()}
BUNDLE_FILENAMES_XMLTXT: dict[str, str] = {k: f"{v}.xml.txt" for k, v in BUNDLE_BASENAMES.items()}

# Backward-compat alias (historically .xml.txt)
BUNDLE_FILENAMES: dict[str, str] = dict(BUNDLE_FILENAMES_XMLTXT)

BUNDLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "CORE": ("app", "frontend", "ui", "client", "schema", "schemas", "core"),
    "DOCS_TOOLS": ("doc", "docs", "readme", "guide", "manual", "tool", "tools", "script", "scripts"),
    "TESTS_OTHERS": ("test", "tests", "spec", "root", "other", "others", "misc"),
}

# -----------------------------
# Chunking / size limits
# -----------------------------

# Chunking settings (AI-friendly)
CHUNK_MAX_LINES: int = 350

# If a file is larger than this, it’s marked as oversized and content is not embedded
OVERSIZE_BYTES: int = 5_000_000

# -----------------------------
# ChatGPT indexing workarounds
# -----------------------------

# txt_mode behavior used by DumpWorker:
#   - "none": only .xml outputs
#   - "copy": write .xml AND also .xml.txt companions (best indexing, more files)
#   - "only": write only .xml.txt (best for file-count limits)
DEFAULT_TXT_MODE: str = "copy"

# Backward-compat alias (to be removed once GUI/worker stop using grouped bundles)
DEFAULT_CREATE_GROUPED_BUNDLES: bool = DEFAULT_CREATE_SINGLE_UPLOAD_DOC