# Hook Management System (HMS) Architecture

Automated concept-to-production pipeline for Suno AI music blueprinting, Google Flow (Veo 3.1 & Gemini Omni Flash) video generation, and DaVinci Resolve post-production synchronization.

---

## 🚀 Key Capabilities (v2.7.0)

- **Master Control Panel GUI (`hms_master_gui.py`):** Single-window Tkinter desktop app for track workflow automation.
- **Dynamic Shot Discovery:** Automatically detects any number of `shot*.mp4` files (e.g. 4 shots at 10s each) and reads exact clip durations from MP4 file headers.
- **Freeze-Frame Prevention:** FCP 7 XML (`xmeml v5`) generator explicitly embeds `<duration>` and `<samplecharacteristics>` tags in video `<file>` definitions to prevent DaVinci Resolve from importing MP4s as static still holds.
- **Track Isolation & Revision Auditability:** Prefixing track slugs (`<slug>_...`) and embedding system revision tags (`v2.7.0`) into FCP 7 XML root headers and timeline markers.
- **Sub-Second Audio Trimming:** Trims master WAV tracks to exact hook offsets to eliminate timeline drift.
- **Cloud Automated Executables:** Automated Windows executable build and GitHub Release publishing via `.github/workflows/build_release.yml`.

---

## 🛠️ Installation & Windows Executable Build

### Running Python Script Directly
```cmd
python hms_master_gui.py
```

### Local Windows Executable Build (`.exe`)
To package `hms_master_gui.py` into a standalone Windows executable with the **337West** custom icon:

```cmd
build_exe.bat
```
*Output executable will be generated at `dist\hms_master_gui.exe`.*

---

## 📦 Automated Release via GitHub Actions

Push a version tag to trigger a cloud build and automatically attach `hms_master_gui.exe` to your GitHub Releases page:

```powershell
git tag v2.7.0
git push origin v2.7.0
```

---

## 📄 Repository Structure

```text
hook-management-system/
├── hms_master_gui.py         # Control Panel Application v2.7.0
├── README.md                 # Project Documentation
├── CHANGELOG.md              # Revision History
├── 337west_icon.ico          # Windows Executable Icon
├── build_exe.py              # PyInstaller Python Build Script
├── build_exe.bat             # Batch Executable Launcher
├── requirements.txt          # Dependency Manifest
└── .github/
    └── workflows/
        └── build_release.yml # GitHub Actions Release Workflow
```
