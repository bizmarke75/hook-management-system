# Changelog - Hook Management System (HMS)

All notable changes to the Hook Management System (HMS) project will be documented in this file.

## [v2.8.0] - 2026-10-17

### Added
- **Track Slug Auto-Fill Engine:** Selecting a master WAV file automatically extracts track names, formats titles, and updates output directory paths.
- **PyInstaller Console Redirector:** Added `TextRedirector` class to safely capture stdout/stderr in standalone executables built with `--noconsole`.
- **Multi-Run Archiving:** Automatically saves timestamped timeline XML copies (`<track_slug>_hook_timeline_<rev>_<timestamp>.xml`) to an `archive/` folder.
- **GitHub Release Automation:** Added `publish_release.bat` and `publish_release.ps1` for one-click staging, committing, tag publishing, and automated GitHub Actions builds.

---

## [v2.7.0] - 2026-10-15

### Fixed
- **DaVinci Resolve MP4 Freeze Frame Bug:** Added explicit `<duration>` and `<samplecharacteristics>` (`width` 1280, `height` 720) tags inside `<file>` elements.
- **Dynamic Shot Discovery:** Replaced hardcoded 5-shot layout with a dynamic directory scanner (`shot1.mp4` through `shotN.mp4`) that parses MP4 clip headers for frame accuracy.

---

## [v2.6.0] - 2026-10-15

### Added
- **Interactive Directory Browsing:** Added native Tkinter `filedialog` support with `Browse...` buttons.
- **Executable Builder Engine:** Created `build_exe.bat` and `build_exe.py` scripts to package `hms_master_gui.py` into a single standalone Windows executable (`dist/hms_master_gui.exe`).

---

## [v2.5.0] - 2026-10-15

### Added
- **Master GUI Control Panel:** Single-window Tkinter desktop application (`hms_master_gui.py`) consolidating shot renaming, audio trimming, beat loading, and XML generation.
- **Track Isolation Protocol:** Prefixing files with track slugs (`<track_slug>_...`) to prevent metadata overwrites across multi-song production runs.
- **Sub-Second Audio Trimming:** Automatic wave cutter to prevent DaVinci Resolve audio offset dropouts.
