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

# Master index base name (worker may normalize to Index.xml.txt in txt-only modes)
INDEX_FILENAME: str = "Index.xml"

# Grouped bundle artifacts (upload helpers for file-count limits)
GROUPED_MANIFEST_FILENAME: str = "REPO_MANIFEST_GROUPED.md"
BUNDLE_GROUPS: tuple[str, ...] = ("CORE", "DOCS_TOOLS", "TESTS_OTHERS")
BUNDLE_FILENAMES: dict[str, str] = {
    "CORE": "REPO_CORE.xml.txt",
    "DOCS_TOOLS": "REPO_DOCS_TOOLS.xml.txt",
    "TESTS_OTHERS": "REPO_TESTS_OTHERS.xml.txt",
}

# Heuristic keywords for classifying volumes into bundles
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

# Whether to generate grouped upload-helper bundles by default
DEFAULT_CREATE_GROUPED_BUNDLES: bool = True