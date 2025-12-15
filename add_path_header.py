import os
import sys

# 1. CONFIGURE YOUR IGNORE LIST
# Folders to skip entirely (prevents traversing huge dependency trees)
IGNORE_DIRS = {'.git', 'node_modules', '__pycache__', 'venv', 'env', 'dist', 'build', '.idea', '.vscode', 'target'}
# Files to skip
IGNORE_FILES = {'.DS_Store', 'add_path_header.py', 'requirements.txt', 'LICENSE', 'README.md'}

# 2. CONFIGURE COMMENT SYNTAX
# format: extension: (prefix, suffix)
COMMENT_SYNTAX = {
    # Hash style (Python, Shell, Ruby, YAML, Docker)
    '.py': ('#', ''),
    '.sh': ('#', ''),
    '.yaml': ('#', ''),
    '.yml': ('#', ''),
    '.rb': ('#', ''),
    '.dockerfile': ('#', ''),
    '.make': ('#', ''),
    '.pl': ('#', ''),
    
    # Double Slash style (JS, C++, Java, Go, Rust, PHP, Swift)
    '.js': ('//', ''),
    '.ts': ('//', ''),
    '.jsx': ('//', ''),
    '.tsx': ('//', ''),
    '.c': ('//', ''),
    '.cpp': ('//', ''),
    '.h': ('//', ''),
    '.cs': ('//', ''),
    '.java': ('//', ''),
    '.go': ('//', ''),
    '.rs': ('//', ''),
    '.php': ('//', ''),
    '.swift': ('//', ''),
    '.kt': ('//', ''),  # Kotlin
    '.scala': ('//', ''),
    '.dart': ('//', ''),

    # Block style (HTML, XML, Markdown)
    '.html': (''),
    '.xml': (''),
    '.md': (''),
    
    # CSS style
    '.css': ('/*', '*/'),
    '.scss': ('/*', '*/'),
    
    # SQL / Lua
    '.sql': ('--', ''),
    '.lua': ('--', '')
}

def get_comment_syntax(filename):
    _, ext = os.path.splitext(filename)
    return COMMENT_SYNTAX.get(ext.lower())

def process_file(filepath):
    # Calculate relative path from the script execution location
    rel_path = os.path.relpath(filepath, start=os.getcwd())
    
    # Get syntax for this file type
    syntax = get_comment_syntax(filepath)
    if not syntax:
        # Unknown file type, skip silently
        return 

    prefix, suffix = syntax
    expected_comment = f"{prefix} {rel_path} {suffix}".strip()

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        print(f"⚠️  Skipping binary or non-utf8 file: {rel_path}")
        return
    except Exception as e:
        print(f"⚠️  Error reading {rel_path}: {e}")
        return

    if not lines:
        # Empty file: just add the header
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(expected_comment + '\n')
        print(f"✅ Added header to empty file: {rel_path}")
        return

    # Check for Shebang (e.g., #!/bin/bash) on line 1
    insert_idx = 0
    if lines[0].startswith("#!"):
        insert_idx = 1
    
    # Check if the relevant line already has the path
    # We check usually the first line, or second if shebang exists
    if len(lines) > insert_idx:
        current_line = lines[insert_idx].strip()
        # If the path is already in the comment, skip it
        if rel_path in current_line:
            return

    # Prepare new content
    new_line = expected_comment + '\n'
    lines.insert(insert_idx, new_line)

    # Write back to file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"✏️  Updated: {rel_path}")

def main():
    root_dir = os.getcwd()
    
    for root, dirs, files in os.walk(root_dir):
        # Modify dirs in-place to skip ignored folders
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file in files:
            if file in IGNORE_FILES:
                continue
                
            filepath = os.path.join(root, file)
            process_file(filepath)

if __name__ == "__main__":
    print("🚀 Starting header check...")
    main()
    print("🏁 Done.")