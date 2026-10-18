# Changelog - Hook Management System (HMS)

All notable changes to the Hook Management System (HMS) project will be documented in this file.

## [v2.8.0] - 2026-10-17

### Added
- **Interactive Directory & File Browsing:** Added native `Browse...` buttons for Video Shots Directory, Metadata Directory, and Master Audio WAV selection in `hms_master_gui.py`.
- **Automatic Track Slug & Title Auto-Fill:** Selecting a Master Audio WAV automatically strips common audio suffixes (`_master`, `_trimmed`, `_audio`, `_full`) and auto-populates Track Slug, Track Title, and suggested Video Shots Directory (`C:\renders\<track_slug>`).
- **Multi-Output Archiving:** Generated timeline XMLs and trimmed WAV files are written as primary production files (`<track_slug>_hook_timeline.xml`) and simultaneously archived with timestamped revision tags (`<track_slug>_hook_timeline_v2.8.0_<timestamp>.xml`) in dedicated `archive/` subfolders.
- **Dynamic Shot Duration Engine:** Automatically scans `video_dir` for all `shot*.mp4` files and uses OpenCV to measure precise frame counts and durations dynamically.
- **Automated GitHub Release Suite (`publish_release.bat` & `publish_release.ps1`):** Complete one-click release publisher that extracts `HMS_REV`, prompts for optional version overrides, commits code, and pushes release tags to trigger GitHub Actions PyInstaller builds.
- **Safe Console Redirection:** PyInstaller `--noconsole` builds redirect `sys.stdout` and `sys.stderr` safely to prevent startup logging crashes.

### Fixed
- Fixed unescaped literal newline syntax error in `build_exe.py` during GitHub Actions PyInstaller build steps.
- Fixed Windows CMD batch string parsing when running `publish_release.bat`.

---

## [v2.6.0] - 2026-10-15

### Added
- Executable builder scripts (`build_exe.py` and `build_exe.bat`) for standalone PyInstaller packaging.

---

## [v2.5.0] - 2026-10-15

### Added
- Master GUI control panel consolidating shot renaming, audio trimming, beat loading, and XML generation.
