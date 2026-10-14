# PDF Editor

Free, offline PDF editor for Windows. Files never leave your computer.
License: AGPL-3.0 (required by PyMuPDF). Add the AGPL-3.0 text as a `LICENSE` file when you publish.

## Run from source
    pip install -r requirements.txt
    python app.py [file.pdf]

## Build a Windows .exe
Double-click `build_windows.bat` (needs Python 3.10+ on Windows). Output: `dist\PDFEditor\PDFEditor.exe`.

## Phase 1 features
Tabs, drag-and-drop open, password-protected PDFs, smooth zoom (Ctrl+wheel), thumbnails,
rotate, delete, reorder, merge/insert, extract pages, split into single pages, undo (Ctrl+Z), safe save.

## Shortcuts
Ctrl+O open - Ctrl+S save - Ctrl+Z undo - Ctrl+M merge - Ctrl+E extract
Ctrl+Shift+L/R rotate - Ctrl+Up/Down move pages - Ctrl+Del delete - Ctrl+= / Ctrl+- zoom - Ctrl+0 fit width

## Easiest way to get an installer (no Python needed on your PC)
1. Create a free GitHub account and a new **public** repository.
2. Upload everything in this folder (keep the `.github` folder).
3. Add a `LICENSE` file (GitHub's "Add file" > "Create new file" offers an AGPL-3.0 template).
4. On the repo's **Actions** tab, run **Build Windows installer** (or push a tag like `v0.1.0`).
5. Download `PDFEditor-Setup.exe` from the run's Artifacts, or from the **Releases** page for tagged builds.
