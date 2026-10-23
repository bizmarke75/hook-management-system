# Changelog - Hook Management System (HMS)

All notable changes to the Hook Management System (HMS) project will be documented in this file.

## [v3.1] - 2026-10-23

### Added
- GUI safety controls for dry-run, snapshot history, rollback, and restoring a selected run.
- CLI bootstrap and run-history commands, including dry-run, verification, rollback, and restore operations.
- Per-run manifests, rename maps, output backups, and guarded recovery through reusable safety and metadata modules.
- ffprobe-backed source metadata and linked source audio on a separate timeline lane.

### Fixed
- GUI dry-run checkbox initialization so the application starts cleanly.

### Changed
- Updated the Resolve import and recovery documentation for HMS v3.1.
- Verified that the generated FCP 7 XML imports successfully into DaVinci Resolve.
- Integrated the XML validator into the CLI module to keep the repository layout compact.

## [v3.09] - 2026-10-23

### Added
- Production hardening pass for the main HMS GUI and pipeline flow.
- ffprobe-based media probing for real audio and video metadata validation.
- ET XML generation and safer XML assembly for DaVinci Resolve import.
- Resolve-oriented FCP 7 XML with source video dimensions and frame rates, per-shot audio detection, and synchronized video/audio clip links.
- A separate A1 master-audio lane and A2 embedded-shot-audio lane when render clips contain audio.
- Unique sequence identifiers and stricter metadata handling.
- Reel metadata with ffprobe-derived source video dimensions and frame rates.
- Safe two-phase temp renaming strategy to prevent overwrite risk during shot sequencing.
- Audio length verification and BPM/duration validation guards.
- Optional GUI stdout guard for execution environments that prefer cleaner console behavior.

### Fixed
- Audio short-read validation and clipping issues in the trimmed WAV workflow.
- XML escaping and metadata mismatches in generated timeline output.
- Unsafe rename behavior during shot sequencing.
- Overwrite and collision risk in the render renaming process.
- Inconsistent source samplerate/channel values in generated FCP XML.

### Changed
- Consolidated the runtime app around the `hms_master_gui.py` production pipeline.
- Tightened build validation and packaging expectations for the Windows release flow.

---

## [v3.0.0] - 2026-10-19

### Added
- Unified Tkinter GUI and dark theme interface.
- RMS sliding-window hook detector with relative timeline sync.
- Sub-second 24-bit PCM WAV trimmer bypassing BWF chunk issues.
- Gapless 24fps FCP 7 XML generator with transient beat pins.
- Headless timeline validator for generated FCP 7 XML.
- Automated Windows PyInstaller build and release packaging flow.

### Changed
- Finalized the v3.0.0 production architecture and documentation set.

---

## [v2.6.0] - 2026-10-15

### Added
- Interactive directory browsing with native Tkinter file dialogs.
- Executable builder scripts for packaging the GUI into a standalone Windows binary.
- PyInstaller dependency manifest updates.

### Fixed
- Path validation and selection handling for custom folders outside `C:\renders\`.

---

## [v2.5.0] - 2026-10-15

### Added
- Master GUI control panel for the full workflow.
- Track isolation protocol and metadata safety rules.
- Sub-second trimmed audio output.
- Revision tagging in generated XML outputs.
- Live logging and runtime diagnostics.

---

## [v2.0.0] - 2024-10-14

### Added
- FCP 7 XML (`xmeml v5`) engine.
- Track-aware transient engine and beat marker import.
- Sequential shot renamer for render ordering.

---

## [v1.0.0] - 2026-10-10

### Added
- Initial proof-of-concept CLI workflow for Suno AI audio and DaVinci Resolve alignment.
