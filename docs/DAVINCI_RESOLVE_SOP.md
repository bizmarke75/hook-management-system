# 337 West Productions — DaVinci Resolve Free Standard Operating Procedure (SOP)
**Document ID:** SOP-HMS-001  
**Project:** Hook Management System (HMS) v3.0.0  
**Target Platform:** DaVinci Resolve Free (v18.x / v19.x+) on Windows 11  
**Interchange Format:** Apple Final Cut Pro 7 XML (`xmeml v5`)  
**Timeline Standard:** 1080p (1920×1080) | 24.0 fps | 40.000s (960 Frames Exact)

---

## 1. Pre-Conform Specifications

Before opening DaVinci Resolve, verify that the HMS pipeline has generated all required deliverables in `output/`:

* `output/<slug>_davinci_timeline.xml` (FCP 7 XML sequence file)
* `output/<slug>_master_audio.wav` (24-bit PCM stereo WAV, 44.1 kHz, ~10.5 MB)
* `output/<slug>_thebeats.txt` (Relative transient marker timestamps `0.000s` to `40.000s`)
* `C:\renders\shot1.mp4 ... shotN.mp4` (Sequenced AI video clips)

---

## 2. Project Setup & Timebase Lock (CRITICAL)

> **WARNING:** DaVinci Resolve Free locks the project timebase once any timeline or media item is added to the Media Pool. Setting the timebase after import causes 23.976 vs 24.0 fps audio-video sync drift.

1. Launch **DaVinci Resolve Free**.
2. Click **New Project** in the Project Manager.
3. Name the project: `HMS_<SLUG>_MASTER` (e.g., `HMS_PAPER_DOLLS_MASTER`).
4. Immediately press **`Shift + 9`** (or click the gear icon in the bottom right corner) to open **Project Settings**.
5. Under **Master Settings > Timeline Format**:
   * **Timeline resolution:** `1920 x 1080 Processing`
   * **Pixel aspect ratio:** `Square`
   * **Timeline frame rate:** `24`
   * **Playback frame rate:** `24`
6. Click **Save**.

---

## 3. Timeline Import Procedure

1. Ensure the **Edit** page (`Shift + 4`) or **Media** page (`Shift + 2`) is active.
2. Open the import dialog using shortcut **`Ctrl + Shift + I`** (or menu: **File > Import > Timeline...**).
3. Navigate to `C:\github\projects\hook-management-system\output\`.
4. Select `<slug>_davinci_timeline.xml` (e.g., `paper_dolls_davinci_timeline.xml`) and click **Open**.

---

## 4. "Load XML..." Dialog Configuration

When the **Load XML...** conform dialogue appears, configure the settings:

| Dialog Option | Setting | Purpose |
| :--- | :--- | :--- |
| **Timeline Name** | Leave Default (`<slug>_davinci_timeline`) | Matches generated sequence ID |
| **Automatically set project settings** | **UNCHECK** | Prevents Resolve from overriding the 24.0 fps lock |
| **Automatically import source clips into media pool** | **CHECK** | Pulls clips from `C:\renders` directly |
| **Ignore file extensions when matching** | **UNCHECK** | Enforces exact `.mp4` and `.wav` linking |
| **Use sizing information** | **CHECK** | Conforms 1080p render framing |
| **Link to source camera files** | **UNCHECK** | HMS targets local render files |

*Click **OK** to execute the sequence assembly.*

---

## 5. Post-Import Conform Verification Checklist

Run through this verification sequence inside the **Edit** page:

- [ ] **Timeline Frame Ruler:**
  * Move the playhead to the last frame (`End` key).
  * Confirm the timecode reads exactly **`00:00:40:00`** (Frame 960).
- [ ] **Audio Track (A1) Audit:**
  * Master audio waveform for `<slug>_master_audio.wav` starts instantly at frame `0` without missing clip warnings.
  * Right-click the clip on A1 > **Clip Attributes** > **Audio**: verify format is stereo, 24-bit.
- [ ] **Video Track (V1) Audit:**
  * All shots (`shot1` through `shotN`) are present in sequential order with zero gaps (no black filler frames).
- [ ] **Beat Transient Markers:**
  * Inspect the sequence timeline ruler.
  * Confirm that **Blue Markers** (`Beat 1`, `Beat 2` ... `Beat N`) populate across the 40 seconds.
  * Verify that marker pins align with the drum/transient peaks visible on the A1 audio track.

---

## 6. Resolving Unlinked Media (Troubleshooting)

If any clip displays **Media Offline**:
1. Open the **Media Pool** (`Ctrl + 1`).
2. Select all clips on the bin list.
3. Right-click > **Relink Selected Clips...**
4. Direct the browser to `C:\renders` for video or `output\` for the master audio WAV.
5. Click **OK**.

---

## 7. Master Render & Delivery Settings

When hook editing and color grading (Teal/Bio-Red or industrial grading) are complete:
1. Navigate to the **Deliver** page (`Shift + 8`).
2. Set **Custom Export**:
   * **Format:** `MP4`
   * **Codec:** `H.264`
   * **Encoder:** Native / NVIDIA (Auto)
   * **Resolution:** `1920 x 1080 HD`
   * **Frame rate:** `24`
   * **Audio:** `Linear PCM` or `AAC 320 Kbps`, `44100 Hz`, `Stereo`
3. Click **Add to Render Queue** and **Render All**.