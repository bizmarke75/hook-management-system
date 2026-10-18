# Project "The Last Train" — Hook Management System (HMS) Production Blueprint
**System Revision:** `HMS v2.8.0`  
**Production Studio:** 337 West Productions  
**Date:** October 18, 2026  

---

## 1. Master Audio & Track Specifications

* **Track Title:** The Last Train
* **Track Slug:** `the_last_train`
* **Master Audio File Path:** `C:\audio\the_last_train_master.wav`
* **Render Output Folder:** `C:\renders\the_last_train\`
* **Target NLE:** DaVinci Resolve (v18 / v19 / v20)
* **Musical Style:** Industrial Alternative Metal — urgent breakbeat groove (117.5 BPM) with relentless live kick/snare, low tube-saturated guitars, overdriven bass, dry baritone vocal opening to wide belted choruses, chopped industrial breakdown, and a hard stop.
* **Tempo:** `117.5 BPM`
* **Hook Sequence Window:** `196.603s` – `246.603s` (`03:16.603` – `04:06.603`)
* **Total Sequence Duration:** `50.0 seconds` (5 clips × 10.0 seconds)
* **Target Frame Rate:** `24.0 fps`

---

## 2. 5-Shot Visual Blueprint (Google Flow / Veo 3.1)

All prompts follow Google's 5-part Veo 3.1 formula (`[Cinematography] + [Subject] + [Action] + [Context] + [Style & Ambiance]`) and are formatted for 10-second Gemini Omni Flash / Veo 3.1 generation.

### 📽️ Shot 1 (`shot1.mp4`) — `00:00 – 00:10` (`196.6s – 206.6s`)
* **Lyrics Anchor:** *"You left your gloves beside the sink / A coffee ring beside the ink"*
* **Cinematic Visual:** Cinematic slow dolly-in close-up shot on a 35mm lens. Elena's mustard-yellow leather gloves lie by a stainless steel kitchen sink next to a handwritten note with a dried coffee ring. Cold blue morning light filtering through dust motes, with a stroboscopic amber warning light pulsing against dark concrete walls.
* **Style & FX:** Gritty 16mm film texture, high-contrast shadows, 24fps. Faint distant wind, low industrial pulse.

### 📽️ Shot 2 (`shot2.mp4`) — `00:10 – 00:20` (`206.6s – 216.6s`)
* **Lyrics Anchor:** *"The last train pulls the whole town through / Past the places we once knew"*
* **Cinematic Visual:** Intense tracking shot in a dark, wet subway station. A massive industrial freight train roars in, its halogen floodlights and amber sparks reflecting in Jovan's still, expressionless eyes. Stroboscopic lighting from passing train windows sweeping across wet steel tracks.
* **Style & FX:** Industrial teal and rust-red color palette, high kinetic motion blur, 24fps. Roaring engine, metallic clacking on rails.

### 📽️ Shot 3 (`shot3.mp4`) — `00:20 – 00:30` (`216.6s – 226.6s`)
* **Lyrics Anchor:** *"I watch the red tail disappear / And let the quiet settle here"*
* **Cinematic Visual:** Jovan walking in slow-motion through the station while the surrounding crowd of commuters is a rapid time-lapse motion blur. Red tail lights on the rear train car disappear into thick, swirling steam and rain. Cold indigo and fluorescent lighting.
* **Style & FX:** Muffled crowd noise, chopped industrial machinery clatter, echoing train horn, 24fps.

### 📽️ Shot 4 (`shot4.mp4`) — `00:30 – 00:40` (`236.6s – 236.6s`)
* **Lyrics Anchor:** *"The last train takes the night away / But leaves your name where it used to stay"*
* **Cinematic Visual:** Macro top-down shot on a 50mm lens. Jovan's finger slowly traces the name "MARA" into thick grey dust on a wooden table next to a dust-covered photograph. A single shaft of golden sunset light cuts through cold shadows.
* **Style & FX:** Cold teal background with warm amber highlights, 24fps. Faint scratching sound, wind blowing softly.

### 📽️ Shot 5 (`shot5.mp4`) — `00:40 – 00:50` (`236.6s – 246.6s`)
* **Lyrics Anchor:** *"Lancaster, the doors roll shut / No more waiting on the platform"*
* **Cinematic Visual:** Static low-angle shot from the platform looking through closing subway train doors. Jovan sits motionless inside, staring straight ahead. Heavy mechanical doors slide shut, cutting off the view and abruptly cutting to pure black on the final frame.
* **Style & FX:** Cold desaturated concrete palette, 24fps. Heavy mechanical doors slamming shut followed by sudden, absolute silence on the hard stop.

---

## 3. Automated Execution SOP (`hms_master_gui.py` v2.8.0)

1. **Asset Preparation:**
   * Render all 5 video clips in Google Flow at 10 seconds each (`360p` draft for 7 credits/shot or `720p/1080p` hero renders).
   * Save them into `C:\renders\the_last_train\` as `shot1.mp4`, `shot2.mp4`, `shot3.mp4`, `shot4.mp4`, and `shot5.mp4`.
   * Place the uncompressed master audio file in `C:\audio\the_last_train_master.wav`.

2. **HMS Control Panel Configuration:**
   * Launch `hms_master_gui.py` (or `hms_master_gui.exe`).
   * Click **`Browse...`** next to **Master Audio WAV** and select `C:\audio\the_last_train_master.wav`.
   * HMS auto-populates:
     * **Track Slug:** `the_last_train`
     * **Track Title:** `The Last Train`
     * **Video Shots Directory:** `C:\renders\the_last_train`
   * Confirm **Revision Tag** is set to `v2.8.0` and **Timeline FPS** is set to `24`.

3. **Execution Pipeline:**
   * Click **🚀 EXECUTE FULL AUTOMATED PIPELINE**.
   * HMS executes:
     * **Step 1:** Shot file validation and creation-time sorting.
     * **Step 2:** Trimming master audio starting at `196.603s` (`audio_trimmed.wav`).
     * **Step 3:** Parsing `117.5 BPM` transient beat grid (`thebeats.txt` & `hooktimestamp.txt`).
     * **Step 4:** Compiling `the_last_train_hook_timeline.xml` (xmeml v5) with embedded `v2.8.0` revision tags and 117.5 BPM blue transient markers.

---

## 4. DaVinci Resolve Import & NLE Post-Production Workflow

1. **Timeline Ingestion:**
   * Open DaVinci Resolve (Free or Studio).
   * Press **`Ctrl + Shift + I`** (**File > Import > Timeline...**).
   * Select `C:\renders\the_last_train\the_last_train_hook_timeline.xml`.
   * Confirm project framerate is `24.0 fps` (**`Shift + 9`**).

2. **Retime & Optical Flow Enhancements:**
   * Select `shot3.mp4` (slow-motion Jovan in time-lapse crowd).
   * In Inspector $\rightarrow$ **Retime and Scaling**, set **Retime Process** to **Optical Flow** and **Motion Estimation** to **Enhanced Better**.
   * Press **`Ctrl + R`** to open Retime Controls; add speed points to accelerate the crowd parts while holding Jovan's movement.

3. **Industrial Color Grade (`Shift + 6`):**
   * **Node 1 (Teal Base):** Push Lift/Gamma toward Cyan/Teal (`#1a3038`), desaturate non-essential colors to 35.0.
   * **Node 2 (Accent Red/Yellow Isolation):** Use Hue vs Sat curves to isolate and boost the yellow gloves (`shot1.mp4`), amber train sparks (`shot2.mp4`), and red train tail lights (`shot3.mp4`).
   * **Node 3 (Texture):** Add mild film grain to unify AI video generations.

4. **Hard Stop Finish:**
   * Ensure `shot5.mp4` ends dead-on the mechanical door slam audio transient, dropping the final frame instantly to black.

---
*Generated and validated for 337 West Productions — Hook Management System (HMS) Architecture v2.8.0*
