# Changelog - Hook Management System (HMS)

All notable changes to the Hook Management System (HMS) project will be documented in this file.

## [v2.6.2] - 2026-10-15

### Fixed
- **`--noconsole` GUI Execution Logging Crash:** Resolved a critical bug where launching `hms_master_gui.exe` in GUI mode (`--noconsole`) caused `sys.stdout` to be `None`, throwing an unhandled `AttributeError` on `print()` calls inside `HMSLogger.log()`.
- **Dual Console & File Logging:** Added safe I/O stream redirection for `sys.stdout` and `sys.stderr` to `io.StringIO()`. Logs are now reliably displayed in the Tkinter live console text widget and saved to `C:\renders\hms_workflow.log` even when running without a command console open.

---

## [v2.6.1] - 2026-10-15

### Added
- **Automated CI/CD Release Pipeline:** Added `.github/workflows/build_release.yml` to automatically build `hms_master_gui.exe` using PyInstaller on a cloud Windows runner upon pushing version tags (`v*`).
- **337West Executable Branding:** Embedded the custom high-resolution 3D metallic 337West icon (`337west_icon.ico`) into the compiled Windows executable.

### Fixed
- **Windows UTF-8 Runner Encoding:** Configured `PYTHONIOENCODING: "utf-8"` and replaced Unicode emoji print characters in build scripts to prevent `UnicodeEncodeError` on Windows `cp1252` runners.
- **Pillow Dependency:** Added `Pillow>=10.0.0` to `requirements.txt` for native PyInstaller `.ico` file processing.

---

## [v2.6.0] - 2026-10-15

### Added
- **Interactive Directory Browsing:** Added native Tkinter `filedialog` support with `Browse...` buttons for Video Directory, Metadata Directory, and Master Audio WAV selection in `hms_master_gui.py`.
- **Executable Builder Engine:** Created `build_exe.bat` and `build_exe.py` scripts to package `hms_master_gui.py` into a single standalone Windows executable (`dist/hms_master_gui.exe`) via PyInstaller.
- **Dependency Manifest Update:** Added `pyinstaller>=6.0.0` to `requirements.txt`.

---

## [v2.5.0] - 2026-10-15

### Added
- **Master GUI Control Panel:** Single-window Tkinter desktop application (`hms_master_gui.py`) consolidating shot renaming, audio trimming, beat loading, and XML generation.
- **Track Isolation Protocol:** Prefixing files with track slugs (`<track_slug>_...`) to prevent metadata overwrites across multi-song production runs.
- **Sub-Second Audio Trimming:** Automatic wave cutter to prevent DaVinci Resolve audio offset dropouts.
- **Revision Tagging Auditability:** Embedded system revision tags into FCP 7 XML root header, sequence title, and frame 0 markers.
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
