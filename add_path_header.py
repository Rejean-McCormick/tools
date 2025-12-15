import os
import sys
import fnmatch

# 1. CONFIGURE YOUR IGNORE LIST
# (These are kept as a fallback or for non-git projects)
DEFAULT_IGNORE_DIRS = {'.git', 'node_modules', '__pycache__', 'venv', 'env', 'dist', 'build', '.idea', '.vscode', 'target'}
DEFAULT_IGNORE_FILES = {'.DS_Store', 'add_path_header.py', 'requirements.txt', 'LICENSE', 'README.md'}

# 2. CONFIGURE COMMENT SYNTAX
COMMENT_SYNTAX = {
    # Hash style
    '.py': ('#', ''), '.sh': ('#', ''), '.yaml': ('#', ''), '.yml': ('#', ''),
    '.rb': ('#', ''), '.dockerfile': ('#', ''), '.make': ('#', ''), '.pl': ('#', ''),
    
    # Double Slash style
    '.js': ('//', ''), '.ts': ('//', ''), '.jsx': ('//', ''), '.tsx': ('//', ''),
    '.c': ('//', ''), '.cpp': ('//', ''), '.h': ('//', ''), '.cs': ('//', ''),
    '.java': ('//', ''), '.go': ('//', ''), '.rs': ('//', ''), '.php': ('//', ''),
    '.swift': ('//', ''), '.kt': ('//', ''), '.scala': ('//', ''), '.dart': ('//', ''),

    # Block style
    '.html': (''), '.xml': (''), '.md': (''),
    
    # CSS style
    '.css': ('/*', '*/'), '.scss': ('/*', '*/'),
    
    # SQL / Lua
    '.sql': ('--', ''), '.lua': ('--', '')
}

def get_comment_syntax(filename):
    _, ext = os.path.splitext(filename)
    return COMMENT_SYNTAX.get(ext.lower())

def load_gitignore(root_dir):
    """
    Reads the .gitignore file from root_dir and returns a list of patterns.
    """
    gitignore_path = os.path.join(root_dir, '.gitignore')
    patterns = []
    
    if os.path.exists(gitignore_path):
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue
                    patterns.append(line)
            print(f"ℹ️  Loaded .gitignore with {len(patterns)} patterns.")
        except Exception as e:
            print(f"⚠️  Could not read .gitignore: {e}")
            
    return patterns

def is_ignored(path, root_dir, patterns, is_dir=False):
    """
    Checks if a path matches any gitignore pattern or default ignores.
    """
    name = os.path.basename(path)
    
    # 1. Check Hardcoded Defaults first
    if is_dir and name in DEFAULT_IGNORE_DIRS:
        return True
    if not is_dir and name in DEFAULT_IGNORE_FILES:
        return True
        
    # 2. Check .gitignore patterns
    # We need the path relative to the root for correct matching
    rel_path = os.path.relpath(path, root_dir)
    
    # Normalize path separators for Windows compatibility
    rel_path = rel_path.replace(os.sep, '/')
    
    for pattern in patterns:
        # Handle directory-specific patterns (ending with /)
        if pattern.endswith('/'):
            if not is_dir:
                continue
            pattern = pattern.rstrip('/')
            
        # fnmatch allows wildcards like *.py, dist/*, etc.
        # We check both the full relative path and just the filename
        # to cover cases like "file.txt" (anywhere) vs "lib/file.txt" (specific)
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_path, pattern):
            return True
            
    return False

def process_file(filepath):
    rel_path = os.path.relpath(filepath, start=os.getcwd())
    syntax = get_comment_syntax(filepath)
    
    if not syntax:
        return 

    prefix, suffix = syntax
    expected_comment = f"{prefix} {rel_path} {suffix}".strip()

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        # Silently skip read errors (binary files etc)
        return

    if not lines:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(expected_comment + '\n')
        print(f"✅ Added header to empty file: {rel_path}")
        return

    # Check for Shebang
    insert_idx = 0
    if lines[0].startswith("#!"):
        insert_idx = 1
    
    # Check if header exists
    if len(lines) > insert_idx:
        if rel_path in lines[insert_idx]:
            return

    # Insert header
    lines.insert(insert_idx, expected_comment + '\n')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"✏️  Updated: {rel_path}")

def main():
    root_dir = os.getcwd()
    ignore_patterns = load_gitignore(root_dir)
    
    for root, dirs, files in os.walk(root_dir):
        # 1. Filter Directories (in-place) to prevent traversing ignored trees
        # We iterate backwards to safely remove items from the list we are iterating
        for i in range(len(dirs) - 1, -1, -1):
            dir_path = os.path.join(root, dirs[i])
            if is_ignored(dir_path, root_dir, ignore_patterns, is_dir=True):
                dirs.pop(i) # Remove directory from traversal
        
        # 2. Process Files
        for file in files:
            file_path = os.path.join(root, file)
            if is_ignored(file_path, root_dir, ignore_patterns, is_dir=False):
                continue
                
            process_file(file_path)

if __name__ == "__main__":
    print("🚀 Starting header check with gitignore support...")
    main()
    print("🏁 Done.")