# Hook Management System (HMS)

**Version:** `v2.8.0`  
**Target Platform:** DaVinci Resolve Free / Studio (FCP 7 `xmeml v5` Protocol)  
**Audio / Generative Stack:** Suno v5/v6, Librosa STFT, Google Flow / Veo 3.1  

---

## 📌 Overview

The **Hook Management System (HMS)** is an automated pipeline designed to bridge AI audio engines, generative video models, and non-linear editors (NLEs). It eliminates manual timeline alignment and solves DaVinci Resolve's FCPXML import bugs by producing strict, track-isolated **FCP 7 XML (`xmeml v5`)** sequence files with embedded transient beat markers.

---

## 🛠️ Key Features (v2.8.0)

- **Master GUI Control Panel (`hms_master_gui.py` v2.8.0):** Unified Tkinter desktop application with interactive directory browsing, automatic track slug/title generation from audio WAV files, and live console logging.
- **Interactive File & Directory Browsing:** Dedicated `Browse...` buttons for Video Shots Directory, Metadata Directory, and Master Audio WAV.
- **Automatic Metadata Auto-Fill:** Selecting a Master Audio WAV automatically cleans file suffixes (`_master`, `_trimmed`) and populates Track Slug, Track Title, and suggested Video Shots Directory.
- **Multi-Output Archiving:** Automatically saves both primary timeline files (`<track_slug>_hook_timeline.xml`) and timestamped revision copies (`<track_slug>_hook_timeline_v2.8.0_<timestamp>.xml`) into dedicated `archive/` subfolders.
- **Dynamic MP4 Shot Detection & Duration Engine:** Automatically scans for all `shot*.mp4` files in your video directory, measuring frame count and duration dynamically.
- **Sub-Second Audio Trimming:** Automatically cuts master WAV files down to the exact hook section starting at frame 0 (`<track_slug>_master_trimmed.wav`) to prevent audio offset dropouts in DaVinci Resolve.
- **Automated GitHub Release Suite (`publish_release.bat` & `publish_release.ps1`):** One-click Git commit, tag, and trigger for automated GitHub Actions executable compilation.

---

## 📁 Repository Architecture

```text
hook-management-system/
├── README.md                   # System documentation & DaVinci Resolve SOP
├── CHANGELOG.md                # Full revision history
├── requirements.txt            # Python dependencies (includes pyinstaller & opencv-python)
├── hms_master_gui.py           # Master GUI Application (v2.8.0)
├── build_exe.py                # PyInstaller standalone compilation script
├── build_exe.bat               # Windows batch launcher for build_exe.py
├── publish_release.bat         # Automated GitHub release batch launcher
├── publish_release.ps1         # Automated PowerShell Git tag & release script
├── run_hms_track_pipeline.py   # CLI Track-Aware Pipeline Engine
├── trim_master_audio.py        # Standalone Sub-Second Wave Trimmer
├── rename_shots.py             # Shot Sequencer (MP4 chronological renamer)
└── docs/
    └── davinci_import_sop.md   # Step-by-step import protocol
```

---

## ⚙️ Standard Operating Procedure (SOP) for DaVinci Resolve

### 1. File Preparation
Place track media according to the following conventions:
- **Video Renders:** `C:\renders\<track_slug>\shot1.mp4` through `shotN.mp4`
- **Master Audio:** `C:\audio\<track_slug>_master.wav`
- **Transient Data:** `C:\renders\output\<track_slug>_thebeats.txt` & `<track_slug>_hooktimestamp.txt`

### 2. Execution via Master GUI
Run the GUI control panel:
```cmd
python hms_master_gui.py
```
Or run `hms_master_gui.exe`. Click **Browse...** next to Master Audio WAV to select your WAV file. HMS will automatically auto-fill the Track Slug, Track Title, and Video Shots Directory. Click **🚀 EXECUTE FULL AUTOMATED PIPELINE**.

### 3. DaVinci Resolve Timeline Import
1. Open DaVinci Resolve and press **Shift + 9** (Project Settings). Set Timeline Frame Rate to **24 fps**.
2. Press **Ctrl + Shift + I** (or go to **File > Import > Timeline...**).
3. Select `C:\renders\<track_slug>\<track_slug>_hook_timeline.xml`.
4. Enable **Snapping (N)** on the Edit Page so cuts and speed ramps magnetically snap to the blue beat markers.
