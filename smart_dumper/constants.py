# smart_wiki_dumper/constants.py
from __future__ import annotations

# Folders always excluded from scanning
ALWAYS_IGNORE_DIRS: set[str] = {
    ".git", ".svn", ".hg", ".idea", ".vscode", ".ipynb_checkpoints",
    "node_modules", "venv", ".venv", "env",
    "__pycache__", ".mypy_cache", ".pytest_cache",
    "dist", "build", "coverage", "target", "out",
    "abstract_wiki_architect.egg-info",
    "WEB-INF", "classes", "lib", "bin", "obj",
}

# Extensions always excluded from dumping
ALWAYS_IGNORE_EXT: set[str] = {
    ".pyc", ".pyo", ".pyd", ".exe", ".dll", ".so", ".dylib", ".class", ".jar", ".war",
    ".bin", ".iso", ".img", ".log", ".sqlite", ".db", ".zip", ".gz", ".tar",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".lock", ".pdf", ".mp4", ".mp3",
}

# Specific filenames always excluded
ALWAYS_IGNORE_FILES: set[str] = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "composer.lock",
    "Gemfile.lock", "poetry.lock", "Cargo.lock", ".DS_Store", "Thumbs.db",
    "Entity", "Fact", "Modifier", "Predicate", "Property",
}

# Name chosen to sort first + be explicit
INSTRUCTIONS_FILENAME: str = "00_START_HERE.instructions.md"

# Chunking settings (AI-friendly)
CHUNK_MAX_LINES: int = 350

# If a file is larger than this, it’s marked as oversized and content is not embedded
OVERSIZE_BYTES: int = 5_000_000
