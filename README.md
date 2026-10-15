# Hook Management System (HMS)

**Version:** `v2.6.0`  
**Target Platform:** DaVinci Resolve Free / Studio (FCP 7 `xmeml v5` Protocol)  
**Audio / Generative Stack:** Suno v5/v6, Librosa STFT, Google Flow / Veo 3.1  

---

## 📌 Overview

The **Hook Management System (HMS)** is an automated pipeline designed to bridge AI audio engines, generative video models, and non-linear editors (NLEs). It eliminates manual timeline alignment and solves DaVinci Resolve's FCPXML import bugs (such as MP4 freeze-frame holds and dropped audio tracks) by producing strict, track-isolated **FCP 7 XML (`xmeml v5`)** sequence files with embedded transient beat markers.

---

## 🛠️ Key Features (v2.6.0)

- **Master GUI Control Panel (`hms_master_gui.py`):** Desktop application with system revision tracking (`v2.6.0`) and live logging.
- **Interactive File & Folder Pickers:** Native `Browse...` buttons for selecting custom Video Directories, Metadata Folders, and Master WAV files.
- **PyInstaller Executable Builder (`build_exe.bat`):** 1-click script to compile the GUI into a standalone `hms_master_gui.exe` binary.
- **Sub-Second Audio Trimming:** Automatically cuts master WAV files down to the exact hook section starting at frame 0 (`<track_slug>_master_trimmed.wav`) to prevent audio offset dropouts in DaVinci Resolve.
- **Track-Aware File Isolation:** Naming conventions incorporate song slugs (e.g. `dear_me`, `paper_dolls`) to prevent overwriting metadata during multi-song production runs.
- **Librosa & Text Transient Engine:** Parses custom `thebeats.txt` or calculates onset envelopes dynamically, embedding blue marker pins directly on the timeline audio track.
- **FCP 7 XML Schema Enforcement:** Bypasses FCPXML 1.9 spine-nesting bugs by utilizing discrete `<track>` nodes for video and audio.

---

## 📁 Repository Structure

```text
hook-management-system/
├── README.md                   # System documentation & quickstart
├── CHANGELOG.md                # Version history & revision tracking
├── .gitignore                  # Media and log exclusions for Git
├── requirements.txt            # Python dependencies (includes PyInstaller)
├── hms_master_gui.py           # Master GUI Application (v2.6.0)
├── build_exe.bat               # 1-Click PyInstaller Executable Builder
├── build_exe.py                # Python Build Helper Script
├── run_hms_track_pipeline.py   # CLI Track-Aware Pipeline Engine
├── trim_master_audio.py        # Standalone Sub-Second Wave Trimmer
├── rename_shots.py             # Shot Sequencer (MP4 chronological renamer)
└── docs/
    └── davinci_import_sop.md   # DaVinci Resolve import protocol & SOP
```

---

## ⚙️ Quickstart & Execution

### Option 1: Run via Standalone Executable
1. Double-click **`build_exe.bat`** to generate **`dist\hms_master_gui.exe`**.
2. Run **`hms_master_gui.exe`** directly—no Python terminal required!

### Option 2: Run via Python GUI
```cmd
python hms_master_gui.py
```
Use the **Browse...** buttons to set your folders, then click **🚀 EXECUTE FULL AUTOMATED PIPELINE**.

---

## 📄 DaVinci Resolve Import Protocol

1. Open DaVinci Resolve and press **Shift + 9** to open **Project Settings**. Set frame rate to **24 fps**.
2. Press **Ctrl + Shift + I** to import `C:\renders\<track_slug>\<track_slug>_hook_timeline.xml`.
3. Enable **Snapping (N)** on the Edit Page so titles and cuts magnetically align to blue transient markers.

---

## 📝 License & Attribution

Part of the **Advanced Audiovisual Production Architecture** suite for Suno, Google Flow, and DaVinci Resolve integration.
