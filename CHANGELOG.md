# Changelog - Hook Management System (HMS)

All notable changes to the Hook Management System (HMS) project will be documented in this file.

## [Unreleased]

> Experimental testing only.

### Added
- Add full-song video timelines that play selected clips once at natural speed, trim the last clip at the song end, and require enough footage to cover the audio.
- Add `--full-song` CLI support for full-length video timelines.

## [v3.16-experimental.1] - 2026-11-03

> Very experimental testing release. The image-only lyric/comic-video and SRT workflow is not production-ready.

### Added
- Add an image-only lyric-video workflow for ordered JPEG/PNG stills, supporting hook-length or full-source-audio timelines.
- Add optional timed SRT subtitle sidecars, clipping and retiming cues to the hook window when needed.
- Validate FCP 7 XML timing and audio duration against the actual sequence length for image-only timelines.
- Include optional SRT sidecars in run backups and rollback restoration.

## [v3.15] - 2026-11-03

### Added
- Select render clips directly from the chosen renders folder to populate the include list; retain optional exclude patterns.

### Fixed
- Mute embedded render audio in generated Resolve timelines while keeping the trimmed master WAV linked on A1, avoiding broken embedded-audio clip references.
- Estimate Target BPM from each newly selected master WAV instead of carrying a previous track's value, and block BPM-dependent runs until estimation completes.
- Name trimmed master audio `<slug>_master_trimmed.wav` consistently in generated timelines, validation, and recovery manifests.
- Keep verify and restore compatible with existing `<slug>_master_audio.wav` outputs and recovery manifests.
- Strip recognized trailing master/trimmed suffixes from selected audio names to avoid duplicate segments in output filenames.

### Changed
- Update application and package labels for HMS v3.15.
- Update the Resolve workflow documentation for direct clip selection and muted embedded audio.

## [v3.14] - 2026-11-03

### Fixed
- Estimate Target BPM from each newly selected master WAV instead of carrying a previous track's value, and block BPM-dependent runs until estimation completes.
- Name trimmed master audio `<slug>_master_trimmed.wav` consistently in generated timelines, validation, and recovery manifests.
- Keep verify and restore compatible with existing `<slug>_master_audio.wav` outputs and recovery manifests.
- Strip recognized trailing master/trimmed suffixes from selected audio names to avoid duplicate segments in output filenames.

### Added
- Add regression tests for BPM estimation, output naming, and pending-estimation workflow guards.

### Changed
- Update application and package labels for HMS v3.14.

## [v3.13] - 2026-10-26
- Prevent full-pipeline dry runs from entering code that mutates files; dry-run checks are also enforced by individual processing steps.
- Stop broad render-folder renaming by requiring explicit clip include patterns, with optional exclusions and explicit ordering for UUID-named clips.
- Keep unselected files untouched, preserve selected clips' source extensions, and block collisions with files outside the selection.

### Added
- Add regression tests for dry-run safety, render filtering, rename collisions, clip ordering, and pipeline selection.

### Changed
- Update application and package labels for HMS v3.13.

## [v3.12] - 2026-10-26

### Added
- Windows installer and Python wheel/source distributions attached to tagged GitHub releases.

### Changed
- Updated application, documentation, and build labels for the v3.12 release.

## [v3.11] - 2026-10-26

### Added
- Selectable output directory in the GUI and `--output-dir` CLI support, including verification and recovery backup routing.

### Changed
- Updated application, documentation, and build labels for the v3.11 release.
- Automated Windows release builds use Python 3.11.

## [v3.1] - 2026-10-23

### Added
- Selectable output directory in the GUI and `--output-dir` support for CLI execution and verification.
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
