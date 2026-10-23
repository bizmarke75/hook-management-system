"""
337 West Productions - Hook Management System (HMS) v3.0.0
Module: hms_master_gui.py
Architecture: Tkinter Dark UI | SoundFile 24-bit Trimmer | Librosa Beat Tracker
Target: DaVinci Resolve Free 24fps FCP 7 XML (xmeml v5) Interchange
Standard: modular-python-builder
"""

import os
import sys
import re
import math
import time
import queue
import urllib.parse
import threading
import traceback
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import numpy as np
import soundfile as sf
import librosa

try:
    from PIL import Image
except ImportError:
    Image = None

MAX_ANALYSIS_FILE_MB = 512


# ==============================================================================
# THREAD-SAFE CONSOLE REDIRECTOR
# ==============================================================================

class SafeLogRedirector:
    """
    Thread-safe stream redirector capturing stdout/stderr into both the
    native CLI console and the Tkinter ScrolledText widget.
    """
    def __init__(self, text_widget, original_stream):
        self.text_widget = text_widget
        self.original_stream = original_stream

    def write(self, message):
        self.original_stream.write(message)
        self.original_stream.flush()
        try:
            self.text_widget.after(0, self._append_text, message)
        except Exception:
            pass

    def _append_text(self, message):
        try:
            self.text_widget.insert(tk.END, message)
            self.text_widget.see(tk.END)
        except Exception:
            pass

    def flush(self):
        self.original_stream.flush()


# ==============================================================================
# PIPELINE STEP 0: RMS ENERGY SLIDING-WINDOW & RELATIVE BEAT TRACKER
# ==============================================================================


def _validate_bpm(bpm_value: float) -> float:
    bpm = float(bpm_value)
    if not 40.0 <= bpm <= 300.0:
        raise ValueError(f"BPM must be between 40 and 300 (got {bpm}).")
    return bpm


def _validate_audio_analysis_size(audio_file: Path) -> None:
    if not audio_file.exists():
        raise FileNotFoundError(f"Source audio file not found: {audio_file}")

    file_size_mb = audio_file.stat().st_size / (1024 * 1024)
    if file_size_mb > MAX_ANALYSIS_FILE_MB:
        raise ValueError(
            f"Audio file is too large for in-memory analysis ({file_size_mb:.1f} MB > {MAX_ANALYSIS_FILE_MB} MB). "
            "Use a smaller source or a streaming analysis path in a future release."
        )


def _verify_video_dimensions(v_file: Path) -> tuple[int, int] | None:
    if Image is None:
        return None

    try:
        with Image.open(v_file) as img:
            width, height = img.size
            return width, height
    except Exception:
        return None


def run_step_0_audio_analysis(audio_path: str, slug: str, target_bpm: float = 170.0, window_duration: float = 40.0) -> dict:
    """
    Detects the peak RMS energy 40.0s hook window and tracks beat transients.
    Calculates relative timestamps (0.000s to 40.000s) for timeline synchronization.
    """
    print(f"\n[RUN] Step 0: Analyzing audio dynamics and transient beat markers for '{slug}'...")
    audio_file = Path(audio_path).resolve()
    _validate_audio_analysis_size(audio_file)
    bpm = _validate_bpm(target_bpm)

    output_dir = Path("output").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Reading '{audio_file.name}' for RMS sliding-window analysis...")
    y, sr = librosa.load(str(audio_file), sr=22050, mono=True)
    total_duration = librosa.get_duration(y=y, sr=sr)
    print(f"[INFO] Audio loaded: {total_duration:.2f}s total duration @ {sr} Hz.")

    if total_duration < window_duration:
        raise ValueError(f"Audio duration ({total_duration:.2f}s) is shorter than target window ({window_duration}s).")

    print(f"[INFO] Computing RMS energy curve across {window_duration}s window...")
    frame_length = 2048
    hop_length = 512
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    frames_per_sec = sr / hop_length
    window_frames = int(window_duration * frames_per_sec)

    window_kernel = np.ones(window_frames)
    integrated_energy = np.convolve(rms, window_kernel, mode="valid")

    best_frame_idx = int(np.argmax(integrated_energy))
    hook_start_s = round(float(best_frame_idx / frames_per_sec), 3)
    hook_end_s = round(hook_start_s + window_duration, 3)
    print(f"[SUCCESS] Hook window identified: {hook_start_s:.3f}s -> {hook_end_s:.3f}s ({window_duration:.1f}s window)")

    print(f"[INFO] Tracking beat transients (Target BPM ~{bpm})...")
    hook_sample_start = int(hook_start_s * sr)
    hook_sample_end = int(hook_end_s * sr)
    y_hook = y[hook_sample_start:hook_sample_end]

    tempo, beat_frames = librosa.beat.beat_track(y=y_hook, sr=sr, hop_length=hop_length, start_bpm=bpm)
    if isinstance(tempo, np.ndarray):
        tempo = float(tempo[0]) if tempo.size > 0 else bpm
    tempo_val = float(tempo)
    print(f"[INFO] Estimated local tempo: {tempo_val:.2f} BPM.")

    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)
    relative_beats = [round(float(b), 3) for b in beat_times if 0.0 <= b <= window_duration]
    print(f"[INFO] Captured {len(relative_beats)} relative transient pins.")

    hook_file = output_dir / f"{slug}_hooktimestamp.txt"
    beats_file = output_dir / f"{slug}_thebeats.txt"

    hook_file.write_text(f"{hook_start_s:.3f}\n{hook_end_s:.3f}\n{window_duration:.3f}\n", encoding="utf-8")
    beats_file.write_text("\n".join(f"{b:.3f}" for b in relative_beats) + "\n", encoding="utf-8")

    print(f"[SUCCESS] Saved hook timestamps: {hook_file.name}")
    print(f"[SUCCESS] Saved relative beat markers: {beats_file.name}")

    return {
        "slug": slug,
        "hook_start_s": hook_start_s,
        "hook_end_s": hook_end_s,
        "duration": window_duration,
        "detected_bpm": tempo_val,
        "beats": relative_beats
    }


# ==============================================================================
# PIPELINE STEP 1: NATURAL SORT SHOT SEQUENCE RENAMER
# ==============================================================================


def natural_sort_key(s):
    """Sorts strings containing numbers in standard human order (shot1, shot2, shot10)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]


def run_step_1_shot_renamer(renders_dir: str, slug: str) -> list:
    """
    Audits and renames render video clips sequentially (shot1.mp4 ... shotN.mp4)
    using natural numerical sorting to eliminate timeline sequencing gaps.
    """
    print(f"\n[RUN] Step 1: Auditing and standardizing render clips in '{renders_dir}'...")
    r_path = Path(renders_dir).resolve()
    if not r_path.exists():
        raise FileNotFoundError(f"Renders folder does not exist: {r_path}")

    extensions = {".mp4", ".mov", ".mkv"}
    video_files = [f for f in r_path.iterdir() if f.is_file() and f.suffix.lower() in extensions]

    if not video_files:
        raise ValueError(f"No video files ({', '.join(extensions)}) found in {r_path}")

    video_files.sort(key=lambda p: natural_sort_key(p.name))
    print(f"[INFO] Discovered {len(video_files)} video assets in renders directory.")

    temp_paths = []
    for idx, old_file in enumerate(video_files, start=1):
        temp_name = f"__hms_tmp_{slug}_{idx}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.mp4"
        temp_path = r_path / temp_name
        old_file.rename(temp_path)
        temp_paths.append((temp_path, idx))

    renamed_files = []
    for temp_path, idx in temp_paths:
        target_name = f"shot{idx}.mp4"
        target_path = r_path / target_name

        if target_path.exists() and target_path != temp_path:
            backup_name = f"__hms_backup_{uuid.uuid4().hex[:8]}_{target_name}"
            target_path.rename(r_path / backup_name)

        temp_path.rename(target_path)
        renamed_files.append(target_path)

    print(f"[SUCCESS] Confirmed {len(renamed_files)} sequential shots (shot1.mp4 -> shot{len(renamed_files)}.mp4).")
    return renamed_files


# ==============================================================================
# PIPELINE STEP 2: SUB-SECOND 24-BIT PCM STEREO WAV TRIMMER (SOUNDFILE)
# ==============================================================================


def run_step_2_audio_trimmer(audio_path: str, slug: str) -> Path:
    """
    Trims master audio exactly to the 40.000s hook window using SoundFile.
    Bypasses BWF chunk errors (bext, LIST, JUNK) and exports a clean 24-bit stereo WAV.
    """
    print(f"\n[RUN] Step 2: Extracting 24-bit PCM master audio slice using SoundFile backend...")
    output_dir = Path("output").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    hook_file = output_dir / f"{slug}_hooktimestamp.txt"

    if not hook_file.exists():
        raise FileNotFoundError(f"Hook timestamps not found at {hook_file}. Execute Step 0 first.")

    lines = [line.strip() for line in hook_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    hook_start_s = float(lines[0])
    duration_s = float(lines[2]) if len(lines) > 2 else 40.0

    print(f"[INFO] Trimming audio: start = {hook_start_s:.3f}s, duration = {duration_s:.3f}s")
    target_wav = output_dir / f"{slug}_master_audio.wav"

    with sf.SoundFile(str(audio_path), "r") as reader:
        sr = reader.samplerate
        channels = reader.channels
        start_frame = int(hook_start_s * sr)
        total_frames = int(duration_s * sr)

        reader.seek(start_frame)
        audio_data = reader.read(frames=total_frames, dtype="float32")

    if len(audio_data) < total_frames:
        raise ValueError(
            f"Short read while trimming audio: requested {total_frames} frames but only {len(audio_data)} frames were read. "
            f"Input file may be shorter than expected."
        )

    sf.write(str(target_wav), audio_data, samplerate=sr, subtype="PCM_24")

    file_size_mb = target_wav.stat().st_size / (1024 * 1024)
    if file_size_mb < 1.0:
        raise IOError(f"Trimmed WAV file size is abnormally small ({file_size_mb:.2f} MB). Possible 44-byte header corruption.")

    print(f"[SUCCESS] Exported 24-bit master audio: {target_wav.name} ({file_size_mb:.2f} MB, {sr} Hz, {channels} ch).")
    return target_wav


# ==============================================================================
# PIPELINE STEP 3: METADATA & STATE SYNCHRONIZATION
# ==============================================================================


def run_step_3_sync_metadata(slug: str) -> dict:
    """
    Validates output assets and reads cached beat transient timestamps.
    """
    print(f"\n[RUN] Step 3: Verifying pipeline state and metadata for '{slug}'...")
    output_dir = Path("output").resolve()
    hook_file = output_dir / f"{slug}_hooktimestamp.txt"
    beats_file = output_dir / f"{slug}_thebeats.txt"
    audio_wav = output_dir / f"{slug}_master_audio.wav"

    if not hook_file.exists():
        raise FileNotFoundError(f"Missing hook timestamps: {hook_file.name}")
    if not beats_file.exists():
        raise FileNotFoundError(f"Missing beat markers: {beats_file.name}")
    if not audio_wav.exists():
        raise FileNotFoundError(f"Missing master audio WAV: {audio_wav.name}")

    beats = [float(b.strip()) for b in beats_file.read_text(encoding="utf-8").splitlines() if b.strip()]
    print(f"[INFO] State synchronized: {len(beats)} transient beat markers loaded.")
    return {"slug": slug, "audio_wav": str(audio_wav), "beats": beats}


# ==============================================================================
# PIPELINE STEP 4: DAVINCI RESOLVE FCP 7 XML (xmeml v5) GENERATOR
# ==============================================================================


def run_step_4_generate_davinci_xml(slug: str, renders_dir: str, fps: int = 24, total_duration: float = 40.0) -> Path:
    """
    Generates an Apple Final Cut Pro 7 XML timeline for DaVinci Resolve Free.
    Assembles gapless video shots across exactly 960 frames and pins blue beat markers.
    """
    print(f"\n[RUN] Step 4: Assembling Apple FCP 7 XML timeline for '{slug}'...")
    output_dir = Path("output").resolve()
    audio_wav = output_dir / f"{slug}_master_audio.wav"
    beats_file = output_dir / f"{slug}_thebeats.txt"

    if not audio_wav.exists() or not beats_file.exists():
        raise FileNotFoundError("Missing master audio or beats file in output/. Run Steps 0-3 first.")

    total_frames = int(round(total_duration * fps))
    print(f"[INFO] Timeline duration: {total_duration:.3f}s | FPS: {fps} | Total Frames: {total_frames}")

    with sf.SoundFile(str(audio_wav), "r") as audio_reader:
        audio_samplerate = audio_reader.samplerate
        audio_channels = audio_reader.channels

    r_path = Path(renders_dir).resolve()
    video_files = [f for f in r_path.iterdir() if f.is_file() and f.suffix.lower() == ".mp4"]
    video_files.sort(key=lambda p: natural_sort_key(p.name))

    if not video_files:
        raise ValueError(f"No video files found in {r_path}")

    num_clips = len(video_files)
    frames_per_clip = total_frames // num_clips
    remainder_frames = total_frames % num_clips
    print(f"[INFO] Distributing {num_clips} video clips across {total_frames} frames...")

    video_clipitems_xml = []
    current_frame = 0

    for idx, v_file in enumerate(video_files):
        clip_dur = frames_per_clip + (1 if idx < remainder_frames else 0)
        start_frame = current_frame
        end_frame = current_frame + clip_dur
        current_frame = end_frame

        dim = _verify_video_dimensions(v_file)
        if dim is not None:
            width, height = dim
            if (width, height) != (1920, 1080):
                print(f"[WARN] Video dimensions differ from default Resolve template: {v_file.name} -> {width}x{height}.")

        norm_path = str(v_file.resolve()).replace("\\", "/")
        if not norm_path.startswith("/"):
            norm_path = "/" + norm_path
        file_url = f"file://localhost{urllib.parse.quote(norm_path)}"

        reel_name = v_file.stem
        clip_item = f"""
							<clipitem id="clipitem-video-{idx+1}">
								<name>{escape(v_file.name)}</name>
								<duration>{clip_dur}</duration>
								<rate>
									<timebase>{fps}</timebase>
									<ntsc>FALSE</ntsc>
								</rate>
								<in>0</in>
								<out>{clip_dur}</out>
								<start>{start_frame}</start>
								<end>{end_frame}</end>
								<reel>
									<name>{escape(reel_name)}</name>
								</reel>
								<file id="file-video-{idx+1}">
									<name>{escape(v_file.name)}</name>
									<pathurl>{file_url}</pathurl>
									<rate>
										<timebase>{fps}</timebase>
										<ntsc>FALSE</ntsc>
									</rate>
									<duration>{clip_dur}</duration>
									<media>
										<video>
											<samplecharacteristics>
												<width>1920</width>
												<height>1080</height>
											</samplecharacteristics>
										</video>
									</media>
								</file>
							</clipitem>"""
        video_clipitems_xml.append(clip_item)

    norm_audio = str(audio_wav.resolve()).replace("\\", "/")
    if not norm_audio.startswith("/"):
        norm_audio = "/" + norm_audio
    audio_url = f"file://localhost{urllib.parse.quote(norm_audio)}"

    sequence_id = str(uuid.uuid4())
    audio_clipitem_xml = f"""
							<clipitem id="clipitem-audio-1">
								<name>{escape(slug)}_master_audio.wav</name>
								<duration>{total_frames}</duration>
								<rate>
									<timebase>{fps}</timebase>
									<ntsc>FALSE</ntsc>
								</rate>
								<in>0</in>
								<out>{total_frames}</out>
								<start>0</start>
								<end>{total_frames}</end>
								<file id="file-audio-1">
									<name>{escape(slug)}_master_audio.wav</name>
									<pathurl>{audio_url}</pathurl>
									<rate>
										<timebase>{fps}</timebase>
										<ntsc>FALSE</ntsc>
									</rate>
									<duration>{total_frames}</duration>
									<media>
										<audio>
											<samplecharacteristics>
												<depth>24</depth>
												<samplerate>{audio_samplerate}</samplerate>
												<channelcount>{audio_channels}</channelcount>
											</samplecharacteristics>
										</audio>
									</media>
								</file>
							</clipitem>"""

    beats = [float(b.strip()) for b in beats_file.read_text(encoding="utf-8").splitlines() if b.strip()]
    markers_xml = []
    marker_count = 0

    for idx, beat_sec in enumerate(beats, start=1):
        marker_frame = int(round(beat_sec * fps))
        if 0 <= marker_frame < total_frames:
            m_xml = f"""
				<marker>
					<name>Beat {idx}</name>
					<comment>Transient {beat_sec:.3f}s</comment>
					<color>Blue</color>
					<in>{marker_frame}</in>
					<out>-1</out>
				</marker>"""
            markers_xml.append(m_xml)
            marker_count += 1

    print(f"[INFO] Encoded {marker_count} transient markers inside 0 <= frame < {total_frames}.")

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="5">
	<sequence id="{sequence_id}">
		<name>{escape(slug)}_davinci_timeline</name>
		<duration>{total_frames}</duration>
		<rate>
			<timebase>{fps}</timebase>
			<ntsc>FALSE</ntsc>
		</rate>
		{"".join(markers_xml)}
		<media>
			<video>
				<format>
					<samplecharacteristics>
						<width>1920</width>
						<height>1080</height>
						<pixelaspectratio>square</pixelaspectratio>
						<rate>
							<timebase>{fps}</timebase>
							<ntsc>FALSE</ntsc>
						</rate>
					</samplecharacteristics>
				</format>
				<track>
					{"".join(video_clipitems_xml)}
				</track>
			</video>
			<audio>
				<track>
					{audio_clipitem_xml}
				</track>
			</audio>
		</media>
	</sequence>
</xmeml>
"""

    timeline_xml = output_dir / f"{slug}_davinci_timeline.xml"
    timeline_xml.write_text(xml_content, encoding="utf-8")
    print(f"[SUCCESS] Timeline XML successfully written to: {timeline_xml.name}")
    return timeline_xml


# ==============================================================================
# TKINTER MASTER GUI
# ==============================================================================

class HMSMasterGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Hook Management System (HMS) v3.0.0 - 337 West Productions")
        self.geometry("960x780")
        self.minsize(800, 600)

        self.bg_color = "#1e1e1e"
        self.panel_color = "#252526"
        self.fg_color = "#d4d4d4"
        self.accent_color = "#007acc"
        self.btn_bg = "#333333"

        self.configure(bg=self.bg_color)
        self._setup_styles()
        self._create_widgets()

        if os.environ.get("HMS_DISABLE_GUI_REDIRECT") != "1":
            sys.stdout = SafeLogRedirector(self.console_text, sys.__stdout__)
            sys.stderr = SafeLogRedirector(self.console_text, sys.__stderr__)

        print("[INFO] Hook Management System (HMS) v3.0.0 initialized.")
        print("[INFO] Environment: 24.0 fps | 1080p | 40.000s timeline standard.")

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TLabel", background=self.bg_color, foreground=self.fg_color, font=("Consolas", 10))
        style.configure("TButton", font=("Consolas", 10, "bold"), padding=4)
        style.configure("Header.TLabel", font=("Consolas", 12, "bold"), foreground=self.accent_color)

    def _create_widgets(self):
        header = ttk.Label(self, text="HMS v3.0.0 :: AUTOMATED DAVINCI RESOLVE INTERCHANGE", style="Header.TLabel")
        header.pack(pady=(12, 6))

        param_frame = tk.LabelFrame(self, text=" Project Configuration ", bg=self.bg_color, fg=self.accent_color, font=("Consolas", 10, "bold"))
        param_frame.pack(fill="x", padx=15, pady=6)

        tk.Label(param_frame, text="Master Audio:", bg=self.bg_color, fg=self.fg_color, font=("Consolas", 9)).grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.audio_var = tk.StringVar(value="")
        self.audio_entry = tk.Entry(param_frame, textvariable=self.audio_var, width=65, bg=self.panel_color, fg=self.fg_color, insertbackground=self.fg_color)
        self.audio_entry.grid(row=0, column=1, padx=4, pady=4)
        tk.Button(param_frame, text="Browse Audio", command=self._browse_audio, bg=self.btn_bg, fg=self.fg_color).grid(row=0, column=2, padx=6, pady=4)

        tk.Label(param_frame, text="Renders Dir:", bg=self.bg_color, fg=self.fg_color, font=("Consolas", 9)).grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.renders_var = tk.StringVar(value=str(Path("C:/renders").resolve()))
        self.renders_entry = tk.Entry(param_frame, textvariable=self.renders_var, width=65, bg=self.panel_color, fg=self.fg_color, insertbackground=self.fg_color)
        self.renders_entry.grid(row=1, column=1, padx=4, pady=4)
        tk.Button(param_frame, text="Browse Folder", command=self._browse_renders, bg=self.btn_bg, fg=self.fg_color).grid(row=1, column=2, padx=6, pady=4)

        meta_subframe = tk.Frame(param_frame, bg=self.bg_color)
        meta_subframe.grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=6)

        tk.Label(meta_subframe, text="Track Slug:", bg=self.bg_color, fg=self.fg_color, font=("Consolas", 9)).pack(side="left")
        self.slug_var = tk.StringVar(value="paper_dolls")
        tk.Entry(meta_subframe, textvariable=self.slug_var, width=18, bg=self.panel_color, fg=self.fg_color).pack(side="left", padx=(4, 16))

        tk.Label(meta_subframe, text="Target BPM:", bg=self.bg_color, fg=self.fg_color, font=("Consolas", 9)).pack(side="left")
        self.bpm_var = tk.StringVar(value="170.0")
        tk.Entry(meta_subframe, textvariable=self.bpm_var, width=8, bg=self.panel_color, fg=self.fg_color).pack(side="left", padx=(4, 16))

        tk.Label(meta_subframe, text="Duration (s):", bg=self.bg_color, fg=self.fg_color, font=("Consolas", 9)).pack(side="left")
        self.duration_var = tk.StringVar(value="40.0")
        tk.Entry(meta_subframe, textvariable=self.duration_var, width=8, bg=self.panel_color, fg=self.fg_color).pack(side="left", padx=(4, 16))

        ctrl_frame = tk.LabelFrame(self, text=" Pipeline Execution ", bg=self.bg_color, fg=self.accent_color, font=("Consolas", 10, "bold"))
        ctrl_frame.pack(fill="x", padx=15, pady=6)

        self.run_all_btn = tk.Button(ctrl_frame, text="RUN COMPLETE PIPELINE (Steps 0 -> 4)", bg=self.accent_color, fg="white", font=("Consolas", 11, "bold"), command=self._start_complete_pipeline)
        self.run_all_btn.pack(fill="x", padx=8, pady=6)

        step_row = tk.Frame(ctrl_frame, bg=self.bg_color)
        step_row.pack(fill="x", padx=8, pady=(0, 6))

        tk.Button(step_row, text="Step 0 (RMS/Beats)", bg=self.btn_bg, fg=self.fg_color, command=lambda: self._run_step_async(0)).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(step_row, text="Step 1 (Renamer)", bg=self.btn_bg, fg=self.fg_color, command=lambda: self._run_step_async(1)).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(step_row, text="Step 2 (Trimmer)", bg=self.btn_bg, fg=self.fg_color, command=lambda: self._run_step_async(2)).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(step_row, text="Step 3 (Sync)", bg=self.btn_bg, fg=self.fg_color, command=lambda: self._run_step_async(3)).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(step_row, text="Step 4 (FCP7 XML)", bg=self.btn_bg, fg=self.fg_color, command=lambda: self._run_step_async(4)).pack(side="left", expand=True, fill="x", padx=2)

        console_frame = tk.LabelFrame(self, text=" Diagnostic Stream (SafeLogRedirector) ", bg=self.bg_color, fg=self.accent_color, font=("Consolas", 10, "bold"))
        console_frame.pack(fill="both", expand=True, padx=15, pady=(6, 12))

        self.console_text = scrolledtext.ScrolledText(console_frame, bg="#121212", fg="#00ff66", insertbackground="#00ff66", font=("Consolas", 9))
        self.console_text.pack(fill="both", expand=True, padx=6, pady=6)

    def _browse_audio(self):
        file_path = filedialog.askopenfilename(filetypes=[("Audio Files", "*.wav;*.mp3;*.flac;*.m4a"), ("All Files", "*.*")])
        if file_path:
            self.audio_var.set(file_path)
            derived_slug = re.sub(r'[^a-zA-Z0-9_]', '_', Path(file_path).stem.lower())
            self.slug_var.set(derived_slug)
            print(f"[INFO] Audio source selected: {Path(file_path).name} (Derived slug: '{derived_slug}')")

    def _browse_renders(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.renders_var.set(folder_path)
            print(f"[INFO] Renders directory selected: {folder_path}")

    def _start_complete_pipeline(self):
        self.run_all_btn.config(state="disabled")
        threading.Thread(target=self._execute_pipeline_worker, daemon=True).start()

    def _execute_pipeline_worker(self):
        try:
            audio_path = self.audio_var.get().strip()
            renders_path = self.renders_var.get().strip()
            slug = self.slug_var.get().strip()
            bpm = _validate_bpm(self.bpm_var.get().strip())
            duration = float(self.duration_var.get().strip())

            if not audio_path:
                print("[ERROR] Please select a master audio file.")
                return

            print("\n=======================================================")
            print(f"STARTING HMS MASTER PIPELINE: {slug.upper()}")
            print("=======================================================")

            run_step_0_audio_analysis(audio_path, slug, target_bpm=bpm, window_duration=duration)
            run_step_1_shot_renamer(renders_path, slug)
            run_step_2_audio_trimmer(audio_path, slug)
            run_step_3_sync_metadata(slug)
            xml_path = run_step_4_generate_davinci_xml(slug, renders_path, fps=24, total_duration=duration)

            print("\n=======================================================")
            print(f"[SUCCESS] COMPLETE PIPELINE FINISHED FOR: {slug}")
            print(f"Target XML: {xml_path}")
            print("Ready for DaVinci Resolve import (Ctrl + Shift + I).")
            print("=======================================================\n")

        except Exception as e:
            print(f"[ERROR] Pipeline failed: {str(e)}")
            print(traceback.format_exc())
        finally:
            self.run_all_btn.after(0, lambda: self.run_all_btn.config(state="normal"))

    def _run_step_async(self, step_idx):
        threading.Thread(target=self._step_worker, args=(step_idx,), daemon=True).start()

    def _step_worker(self, step_idx):
        try:
            audio_path = self.audio_var.get().strip()
            renders_path = self.renders_var.get().strip()
            slug = self.slug_var.get().strip()
            bpm = _validate_bpm(self.bpm_var.get().strip())
            duration = float(self.duration_var.get().strip())

            if step_idx == 0:
                run_step_0_audio_analysis(audio_path, slug, target_bpm=bpm, window_duration=duration)
            elif step_idx == 1:
                run_step_1_shot_renamer(renders_path, slug)
            elif step_idx == 2:
                run_step_2_audio_trimmer(audio_path, slug)
            elif step_idx == 3:
                run_step_3_sync_metadata(slug)
            elif step_idx == 4:
                run_step_4_generate_davinci_xml(slug, renders_path, fps=24, total_duration=duration)
        except Exception as e:
            print(f"[ERROR] Step {step_idx} execution error: {str(e)}")
            print(traceback.format_exc())


if __name__ == "__main__":
    app = HMSMasterGUI()
    app.mainloop()
