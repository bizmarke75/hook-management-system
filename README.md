# Hook Management System (HMS) - Master Automation Architecture

## Overview

The **Hook Management System (HMS)** is a professional automation pipeline designed for AI music video creators, video editors, and audio engineers. HMS bridges Suno AI audio generation, Google Flow / Veo 3 video renders, and DaVinci Resolve (Free & Studio) post-production timelines.

It solves sub-second audio offset drift, frame-accurate beat markers, sequential shot ordering, and FCPXML timeline freeze-frame bugs in a single desktop GUI application or standalone executable.

---

## Key Features in v2.6.1

- **Single-Window Desktop GUI (v2.6.1):** Consolidated Tkinter control panel (`hms_master_gui.py`) with interactive `Browse...` file pickers for directories and WAV files.
- **Branded Executable Packaging:** Standalone Windows `.exe` build support via `build_exe.bat` or `build_exe.py` featuring custom 3D metallic **337West** icon branding.
- **Automated Cloud Releases (GitHub Actions):** `.github/workflows/build_release.yml` automatically compiles the `.exe` and publishes GitHub Releases on version tag pushes (`v*`).
- **Track-Aware Audio & Transient Sync:** Sub-second WAV audio trimmer (`<slug>_master_trimmed.wav`) and track-isolated transient beat pin loader (`<slug>_thebeats.txt`).
- **FCP 7 XML Engine (`xmeml v5`):** Generates clean multi-track timelines (`<slug>_hook_timeline.xml`) compatible with DaVinci Resolve Free Edition without freeze-frame hold bugs.

---

## Repository Structure

```text
C:\github\projects\hook-management-system\
├── hms_master_gui.py              # Master GUI Application (v2.6.1)
├── build_exe.py                   # PyInstaller UTF-8 build script
├── build_exe.bat                  # 1-click Windows EXE builder
├── 337west_icon.ico               # Multi-resolution 337West app icon
├── 337west_icon.png               # High-res 337West graphic badge
├── README.md                      # Main project documentation
├── CHANGELOG.md                   # System version history
├── requirements.txt               # Dependencies (pyinstaller, librosa, numpy)
├── .gitignore                     # Git filter for renders and temporary builds
├── .github\
│   └── workflows\
│       └── build_release.yml      # GitHub Actions automated release pipeline
└── docs\
    └── davinci_import_sop.md      # DaVinci Resolve 4-step import SOP
```

---

## Quickstart Guide

### Option 1: Run Standalone Executable
1. Download `hms_master_gui.exe` from your GitHub Releases page.
2. Double-click `hms_master_gui.exe` to launch the GUI control panel.

### Option 2: Run Python Script
```cmd
cd C:\github\projects\hook-management-system
pip install -r requirements.txt
python hms_master_gui.py
```

### Option 3: Build `.exe` Locally
```cmd
build_exe.bat
```
*(Outputs `dist/hms_master_gui.exe` with embedded 337West icon)*

---

## License & Attribution

Developed by 337West for the Hook Management System architecture. Licensed under Apache 2.0.
