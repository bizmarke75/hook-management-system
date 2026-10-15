# Changelog - Hook Management System (HMS)

All notable changes to the Hook Management System (HMS) project will be documented in this file.

## [v2.6.1] - 2026-10-15

### Added
- **Automated GitHub Actions CI/CD Pipeline:** Added `.github/workflows/build_release.yml` to compile `hms_master_gui.exe` automatically in the cloud on Windows runners whenever a `v*` release tag is pushed.
- **Branded 337West Icon:** Integrated custom 3D metallic `337West` icon assets (`337west_icon.ico` and `337west_icon.png`) into PyInstaller executable builds (`build_exe.bat` and `build_exe.py`).
- **Automated GitHub Releases:** Configured `softprops/action-gh-release@v2` to publish compiled executables, SOP documentation, and CHANGELOG release notes automatically.

### Fixed
- **Windows UTF-8 Encoding Fix:** Resolved `UnicodeEncodeError: 'charmap'` failure in `build_exe.py` during GitHub Actions build execution on Windows by setting explicit UTF-8 encoding and replacing non-ASCII output symbols with clean log tags.

---

## [v2.6.0] - 2026-10-15

### Added
- **Interactive Directory Browsing:** Added native Tkinter `filedialog` support with `Browse...` buttons for Video Directory, Metadata Directory, and Master Audio WAV selection in `hms_master_gui.py`.
- **Executable Builder Engine:** Created `build_exe.bat` and `build_exe.py` scripts to package `hms_master_gui.py` into a single standalone Windows executable (`dist/hms_master_gui.exe`) via PyInstaller.
- **Dependency Manifest Update:** Added `pyinstaller>=6.0.0` to `requirements.txt`.

### Fixed
- Path handling and validation when selecting custom or non-standard folder locations outside `C:\renders\`.

---

## [v2.5.0] - 2026-10-15

### Added
- **Master GUI Control Panel:** Single-window Tkinter desktop application (`hms_master_gui.py`) consolidating shot renaming, audio trimming, beat loading, and XML generation.
- **Track Isolation Protocol:** Prefixing files with track slugs (`<track_slug>_...`) to prevent metadata overwrites across multi-song production runs.
- **Sub-Second Audio Trimming:** Automatic wave cutter to prevent DaVinci Resolve audio offset dropouts.
- **Revision Tagging Auditability:** Embedded `v2.5.0` system revision tags into FCP 7 XML root header, sequence title, and frame 0 markers.
- **Live Logging System:** Simultaneous console logging and file logging (`C:\renders\hms_workflow.log`).

---

## [v2.0.0] - 2026-10-14

### Added
- **FCP 7 XML (`xmeml v5`) Engine:** Replaced FCPXML 1.9 to bypass DaVinci Resolve MP4 freeze-frame hold bugs.
- **Track-Aware Transient Engine:** Support for parsing `thebeats.txt` and embedding blue timeline markers onto audio tracks.
- **Sequential Shot Renamer:** Chronological ordering and renaming of MP4 render clips (`shot1.mp4` through `shot5.mp4`).

---

## [v1.0.0] - 2026-10-10

### Added
- Initial proof-of-concept CLI scripts for Suno AI audio blueprinting, Google Flow video generation, and DaVinci Resolve alignment.
