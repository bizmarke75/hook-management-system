# Changelog - Hook Management System (HMS)

All notable changes to the Hook Management System (HMS) project will be documented in this file.

## [v2.7.0] - 2026-10-15

### Fixed
- **DaVinci Resolve MP4 Freeze-Frame Bug:** Added explicit `<duration>` and `<samplecharacteristics>` (`width` 1280, `height` 720) metadata tags directly inside each `<file>` block in the FCP 7 XML (`xmeml v5`) generator. This forces DaVinci Resolve to import video clips as active motion streams rather than static single-frame holds.
- **Dynamic Shot Discovery:** Removed hardcoded 5-shot fallback array in `hms_master_gui.py`. The engine now dynamically scans the target video directory for all `shot*.mp4` files (e.g., 4 shots of 10s each from Gemini Omni Flash or N shots of arbitrary lengths).
- **Header-Based MP4 Duration Extraction:** Implemented zero-dependency `get_mp4_duration()` to read exact millisecond clip durations directly from MP4 `mvhd` atom headers, ensuring frame-accurate timeline placement.

---

## [v2.6.2] - 2026-10-15

### Fixed
- **PyInstaller Console Stream Crash:** Added safe stream initialization (`io.StringIO()`) for `sys.stdout` and `sys.stderr` when running in `--noconsole` mode. Prevents `AttributeError` log crashes on Windows.

---

## [v2.6.1] - 2026-10-15

### Added
- **GitHub Actions Release Automation:** Added `.github/workflows/build_release.yml` CI/CD pipeline for automated cloud `.exe` compilation and release publishing.
- **Console Output Encoding Fix:** Configured `PYTHONIOENCODING: "utf-8"` and replaced Unicode emojis in `build_exe.py` with ASCII tags to prevent `cp1252` encoding errors on Windows runners.
- **337West Icon Assets:** Packaged multi-resolution `337west_icon.ico` and `337west_icon.png` for executable branding.

---

## [v2.6.0] - 2026-10-15

### Added
- **Interactive Directory Browsing:** Added native Tkinter `filedialog` support with `Browse...` buttons for Video Directory, Metadata Directory, and Master Audio WAV selection in `hms_master_gui.py`.
- **Executable Builder Engine:** Created `build_exe.bat` and `build_exe.py` scripts to package `hms_master_gui.py` into a single standalone Windows executable (`dist/hms_master_gui.exe`) via PyInstaller.
- **Dependency Manifest Update:** Added `pyinstaller>=6.0.0` and `Pillow>=10.0.0` to `requirements.txt`.

---

## [v2.5.0] - 2026-10-15

### Added
- **Master GUI Control Panel:** Single-window Tkinter desktop application (`hms_master_gui.py`) consolidating shot renaming, audio trimming, beat loading, and XML generation.
- **Track Isolation Protocol:** Prefixing files with track slugs (`<track_slug>_...`) to prevent metadata overwrites across multi-song production runs.
- **Sub-Second Audio Trimming:** Automatic wave cutter to prevent DaVinci Resolve audio offset dropouts.
- **Revision Tagging Auditability:** Embedded revision tags into FCP 7 XML root header, sequence title, and frame 0 markers.
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
