# 337 West Productions — HMS Operator Runbook

**Document ID:** SOP-HMS-001
**Project:** Hook Management System (HMS) v3.16 Experimental
**Target Platform:** DaVinci Resolve Free (v18.x / v19.x+) on Windows 10/11
**Interchange Format:** Apple Final Cut Pro 7 XML (`xmeml v5`)
**Timeline Standard:** Source-derived resolution | 24.0 fps | 40.000s hook by default; full-song timelines may use the full source-audio duration

This runbook covers the daily production workflow: set up the project, run HMS, verify the generated sequence, import it into DaVinci Resolve, and recover or correct a failed run. It keeps the final delivery/export settings in the same guide so operators can move seamlessly from generation to final export.

> **VERY EXPERIMENTAL — TESTING ONLY:** The image-only lyric/comic-video, full-song video, and SRT workflows are not production-ready. Back up source media, inspect generated timelines, and import subtitle sidecars separately.

---

## 1. Before you start

### Required inputs

- A valid master audio source
- A render directory with sequenced video shots
- `ffprobe` on `PATH`
- A Windows 10/11 machine with DaVinci Resolve Free installed

### Expected HMS outputs

Before opening Resolve, confirm that HMS generated the expected files in the selected output folder:

- `<slug>_davinci_timeline.xml` — Final Cut Pro 7 interchange XML (`xmeml` v5), imported into Resolve as a timeline
- `<slug>_master_trimmed.wav` — 24-bit PCM WAV for the selected hook or full-song duration
- `<slug>_thebeats.txt` — transient beat timestamps
- `shot1` through `shotN` — the final ordered video renders, retaining their source extensions; image-only mode references selected stills without renaming them
- `<slug>_subtitles.srt` — optional timed captions, imported into Resolve separately from the XML

If a custom **Output Dir** is chosen in the HMS GUI or passed via `--output-dir`, use that folder instead of the default `output/` location for the timeline, trimmed master WAV, and beat files. Selecting a new master WAV estimates its BPM into the GUI's **Target BPM** field; verify or adjust the estimate as needed. When HMS derives the slug, it removes recognized trailing master/trimmed suffixes from the source filename to avoid duplicated master-name segments in outputs.

### Project and file safety checks

- Choose the intended video clips from the file picker after selecting the render directory, or use **Choose Files** to revise the selection.
- **Experimental testing only:** for an image-only lyric/comic-book timeline, select **Image-only Lyric Video** and choose JPEG/PNG stills; their selected order is used and source images are not renamed.
- Choose **Hook** or **Full song** for the timeline. Full-song mode starts at the beginning and uses the complete source audio, up to 600 seconds. For video clips, selected shots play once at natural speed in order; the final clip is trimmed to the song end. If the selected footage is too short, HMS stops before renaming anything and asks for more shots/files. For still images, HMS distributes the images across the timeline.
- Optional: enable **Include SRT subtitles** and select a timed SubRip `.srt` file. HMS clips/retimes cues for a hook or keeps full-song timing.
- Confirm the include list is not blank; HMS blocks blank include patterns before generating or renaming output.
- Use `--exclude` or **Exclude Clips** for optional filename patterns that should be skipped.
- Use **DRY RUN** or `--dry-run` before a production run when you are validating selection or ordering.

---

## 2. Run HMS safely

### GUI workflow

1. Open `hms_master_gui.py`.
2. Select the master audio file and render directory.
3. Set the output folder if needed.
4. Choose **Standard Hook Video** for video renders, or **Image-only Lyric Video** for a still-image sequence. Select the intended files in the picker that opens after choosing the renders directory; use **Choose Files** to revise the selection.
5. Add optional exclude patterns if some selected clips should be ignored.
6. Choose **Hook** or **Full song**. Full-song video mode uses each selected clip once at natural speed and requires enough footage to cover the audio; add more shots/files if HMS reports insufficient duration. For still-image timelines, selected images are distributed across the chosen duration. If subtitles are desired, enable **Include SRT subtitles** and select a timed `.srt` file.
7. Run with **Dry Run** enabled to preview the planned operations; review the log and selection.
8. When the preview is correct, disable **Dry Run**, run again, and review the log output.

### CLI workflow

```powershell
python hms_v31_patcher.py --dry-run --audio "C:\audio\track.wav" --renders "C:\renders" --slug track --include "shot_2a*" --include "shot_2b*" --exclude "*_final*" --output-dir "D:\HMS\output"
python hms_v31_patcher.py --audio "C:\audio\track.wav" --renders "C:\renders" --slug track --include "shot_2a*" --include "shot_2b*" --output-dir "D:\HMS\output"
python hms_v31_patcher.py --audio "C:\audio\track.wav" --renders "C:\renders" --slug track --include "*.mp4" --full-song
python hms_v31_patcher.py --verify-only --slug track --renders "C:\renders" --output-dir "D:\HMS\output"
```

Important notes:

- Exact filenames are processed in the order entered.
- `--full-song` uses the full audio duration. For video clips, selected footage must cover the song; clips play once at natural speed and the final clip is trimmed at the song end.
- Unmatched files are left untouched.
- The dry-run guard applies to individual steps as well as the full pipeline.
- `--verify-only` checks output integrity without rewriting files.

---

## 3. Recovery and rollback before import

HMS stores run history under `rollback/run_NNN/` in the application's working directory (normally the project root), with manifests, rename maps, and backups of prior output files. Keep this folder with the same project/working directory used for the run.

Use either:

- the GUI controls (**ROLLBACK LAST RUN** / **RESTORE RUN...**), or
- CLI recovery commands:

```powershell
python hms_v31_patcher.py --rollback
python hms_v31_patcher.py --restore run_003
```

Recovery is safety-checked and will stop if required renamed shots or backups are missing, or if a restore would overwrite an existing file unexpectedly. Treat run history as local recovery data, not an independent backup: protect a copy of the `rollback/` folder and the source media separately.

---

## 4. DaVinci Resolve setup

> Warning: DaVinci Resolve Free locks the project timebase once media or a timeline is imported. Set the project to 24 fps before bringing in any assets.

1. Launch DaVinci Resolve Free.
2. Create a new project named `HMS_<SLUG>_MASTER`.
3. Open **Project Settings** (`Shift + 9`).
4. Under **Master Settings > Timeline Format**:
   - Timeline resolution: match the final output target
   - Pixel aspect ratio: `Square`
   - Timeline frame rate: `24`
   - Playback frame rate: `24`
5. Save the project.

---

## 5. Import the HMS XML into Resolve

1. Ensure the **Edit** page (`Shift + 4`) or **Media** page (`Shift + 2`) is active.
2. Open the import dialog with `Ctrl + Shift + I`.
3. Navigate to the output folder that contains the generated XML.
4. Select `<slug>_davinci_timeline.xml` and click **Open**.

When the **Load XML** dialog appears, use:

| Dialog option | Setting |
| :--- | :--- |
| Timeline Name | Leave default |
| Automatically set project settings | Unchecked |
| Automatically import source clips into media pool | Checked |
| Ignore file extensions when matching | Unchecked |
| Use sizing information | Checked |
| Link to source camera files | Unchecked |

Then click **OK**.

---

## 6. Post-import validation checklist

Use the Edit page and confirm all of the following:

- [ ] Standard hook timeline ruler ends at `00:00:40:00` (960 frames), or at the selected full-song duration
- [ ] Audio begins at frame 0 and matches the trimmed master WAV
- [ ] Trimmed master audio sits on A1; embedded render audio is muted and no shot-audio clips appear on A2
- [ ] If an SRT sidecar was generated, import it into Resolve as a separate subtitle track and confirm cue timing
- [ ] Shots appear in order from `shot1` to `shotN` with no black filler gaps
- [ ] Blue marker pins span the full hook window and align with transient peaks
- [ ] Sequence name and revision metadata are visible in the XML root and clip metadata

If any clips show as **Media Offline**:

1. Open the **Media Pool**.
2. Select the affected clips.
3. Right-click and choose **Relink Selected Clips**.
4. Point Resolve to the render directory or output folder as needed.
5. Confirm the relink.

---

## 7. Final delivery / export settings

When the edit is approved, export the completed cut from the **Deliver** page (`Shift + 8`):

- Format: `MP4`
- Codec: `H.264`
- Resolution: `1920 x 1080 HD`
- Frame rate: `24`
- Audio: `AAC 320 Kbps` or `Linear PCM`

Add to the render queue and render all.

---

## 8. Release verification checklist

The current tag-triggered GitHub Actions workflow runs repository regression tests, builds the executable, portable ZIP, installer, wheel, and source archive, and checks that expected files exist. It does not launch the packaged executable, smoke-test the wheel install path, or import a generated timeline into Resolve. The workflow publishes a non-draft release directly from a version tag; it does not provide a staged candidate review.

Before creating a release tag, close these validation gaps against the exact candidate commit and artifacts:

- Run `python -m unittest discover -s tests -v` and record the outcome.
- On a clean Windows environment, launch the packaged EXE and smoke-test the CLI/GUI paths, including dry run and verify-only.
- Install and import the built wheel; inspect the portable ZIP and installer contents and confirm version labels match the tag.
- Exercise include/exclude ordering and a custom output directory with representative media.
- Complete a restore drill using a disposable run with both pre-existing output files and renamed clips; confirm the restore returns each item to its prior state.
- Keep the working-directory `rollback/` folder available for recovery, but exclude it from source and release artifacts; test recovery when a backup or destination is missing or occupied. The app restore covers run outputs and clip renames; it is not a documented rollback mechanism for published installers or releases.
- Import the generated XML and relink media in the current production Resolve version before release approval.

These are release gates for a packaged HMS build, not claims that all of them have passed for v3.16. The v3.16 still-image and subtitle workflows have only been exercised with generated test media, not in DaVinci Resolve. The last manual Resolve validation note is for the FCP 7 XML import workflow in HMS v3.12.

---
