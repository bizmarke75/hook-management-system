# 337 West Productions — DaVinci Resolve Free Standard Operating Procedure (SOP)

**Document ID:** SOP-HMS-001
**Project:** Hook Management System (HMS) v3.1
**Target Platform:** DaVinci Resolve Free (v18.x / v19.x+) on Windows 11
**Interchange Format:** Apple Final Cut Pro 7 XML (`xmeml v5`)
**Timeline Standard:** Source-derived video resolution | 24.0 fps | 40.000s (960 frames exact)

---

## 1. Pre-conform specification

Before opening DaVinci Resolve, verify that the HMS pipeline has generated the required output assets in `output/`:

- `output/<slug>_davinci_timeline.xml` — FCP 7 XML sequence file
- `output/<slug>_master_audio.wav` — 24-bit PCM WAV trimmed to the hook window
- `output/<slug>_thebeats.txt` — relative beat transient timestamps
- `C:\renders\shot1.mp4` through `shotN.mp4` — sequenced render shots

If a custom **Output Dir** is selected in the HMS GUI or supplied with `--output-dir`, use that folder instead of `output/` for the generated timeline, master WAV, and beat files.

---

## 2. Project setup and timebase lock

> Warning: DaVinci Resolve Free locks the project timebase once media or a timeline is imported. Set the project to 24 fps before bringing in any assets.

1. Launch DaVinci Resolve Free.
2. Click New Project in the Project Manager.
3. Name the project: `HMS_<SLUG>_MASTER`.
4. Press `Shift + 9` to open Project Settings.
5. Under Master Settings > Timeline Format:
   - Timeline resolution: Match the desired output; the XML includes probed source dimensions for each shot
   - Pixel aspect ratio: `Square`
   - Timeline frame rate: `24`
   - Playback frame rate: `24`
6. Save the project.

---

## 3. Timeline import procedure

1. Ensure the Edit page (`Shift + 4`) or Media page (`Shift + 2`) is active.
2. Open the import dialog with `Ctrl + Shift + I`.
3. Navigate to the generated output folder.
4. Select the `<slug>_davinci_timeline.xml` file and click Open.

---

## 4. Load XML dialog configuration

When the Load XML dialog appears, use these settings:

| Dialog option | Setting | Purpose |
| :--- | :--- | :--- |
| Timeline Name | Leave default | Matches the generated sequence name |
| Automatically set project settings | Unchecked | Avoids overriding the 24 fps lock |
| Automatically import source clips into media pool | Checked | Pulls clips from the renders folder |
| Ignore file extensions when matching | Unchecked | Keeps exact `.mp4` and `.wav` linking |
| Use sizing information | Checked | Preserves sizing metadata from probed source media |
| Link to source camera files | Unchecked | HMS targets local render assets |

Click OK to proceed.

---

## 5. Post-import verification checklist

Run through this checklist on the Edit page:

- [ ] Timeline ruler ends at exactly `00:00:40:00` (960 frames)
- [ ] Audio track begins at frame 0 and matches the trimmed master audio file
- [ ] Master audio is on A1; embedded render audio, when present, is linked to its video clip on A2
- [ ] Video shots appear in order from `shot1` to `shotN` with no black filler gaps
- [ ] Blue marker pins span the full hook window and align to transient peaks
- [ ] Sequence name and revision metadata are present in the XML root and clip metadata

---

## 6. Troubleshooting unlinked media

If any clips show Media Offline:

1. Open the Media Pool.
2. Select all affected clips.
3. Right-click > Relink Selected Clips.
4. Point the browser to the renders directory or output folder as needed.
5. Click OK.

---

## 7. Master render and delivery settings

When editing and color finishing are complete:

1. Go to the Deliver page (`Shift + 8`).
2. Set Custom Export:
   - Format: `MP4`
   - Codec: `H.264`
   - Resolution: `1920 x 1080 HD`
   - Frame rate: `24`
   - Audio: `AAC 320 Kbps` or `Linear PCM`
3. Add to render queue and render all.

---

## 8. Runtime expectations

The current HMS v3.1 workflow expects:

- a valid master audio source
- a render directory with sequential clips
- `ffprobe` available in PATH
- a correctly generated `output/<slug>_davinci_timeline.xml`

This SOP is the standard import path for resolving the generated timeline safely in DaVinci Resolve Free.
The HMS v3.1 FCP 7 XML import has been manually verified in DaVinci Resolve.

## 9. Run history and recovery

HMS stores each complete or failed pipeline run under `rollback/run_NNN/`, with its manifest, shot rename map, and backups of output files that existed before the run. Use the GUI's **ROLLBACK LAST RUN** or **RESTORE RUN...** controls, or run `python hms_v31_patcher.py --rollback` / `--restore run_NNN`. Restore is safety-checked and stops if required renamed shots or backups are missing, or if restoring an original filename would overwrite another file.

Use the GUI's **DRY RUN** checkbox or run the command with `--dry-run` and explicit audio, renders, and slug arguments to inspect the proposed operations without changing files. **VERIFY ONLY** checks existing output and timeline integrity without rewriting it.
