# Smart Dumper — Planned Upgrade

## Goal

Upgrade Smart Dumper so the user can inspect a selected repository folder before generating the dump, understand folder sizes on demand, and choose whether to erase a previous dump before writing a new one.

## Current Context

Smart Dumper already supports:

- selecting a repository root
- selecting an output folder
- configuring output format and dump options
- generating timestamped dump folders
- scanning top-level folders
- calculating folder sizes internally during dump planning
- writing dump volumes, index files, instructions, and optional upload-helper documents

This upgrade focuses on improving the pre-dump user experience and output overwrite behavior.

## Upgrade 1 — Folder Browser After Repository Selection

### Objective

After the user selects a repository folder, Smart Dumper should immediately display the visible folder contents in the GUI.

### Expected Behaviour

When the user selects a repository root:

1. The app scans the selected folder.
2. The GUI displays:
   - direct subfolders
   - direct files
   - basic metadata where available
3. The display should respect the same ignore logic used by the dump process as much as practical:
   - always-ignored directories
   - always-ignored extensions
   - always-ignored filenames
   - `.gitignore`
   - `.smartignore`, when enabled

### Suggested UI

Add a new panel below `Repository Root`:

```text
Repository Contents
[tree view]
  📁 worker
  📄 constants.py
  📄 gui.py
  📄 main.py