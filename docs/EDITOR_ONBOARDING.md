# HMS Editor / Operator Onboarding

This guide is for new operators and editors working with the HMS pipeline for the first time: prepare media, run HMS safely, confirm the generated timeline, and know how to recover.

## 1. Prerequisites

Before you begin, confirm that all of the following are in place:

- Windows 10/11 with the HMS project checked out locally
- Python 3.10+ installed
- `ffprobe` on `PATH`
- DaVinci Resolve Free installed for import and review
- A valid master audio file and a render folder with the final shots
- Access to a working copy of the project and its intended output location

## 2. First-run checklist

1. Open the repository root in PowerShell. Keep the same working directory for the run and its later recovery commands; run history is stored under `rollback/` relative to that directory.
2. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

3. Launch the HMS GUI:

```powershell
python hms_master_gui.py
```

4. Pick the master audio file and render directory.
5. Define the include patterns for the exact shots you want processed.
6. Set `--output-dir` or the GUI output folder if you are not writing to the default `output/` path.
7. Start with **Dry Run** enabled.
8. Review the planned selection and order. If correct, disable **Dry Run** and run the pipeline again to write outputs.

## 3. Safe execution habits

- Do not leave the include list blank.
- Use explicit include patterns for the final shot set.
- Exact filenames are processed in the order entered; unmatched files remain untouched.
- Use exclude patterns only when you need to skip a known subset.
- Run a dry run before a production pass whenever you are changing shot order or using a new output folder.
- Review the log before moving on; if the pipeline reports a mismatch, stop and fix the file selection before continuing.
- Treat `rollback/` as local recovery data and keep a protected copy; it is not a substitute for backing up source media or project files.

## 4. What good output looks like

A healthy HMS run should produce:

- `<slug>_master_trimmed.wav` — trimmed master audio
- `<slug>_thebeats.txt` — beat marker timestamps
- `<slug>_davinci_timeline.xml` — DaVinci Resolve timeline
- ordered shot files with their source extensions and no unexpected collisions

Use **VERIFY ONLY** or the `--verify-only` CLI option to check existing output without rewriting it. A successful HMS run does not replace the Resolve import and timeline checks below.

## 5. Resolve import and verification

After HMS finishes:

1. Open a new Resolve project named `HMS_<SLUG>_MASTER`.
2. Set the project timebase to `24 fps` before importing.
3. Import the generated XML from the output directory.
4. Confirm the sequence ends at `00:00:40:00` and the audio begins at frame 0.
5. Check that the shots are ordered correctly and the markers align with the hook window.
6. If clips appear as offline, relink them to the render directory or the selected output folder.

## 6. Recovery and rollback

If a run needs to be undone, use the GUI's **ROLLBACK LAST RUN** / **RESTORE RUN...** controls or the CLI:

```powershell
python hms_v31_patcher.py --rollback
python hms_v31_patcher.py --restore run_003
```

Confirm the run ID and restore target before proceeding. HMS stops if required backups or renamed shots are missing or if restoring would overwrite an unexpected file. Recovery is for HMS run outputs and clip renames; it does not roll back a published installer or release.

## 7. Before a release or handoff

Before a new build is published or handed off, follow the runbook's **Release verification checklist**. At minimum, verify that the candidate launches, run regression and dry-run/verify-only checks, exercise restore on a disposable run, and import the timeline into the current production Resolve version.

This guide covers routine operator behavior; package creation and release approval remain maintainer responsibilities.
