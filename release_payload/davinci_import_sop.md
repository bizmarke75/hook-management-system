# Hook Management System (HMS) — DaVinci Resolve Import SOP
**System Version:** `v2.5.0`  
**Target NLE:** DaVinci Resolve Free / Studio (v18, v19, v20)  
**Schema Standard:** Final Cut Pro 7 XML (`xmeml v5`)  

---

## 1. Overview & Architectural Goals

The **Hook Management System (HMS)** automates the synchronization of AI-generated audiovisual renders (e.g., Google Flow / Veo 3.1) and AI music stems (e.g., Suno AI) into DaVinci Resolve. 

This Standard Operating Procedure (SOP) eliminates common XML parsing bugs—such as video clips misinterpreting as static still images or audio tracks dropping sub-second offsets—by enforcing a standardized pre-import pipeline and project configuration.

---

## 2. Pre-Import Checklist

Before launching DaVinci Resolve, verify that the automated Python pipeline (`hms_master_gui.py` or `run_hms_track_pipeline.py`) has executed successfully and generated the required track assets:

- [ ] **Sequential Shot Renders:** Located in `C:\renders\<track_slug>\` named sequentially:
  - `shot1.mp4`
  - `shot2.mp4`
  - `shot3.mp4`
  - `shot4.mp4`
  - `shot5.mp4`
- [ ] **Pre-Trimmed Master Audio:** Located at `C:\audio\<track_slug>_master_trimmed.wav` (where time `00:00.000` corresponds to the exact start of the hook).
- [ ] **Track-Aware Transient Files:** Located in `C:\renders\output\`:
  - `<track_slug>_thebeats.txt`
  - `<track_slug>_hooktimestamp.txt`
- [ ] **FCP 7 Timeline XML:** Located at `C:\renders\<track_slug>\<track_slug>_hook_timeline.xml`.

---

## 3. DaVinci Resolve Project Setup

1. Launch **DaVinci Resolve**.
2. Create or open your project.
3. Open **Project Settings** by pressing **Shift + 9** (or clicking the gear icon in the bottom right corner).
4. Navigate to **Master Settings**:
   - Set **Timeline Frame Rate** to **24 fps** (must match the frame rate specified in `hms_master_gui.py`).
   - Set **Playback Frame Rate** to **24 fps**.
   - Set **Video Format** to **1080p 24** (or **720p 24**).
5. Navigate to **Image Scaling**:
   - Set **Input Scaling** to **Scale full frame with crop** (prevents black bars on non-standard AI render aspect ratios).
6. Click **Save**.

---

## 4. Timeline Import Protocol

1. Open the **Edit Page** (**Shift + 4**) or **Cut Page** (**Shift + 3**).
2. Press **Ctrl + Shift + I** (Windows) or **Cmd + Shift + I** (macOS), or navigate to:
   `File > Import > Timeline...`
3. Navigate to your project render directory:
   `C:\renders\<track_slug>\<track_slug>_hook_timeline.xml`
4. Click **Open**.
5. In the **Load XML** configuration dialog:
   - **Timeline Name:** Retain default (e.g., `<Track Title> Hook Video [v2.5.0]`).
   - **Automatically import source clips into Media Pool:** Checked `[X]`.
   - **Use sizing information:** Checked `[X]`.
6. Click **OK**.

---

## 5. Post-Import Verification & Layout

Upon successful import, your timeline will display the following layout:

| Timeline Track | Asset Assigned | State / Function |
|---|---|---|
| **Video Track V1** | `shot1.mp4` – `shot5.mp4` | Sequentially ordered full-motion video clips (no freeze frames). |
| **Video Track V2** | *Empty* | Reserved for kinetic Text+ typography overlays. |
| **Video Track V3** | *Empty* | Reserved for 35mm film grain overlays / adjustment clips. |
| **Audio Track A1** | `<track_slug>_master_trimmed.wav` | Synchronized audio track starting at frame 0. |
| **Audio Markers** | Transient Beat Pins | Blue marker pins embedded along Track A1 at every transient hit. |

---

## 6. Editorial Polish Workflow

### A. Enable Snapping
- Press **N** to toggle **Snapping** ON.
- Playhead movements, clip handles, and Text+ nodes will now magnetically snap to the embedded blue beat markers.

### B. Lock Audio Track
- Click the **Padlock Icon** on Audio Track A1 to prevent accidental ripple edits from knocking audio out of phase sync.

### C. Kinetic Typography Setup (Text+)
1. Drag a **Text+** title generator from the Effects Library onto **Video Track V2**.
2. Trim the Text+ clip so its duration matches the transient beat spacing (e.g., 0-frame hold cuts).
3. In the **Inspector > Text tab**, enter your kinetic lyrics.
4. Go to the **Shading tab**:
   - Select **Select Element: 3 (Shadow)** and check **Enabled**.
   - Set **Color** to Neon Orange (`#FF6600`).
   - Increase **Softness X/Y** to create an aggressive glow surrounding the stencil text.

### D. 35mm Film Grain Overlay
1. Place a 4K 35mm Film Grain asset onto **Video Track V3** extending across the 40-second hook.
2. In the **Inspector > Video > Composite**, set **Composite Mode** to **Soft Light** or **Overlay**.
3. Set **Opacity** to **25% - 30%**.

---

## 7. Troubleshooting & Common Fixes

| Issue | Root Cause | Solution |
|---|---|---|
| **Video imports as still image / freeze frame** | FCPXML 1.9 parent-child spine nesting bug. | Ensure timeline was created using FCP 7 XML (`xmeml v5`) via `hms_master_gui.py` v2.5.0+. |
| **Audio is missing or out of sync** | Raw audio used without trimming. | Run `trim_master_audio.py` to create a `00:00` aligned WAV file before importing XML. |
| **Markers missing from timeline** | `thebeats.txt` file missing during script run. | Place `<track_slug>_thebeats.txt` into `C:\renders\output\` and re-generate XML. |
| **Timecode drift on long tracks** | Timeline frame rate set to 23.976 fps instead of 24.0 fps. | Verify Project Settings (**Shift + 9**) matches 24 fps before XML import. |

---
*Generated by Hook Management System (HMS) Repository Core — v2.5.0*
