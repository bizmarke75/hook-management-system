[ Master Audio ] ──> [ Step 0: RMS Sliding Window + Librosa Beat Tracker ] ──> [ output/_hooktimestamp.txt ]└──> [ output/_thebeats.txt ][ Video Renders ] ──> [ Step 1: Natural-Sort Sequence Renamer ] ────────────> [ shot1.mp4 ... shotN.mp4 ][ Source Audio ]  ──> [ Step 2: SoundFile 24-bit PCM Audio Trimmer ] ────────> [ output/_master_audio.wav ][ Metadata State] ──> [ Step 3: State Verification & Marker Alignment ] ─────> [ In-Memory Sync ][ Assemble All ]  ──> [ Step 4: DaVinci Resolve FCP 7 XML Generator ] ───────> [ output/_davinci_timeline.xml ]
### Step 0: RMS Energy Sliding Window & Beat Detection
* Analyzes root-mean-square (RMS) signal energy across a sliding 40.0s window:
  $$\text{Energy}(t) = \int_{t}^{t + 40.0} \text{RMS}(y)^2 \, dt$$
* Automatically identifies the loudest, highest-impact hook/chorus segment (`hook_start_s` to `hook_end_s`).
* Employs Librosa onset strength and dynamic tempo estimation (~170.0 BPM default).
* **Relative Mapping Protocol:** Translates all transient beat hits into relative timestamps starting strictly at `0.000s` to `40.000s`, resolving negative offset and double-subtraction bugs.

### Step 1: Natural-Sort Video Sequencer
* Replaces standard ASCII alphabetical sorting (where `shot10.mp4` erroneously precedes `shot2.mp4`) with human natural numerical sorting via regular expression tokenization:
  ```python
  key = lambda p: [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', str(p.name))]
Renames all .mp4, .mov, and .mkv clips inside C:\renders\ sequentially (shot1.mp4 through shotN.mp4) using collision-safe temporary handles, ensuring zero dropped cuts.Step 2: Sub-Second 24-Bit PCM Audio Extraction (SoundFile)Replaces Python's native wave module with soundfile (libsndfile C-backend).Bypasses non-audio Suno AI Broadcast Wave Format (BWF) metadata chunks (bext, LIST, JUNK) that trigger seek crashes and empty 44-byte header corruptions.Extracts the exact 40.000-second window ($40.0 \times 44100 = 1,764,000$ audio samples) and exports an uncompressed 24-bit stereo WAV (~10.58 MB).Step 3: Metadata & State SynchronizationVerifies disk persistence of output/<slug>_hooktimestamp.txt, output/<slug>_thebeats.txt, and output/<slug>_master_audio.wav.Validates array continuity for all transient marker timestamps prior to timeline assembly.Step 4: DaVinci Resolve FCP 7 XML GenerationGenerates valid Apple Final Cut Pro 7 XML (xmeml version 5).Resolved Template Leak: Evaluates {total_frames} directly to integer 960 before writing to disk, preventing syntax parsing failures in DaVinci Resolve.Frame Budget Allocation: Divides the 960-frame budget across all video cuts evenly:$$\text{Clip Duration} = \left\lfloor \frac{960}{N} \right\rfloor + (1 \text{ if } i < (960 \pmod N) \text{ else } 0)$$Transient Marker Embedding: Embeds blue timeline markers (<color>Blue</color>) directly on the sequence ruler at frame $F = \text{round}(\text{timestamp} \times 24)$ within $0 \le F < 960$.3. Repository StructurePlaintexthook-management-system/
│
├── .github/
│   └── workflows/
│       └── build.yml               # Automated CI/CD PyInstaller build & GitHub release
│
├── docs/
│   └── DAVINCI_RESOLVE_SOP.md      # Standard Operating Procedure for XML timeline conform
│
├── output/                         # Automated output deliverables
│   ├── paper_dolls_davinci_timeline.xml
│   ├── paper_dolls_master_audio.wav
│   ├── paper_dolls_thebeats.txt
│   └── paper_dolls_hooktimestamp.txt
│
├── hms_master_gui.py               # Master Application: Tkinter dark UI + Steps 0-4
├── hms_master_gui.spec             # Hardened PyInstaller spec with hook neutralization
├── verify_timeline_xml.py          # Standalone headless XML & marker verification CLI
├── inline_patcher.py               # Local build hardening, hook patcher, and compiler
├── requirements.txt                # Production pinned dependency manifest
├── README.md                       # Master architecture documentation
└── .gitignore                      # Workspace and build exclusions
4. Installation & Local ExecutionSystem RequirementsOperating System: Windows 11 / Windows 10 x64Python Runtime: Python 3.10 (Recommended) or Python 3.11+DAW / NLE: DaVinci Resolve Free (v18.x, v19.x+)Environment InitializationPowerShell# 1. Clone the repository
git clone [https://github.com/bizmarke75/hook-management-system.git](https://github.com/bizmarke75/hook-management-system.git)
cd hook-management-system

# 2. Establish dedicated virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install pinned dependencies
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# 4. Verify DSP audio backend
python -c "import soundfile, librosa, scipy, numpy, tkinter; print('[SUCCESS] HMS environment verified.')"
Launch Master GUIPowerShellpython hms_master_gui.py
5. Master GUI Operation GuideThe HMS interface includes the thread-safe SafeLogRedirector, streaming live stdout/stderr simultaneously to the native Windows terminal and the in-app console:Audio Ingest: Click Browse Audio to load your master track. HMS automatically derives a clean project slug (e.g., paper_dolls.wav $\rightarrow$ paper_dolls).Video Ingest: Click Browse Folder and select your video render directory (e.g., C:\renders).Configure Parameters: Confirm Target BPM (170.0) and Duration (40.0).Execute Pipeline:Click RUN COMPLETE PIPELINE (Steps 0 -> 4) to run the complete automated pipeline in a background thread.Alternatively, use individual step buttons (Step 0 through Step 4) to inspect intermediate outputs.Output Delivery: Generated XML timelines, 24-bit audio, and beat logs are saved directly to output/.6. Headless XML Verification ToolAudit any generated timeline before launching DaVinci Resolve using the standalone headless diagnostic script:PowerShellpython verify_timeline_xml.py output\paper_dolls_davinci_timeline.xml
Diagnostic Output ExamplePlaintext[RUN] Auditing timeline XML: output\paper_dolls_davinci_timeline.xml
[INFO] Timebase confirmed: 24 fps (NTSC: FALSE).
[INFO] Auditing 12 video clip segments...
[INFO] Video continuity verified: 0 to 960 frames (gapless, no remainder drift).
[INFO] Audio track duration confirmed: 960 frames (40.000s @ 24fps).
[INFO] Master audio located: paper_dolls_master_audio.wav (10.58 MB, 24-bit PCM).
[INFO] Auditing 113 timeline markers...
[INFO] Marker audit: 113 transient pins verified within 0 <= frame < 960.
[SUCCESS] XML timeline verification passed with zero schema or continuity errors.
7. DaVinci Resolve Free Import SOPTo import generated timelines into DaVinci Resolve Free without Studio API restrictions:Launch DaVinci Resolve Free and create a new project.Open Project Settings (Shift + 9) and set Timeline frame rate to 24 under Master Settings > Timeline Format. Click Save.Press Ctrl + Shift + I (or navigate to File > Import > Timeline...).Select output/<slug>_davinci_timeline.xml.In the Load XML prompt:Uncheck Automatically set project settings.Check Automatically import source clips into media pool.Uncheck Ignore file extensions when matching.Click OK.Visual Quality Checkpoints in ResolveTimeline Duration: Ruler must read exactly 00:00:40:00 (Frame 960).Audio Track (A1): Immediate waveform display from frame 0 with zero silent padding or offset.Markers: ~113 blue markers positioned exactly on drum transients across the 40-second block.Video Track (V1): Gapless cuts across all shots with no missing-media indicators.8. Building the Standalone Executable LocallyTo compile the standalone portable binary without Python runtime dependencies:PowerShellpython inline_patcher.py
inline_patcher.py performs four automated build actions:Surgically patches PyInstaller's hook-setuptools.py to prevent Python 3.14 metadata comparison crashes.Writes a hardened hms_master_gui.spec with pyi_rth_pkgres neutralized.Compiles the binary via PyInstaller into dist\hms_master_gui\hms_master_gui.exe.Packages the complete release folder into dist\HMS_v3.0.0_Portable.zip.9. Automated CI/CD GitHub Actions BuildThe repository includes .github/workflows/build.yml for automated release packaging:Trigger: Pushing any version tag matching v* (e.g., git push origin v3.0.0).Runner: windows-latest running an isolated Python 3.10 environment.Pipeline: Checks out code, restores pip caches, installs pinned dependencies, compiles via PyInstaller, audits libsndfile dynamic link libraries, and uploads HMS_v3.0.0_Portable.zip directly to the GitHub release.10. Troubleshooting & Diagnostic MatrixSymptom / ErrorRoot CauseResolutionTypeError: '<' not supported between instances of 'NoneType' and 'tuple'PyInstaller hook-setuptools.py failing on Python 3.14 metadataRun python inline_patcher.py to apply the safe version check.AttributeError: module 'pkgutil' has no attribute 'ImpImporter'Python 3.14 removed ImpImporter, breaking pyi_rth_pkgres.pyUse hms_master_gui.spec with a.scripts filtering to neutralize the hook.ValueError: Target module "distutils" already imported as ExcludedModuleSpec file defined excludes=['distutils'], colliding with hook-distutilsKeep excludes=[] empty in hms_master_gui.spec.Trimmed WAV is 44 bytes / silentStandard wave module failed on Suno AI BWF metadata chunksStep 2 uses soundfile with subtype="PCM_24", which bypasses BWF chunks.DaVinci timeline drifts out of syncProject timebase was set to 23.976 fps instead of 24.0 fpsLock Project Settings to 24.0 fps before importing XML (Shift + 9).11. Production Track Verification StatusTrack NameGenre / StyleBPMHook WindowMarkersStatuspaper_dollsIndustrial Nu-Metal170.040.000s (960 frames)113 Blue PinsVERIFIED & CONFORMEDgrace_deficitIndustrial Nu-Metal170.040.000s (960 frames)113 Blue PinsVERIFIED & CONFORMED12. Ownership & Intellectual PropertyCopyright © 2026 Charles Pinkerton Sr. / 337 West Productions (Lancaster, PA). All Rights Reserved.Proprietary tooling developed for internal music video automation, DaVinci Resolve timeline interchange, and audio stem processing.
---

### Immediate Deployment Execution Checklist

Run these commands in PowerShell from `C:\github\projects\hook-management-system` to write the file, commit the repository changes, and trigger the GitHub Actions build:

```powershell
# 1. Stage the complete README and project assets
git add README.md requirements.txt docs/DAVINCI_RESOLVE_SOP.md .github/workflows/build.yml hms_master_gui.py hms_master_gui.spec inline_patcher.py

# 2. Commit the updates
git commit -m "docs: finalize complete production README.md for HMS v3.0.0"

# 3. Push to main
git push origin main

# 4. Re-anchor tag v3.0.0 and force-push to fire GitHub Actions
git tag -fa v3.0.0 -m "Hook Management System v3.0.0: Automated CI PyInstaller release"
git push origin v3.0.0 --force

# 5. Monitor automated build live in PowerShell
gh run watch