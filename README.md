# Hook Management System (HMS) v3.0.0

[![Release](https://img.shields.io/github/v/release/bizmarke75/hook-management-system?color=007acc&logo=github)](https://github.com/bizmarke75/hook-management-system/releases)
[![Platform](https://img.shields.io/badge/Platform-Windows%2011%20x64-blue?logo=windows)](https://github.com/bizmarke75/hook-management-system)
[![Interchange](https://img.shields.io/badge/Interchange-Apple%20FCP%207%20XML%20(xmeml%20v5)-orange)](https://www.blackmagicdesign.com/products/davinciresolve)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%20Tkinter%20%7C%20Librosa-green?logo=python)](https://python.org)

**Hook Management System (HMS) v3.0.0** is an automated desktop workstation and timeline interchange suite developed for **337 West Productions** (Lancaster, PA). HMS detects song hooks, tracks rhythm transients, standardizes multi-shot video renders, extracts broadcast-grade 24-bit PCM master audio, and programmatically generates Apple Final Cut Pro 7 XML (`xmeml v5`) project timelines targeted for **DaVinci Resolve Free** (bypassing Studio-only Python scripting API limitations).

---

## Production Standard & Interchange Parameters

| Parameter | Specification | Purpose / Standard |
| :--- | :--- | :--- |
| **Timeline Timebase** | **24.0 fps** | Cinematic standard conforming to 24fps AI video renders |
| **Hook Window Duration** | **40.000s** (Exactly 960 frames) | Standard music marketing hook showcase block |
| **Timeline Resolution** | **1920 × 1080 (1080p)** | Full HD square pixel aspect ratio (`1:1`) |
| **Audio Format** | **24-bit PCM Stereo WAV** | Broadcast-grade uncompressed audio @ 44.1 kHz |
| **Beat Marker Pinning** | **Relative Timeline Frame Map** | Snapped transient pins (`0 <= frame < 960`) |
| **Active Target Tracks** | `paper_dolls`, `grace_deficit` | 170 BPM industrial nu-metal (~113 transient beat pins) |

---

## Architectural Pipeline (Steps 0 → 4)

HMS executes a 5-stage sequential automation pipeline with strict error boundaries and diagnostic logging: