# DaVinci Resolve Import Standard Operating Procedure (SOP)

**System Version:** `v2.8.0`  
**Target NLE:** DaVinci Resolve Free / Studio (v18, v19, v20)  

---

## 📌 Protocol Summary

The HMS v2.8.0 workflow outputs a single, fully-assembled Final Cut Pro 7 XML (`xmeml v5`) timeline file (`<track_slug>_hook_timeline.xml`) containing:
1. Sequenced video clips (`shot1.mp4` ... `shotN.mp4`)
2. Sub-second trimmed master audio WAV (`<track_slug>_master_trimmed.wav`)
3. Embedded blue transient beat markers (~64 markers at 95.7 BPM)

---

## ⚙️ Step-by-Step Import Steps

1. Launch DaVinci Resolve and create or open your project.
2. Press **Shift + 9** to open **Project Settings**. Set **Timeline Frame Rate** to **24 fps**.
3. Go to **File > Import > Timeline...** (or press **Ctrl + Shift + I** / **Cmd + Shift + I**).
4. Select `C:\renders\<track_slug>\<track_slug>_hook_timeline.xml`.
5. Press **N** on your keyboard to enable **Timeline Snapping**. Cuts, speed points (**Ctrl + R**), and transitions will magnetically lock onto the blue beat marker flags.
