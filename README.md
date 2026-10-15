# Hook Management System (HMS) Architecture

System Revision: v2.6.2

An automated audiovisual post-production pipeline connecting Suno AI audio engines, Google Flow generative video models, and DaVinci Resolve Free/Studio via track-isolated FCP 7 XML (xmeml v5) synchronization.

---

## Key Features

* **Master GUI Control Panel (hms_master_gui.py / hms_master_gui.exe):** Single-window Tkinter desktop control center with native Browse... directory pickers and live execution logging console.
* **Sub-Second Audio Trimming:** Automatically cuts hook segments from master WAV files, bypassing DaVinci Resolve sub-second audio dropouts.
* **Sequential Shot Renamer:** Chronologically orders and renames generated MP4 video clips (shot1.mp4 through shot5.mp4).
* **Track-Aware Beat & Transient Marker Loading:** Converts onset timestamps into magnetic blue timeline markers on audio track A1.
* **FCP 7 XML (xmeml v5) Engine:** Uses discrete track blocks to eliminate FCPXML video freeze-frame hold bugs.
* **1-Click Standalone Executable Packaging:** Package into a single Windows executable using build_exe.bat or automated GitHub Actions cloud builds.

---

## Repository Structure

```text
C:\github\projects\hook-management-system\
├── hms_master_gui.py         # Master Control Panel Application (v2.6.2)
├── README.md                 # System architecture documentation
├── CHANGELOG.md              # Version release history
├── 337west_icon.ico          # Custom 3D metallic 337West executable icon
├── 337west_icon.png          # High-resolution branding graphic
├── build_exe.bat             # 1-click Windows PyInstaller build script
├── build_exe.py              # Python build script engine
├── requirements.txt          # Python dependency manifest
├── .gitignore                # Filter for heavy render outputs
├── .github\
│   └── workflows\
│       └── build_release.yml # Automated GitHub Actions release workflow
└── docs\
    └── davinci_import_sop.md # DaVinci Resolve import SOP
```

---

## Quick Start

### Option 1: Run the Standalone .exe
Download `hms_master_gui.exe` from the GitHub Releases page and double-click to launch!

### Option 2: Run via Python
```cmd
pip install -r requirements.txt
python hms_master_gui.py
```

### Option 3: Build Your Own .exe Locally
```cmd
build_exe.bat
```
Your compiled application will be generated in `dist\hms_master_gui.exe`.
