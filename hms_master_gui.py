"""
337 West Productions - Hook Management System (HMS) v3.09
Module: hms_master_gui.py
Architecture: Tkinter Dark UI | SoundFile 24-bit Trimmer | Librosa Beat Tracker
Target: DaVinci Resolve Free 24fps FCP 7 XML (xmeml v5) Interchange
Standard: modular-python-builder
"""

import argparse
import math
import os
import queue
import re
import sys
import threading
import time
import traceback
import urllib.parse
import uuid
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

from hms_metadata import probe_media
from hms_manifest import ManifestStore
from hms_safety import RollbackStore, is_dry_run, set_dry_run
from hms_v31_patcher import build_argument_parser, dispatch_cli

import librosa
import numpy as np
import soundfile as sf
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

MAX_ANALYSIS_FILE_MB = 512


# ==============================================================================
# GLOBAL HELPERS
# ==============================================================================


def _validate_bpm(bpm_value: float) -> float:
    bpm = float(bpm_value)
    if not 40.0 <= bpm <= 300.0:
        raise ValueError(f"Target BPM must be between 40 and 300 (got {bpm}).")
    return bpm


def _validate_duration(duration_value: float) -> float:
    duration = float(duration_value)
    if duration <= 0:
        raise ValueError("Duration must be positive.")
    if duration > 600:
        raise ValueError("Duration exceeds the maximum supported value (600s).")
    return duration


def _validate_audio_analysis_size(audio_file: Path) -> None:
    if not audio_file.exists():
        raise FileNotFoundError(f"Source audio file not found: {audio_file}")

    file_size_mb = audio_file.stat().st_size / (1024 * 1024)
    if file_size_mb > MAX_ANALYSIS_FILE_MB:
        raise ValueError(
            f"Audio file is too large for in-memory analysis ({file_size_mb:.1f} MB > {MAX_ANALYSIS_FILE_MB} MB). "
            "Use a smaller source or a streaming analysis path in a future release."
        )


def _fcpxml_rate(fps_value: str | int | float) -> tuple[int, str, float]:
    """Convert ffprobe's rational frame rate to FCP XML timebase and NTSC flag."""
    try:
        rate = Fraction(str(fps_value))
        value = float(rate)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f"Invalid media frame rate: {fps_value!r}.") from error
    if value <= 0:
        raise ValueError(f"Invalid media frame rate: {fps_value!r}.")

    for nominal, ntsc_rate in ((24, 24000 / 1001), (30, 30000 / 1001), (60, 60000 / 1001)):
        if abs(value - ntsc_rate) < 0.01:
            return nominal, "TRUE", value
    return max(1, int(round(value))), "FALSE", value


def _append_rate(parent: ET.Element, fps: int, ntsc: str = "FALSE") -> None:
    rate = ET.SubElement(parent, "rate")
    ET.SubElement(rate, "timebase").text = str(fps)
    ET.SubElement(rate, "ntsc").text = ntsc


def _append_clip_link(
    clip_item: ET.Element,
    clip_ref: str,
    media_type: str,
    track_index: int,
    clip_index: int,
) -> None:
    link = ET.SubElement(clip_item, "link")
    ET.SubElement(link, "linkclipref").text = clip_ref
    ET.SubElement(link, "mediatype").text = media_type
    ET.SubElement(link, "trackindex").text = str(track_index)
    ET.SubElement(link, "clipindex").text = str(clip_index)


def _file_path_url(path: Path) -> str:
    normalized_path = str(path.resolve()).replace("\\", "/")
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    return f"file://localhost{urllib.parse.quote(normalized_path, safe='/:')}"


def _frame_distribution_by_duration(
    video_files: list[Path],
    total_duration: float,
    fps: int,
    metadata: list[dict] | None = None,
) -> list[int]:
    tracked = [
        max(
            (metadata[idx] if metadata else probe_media(v_file)).get(
                "duration", total_duration / max(len(video_files), 1)
            ),
            0.01,
        )
        for idx, v_file in enumerate(video_files)
    ]

    total_weight = sum(tracked)
    if total_weight <= 0:
        return [int(round((total_duration * fps) / len(video_files))) for _ in video_files]

    target_total = int(round(total_duration * fps))
    raw_alloc = [target_total * (w / total_weight) for w in tracked]
    allocations = [int(math.floor(v)) for v in raw_alloc]
    remainder = target_total - sum(allocations)

    if remainder > 0:
        order = sorted(range(len(allocations)), key=lambda i: raw_alloc[i] - allocations[i], reverse=True)
        for idx in order[:remainder]:
            allocations[idx] += 1

    return allocations


# ==============================================================================
# THREAD-SAFE CONSOLE REDIRECTOR
# ==============================================================================

class SafeLogRedirector:
    """Thread-safe stream redirector capturing stdout/stderr into the Tk console."""

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


def run_step_0_audio_analysis(
    audio_path: str,
    slug: str,
    target_bpm: float = 170.0,
    window_duration: float = 40.0,
    dry_run: bool = False,
) -> dict:
    """Detects the peak RMS energy 40.0s hook window and tracks beat transients."""
    print(f"\n[RUN] Step 0: Analyzing audio dynamics and transient beat markers for '{slug}'...")
    audio_file = Path(audio_path).resolve()
    _validate_audio_analysis_size(audio_file)
    bpm = _validate_bpm(target_bpm)
    window_duration = _validate_duration(window_duration)

    output_dir = Path("output").resolve()

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

    if dry_run:
        print(f"[DRY-RUN] Would write hook timestamps: {hook_file}")
        print(f"[DRY-RUN] Would write {len(relative_beats)} beat markers: {beats_file}")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
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
        "beats": relative_beats,
    }


# ==============================================================================
# PIPELINE STEP 1: NATURAL SORT SHOT SEQUENCE RENAMER
# ==============================================================================


def natural_sort_key(s):
    """Sorts strings containing numbers in standard human order (shot1, shot2, shot10)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]


def run_step_1_shot_renamer(
    renders_dir: str,
    slug: str,
    dry_run: bool = False,
    rename_map_callback=None,
) -> list:
    """Renames render clips into a safe, zero-collision shot sequence."""
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

    rename_map = [
        {"original": current.name, "new": f"shot{index}.mp4"}
        for index, current in enumerate(video_files, start=1)
    ]
    if dry_run:
        for item in rename_map:
            print(f"[DRY-RUN] Rename {item['original']} -> {item['new']}")
        return [r_path / item["new"] for item in rename_map]
    if rename_map_callback:
        rename_map_callback(rename_map, "planned")

    temp_files = [
        r_path / f"__hms_tmp_{slug}_{index}_{uuid.uuid4().hex[:8]}.tmp"
        for index in range(len(video_files))
    ]
    target_files = [r_path / item["new"] for item in rename_map]
    finalized_indexes = set()
    try:
        for current, temp_path in zip(video_files, temp_files):
            current.rename(temp_path)
        for index, (temp_path, target_path) in enumerate(zip(temp_files, target_files)):
            temp_path.rename(target_path)
            finalized_indexes.add(index)
    except Exception:
        staged_for_recovery = []
        try:
            for index, (original, temp_path, target_path) in enumerate(
                zip(video_files, temp_files, target_files)
            ):
                current = (
                    target_path
                    if index in finalized_indexes
                    else temp_path if temp_path.exists() else original
                )
                if not current.exists():
                    raise RuntimeError(f"Cannot recover renamed render; missing {current}")
                recovery_path = r_path / f"__hms_recover_{uuid.uuid4().hex}.tmp"
                current.rename(recovery_path)
                staged_for_recovery.append((recovery_path, original))
            for recovery_path, original in staged_for_recovery:
                recovery_path.rename(original)
            if rename_map_callback:
                rename_map_callback(rename_map, "restored")
        except Exception as recovery_error:
            raise RuntimeError(
                "Shot renaming failed and automatic recovery was incomplete; "
                f"recovery files may remain in {r_path}: {recovery_error}"
            ) from recovery_error
        raise

    if rename_map_callback:
        rename_map_callback(rename_map, "completed")
    renamed_files = target_files

    print(f"[SUCCESS] Confirmed {len(renamed_files)} sequential shots (shot1.mp4 -> shot{len(renamed_files)}.mp4).")
    return renamed_files


# ==============================================================================
# PIPELINE STEP 2: SUB-SECOND 24-BIT PCM STEREO WAV TRIMMER (SOUNDFILE)
# ==============================================================================


def run_step_2_audio_trimmer(audio_path: str, slug: str, dry_run: bool = False) -> Path:
    """Trims master audio exactly to the configured hook window using SoundFile."""
    print(f"\n[RUN] Step 2: Extracting 24-bit PCM master audio slice using SoundFile backend...")
    output_dir = Path("output").resolve()
    hook_file = output_dir / f"{slug}_hooktimestamp.txt"

    if not hook_file.exists():
        raise FileNotFoundError(f"Hook timestamps not found at {hook_file}. Execute Step 0 first.")

    lines = [line.strip() for line in hook_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    hook_start_s = float(lines[0])
    duration_s = float(lines[2]) if len(lines) > 2 else 40.0

    print(f"[INFO] Trimming audio: start = {hook_start_s:.3f}s, duration = {duration_s:.3f}s")
    target_wav = output_dir / f"{slug}_master_audio.wav"
    if dry_run:
        print(f"[DRY-RUN] Would create {target_wav}")
        return target_wav

    with sf.SoundFile(str(audio_path), "r") as reader:
        sr = reader.samplerate
        channels = reader.channels
        start_frame = int(hook_start_s * sr)
        total_frames = int(duration_s * sr)

        reader.seek(start_frame)
        audio_data = reader.read(frames=total_frames, dtype="float32")

    if len(audio_data) != total_frames:
        raise ValueError(
            f"Expected {total_frames} frames, got {len(audio_data)} while trimming '{audio_path}'."
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
    """Validates output assets and reads cached beat transient timestamps."""
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


def run_step_4_generate_davinci_xml(
    slug: str,
    renders_dir: str,
    fps: int = 24,
    total_duration: float = 40.0,
    dry_run: bool = False,
) -> Path:
    """Generates a valid FCP7-compatible XML timeline using real media metadata."""
    print(f"\n[RUN] Step 4: Assembling Apple FCP 7 XML timeline for '{slug}'...")
    total_duration = _validate_duration(total_duration)

    output_dir = Path("output").resolve()
    audio_wav = output_dir / f"{slug}_master_audio.wav"
    beats_file = output_dir / f"{slug}_thebeats.txt"

    if not audio_wav.exists() or not beats_file.exists():
        raise FileNotFoundError("Missing master audio or beats file in output/. Run Steps 0-3 first.")

    audio_meta = probe_media(audio_wav)
    if not audio_meta["has_audio"]:
        raise ValueError(f"ffprobe did not find an audio stream in the master WAV: {audio_wav.name}")
    if audio_meta["duration"] <= 0:
        raise ValueError(f"ffprobe did not report the master WAV duration: {audio_wav.name}")
    sample_rate = audio_meta["samplerate"]
    channel_count = audio_meta["channels"]
    audio_depth = audio_meta["depth"]

    total_frames = int(round(total_duration * fps))
    print(f"[INFO] Timeline duration: {total_duration:.3f}s | FPS: {fps} | Total Frames: {total_frames}")

    r_path = Path(renders_dir).resolve()
    video_files = [f for f in r_path.iterdir() if f.is_file() and f.suffix.lower() == ".mp4"]
    video_files.sort(key=lambda p: natural_sort_key(p.name))

    if not video_files:
        raise ValueError(f"No video files found in {r_path}")

    video_metadata = [probe_media(video_file) for video_file in video_files]
    for video_file, metadata in zip(video_files, video_metadata):
        if not metadata["has_video"]:
            raise ValueError(f"Render does not contain a video stream: {video_file.name}")
        if metadata["duration"] <= 0:
            raise ValueError(f"ffprobe did not report the video duration: {video_file.name}")

    frame_alloc = _frame_distribution_by_duration(video_files, total_duration, fps, video_metadata)
    print(f"[INFO] Clip frame distribution: {frame_alloc}")

    root = ET.Element("xmeml", version="5")
    sequence_id = str(uuid.uuid4())
    sequence = ET.SubElement(root, "sequence", {"id": sequence_id})
    ET.SubElement(sequence, "name").text = f"{slug}_davinci_timeline"
    ET.SubElement(sequence, "duration").text = str(total_frames)
    _append_rate(sequence, fps)
    timecode = ET.SubElement(sequence, "timecode")
    _append_rate(timecode, fps)
    ET.SubElement(timecode, "string").text = "00:00:00:00"
    ET.SubElement(timecode, "frame").text = "0"
    ET.SubElement(timecode, "displayformat").text = "NDF"

    beats = [float(b.strip()) for b in beats_file.read_text(encoding="utf-8").splitlines() if b.strip()]
    for idx, beat_sec in enumerate(beats, start=1):
        marker_frame = int(round(beat_sec * fps))
        if 0 <= marker_frame < total_frames:
            marker = ET.SubElement(sequence, "marker")
            ET.SubElement(marker, "name").text = f"Beat {idx}"
            ET.SubElement(marker, "comment").text = f"Transient {beat_sec:.3f}s"
            ET.SubElement(marker, "color").text = "Blue"
            ET.SubElement(marker, "in").text = str(marker_frame)
            ET.SubElement(marker, "out").text = "-1"

    media = ET.SubElement(sequence, "media")
    video_media = ET.SubElement(media, "video")
    format_el = ET.SubElement(video_media, "format")
    sample_chars = ET.SubElement(format_el, "samplecharacteristics")
    sequence_metadata = max(video_metadata, key=lambda item: item["width"] * item["height"])
    ET.SubElement(sample_chars, "width").text = str(sequence_metadata["width"])
    ET.SubElement(sample_chars, "height").text = str(sequence_metadata["height"])
    ET.SubElement(sample_chars, "pixelaspectratio").text = "square"
    _append_rate(sample_chars, fps)

    track = ET.SubElement(video_media, "track")
    ET.SubElement(track, "enabled").text = "TRUE"
    ET.SubElement(track, "locked").text = "FALSE"
    current_frame = 0
    shot_clips = []

    for idx, (v_file, video_meta) in enumerate(zip(video_files, video_metadata)):
        clip_dur = frame_alloc[idx]
        start_frame = current_frame
        end_frame = current_frame + clip_dur
        current_frame = end_frame

        source_fps, source_ntsc, actual_source_fps = _fcpxml_rate(video_meta["fps"])
        source_duration = video_meta["duration"] or clip_dur / fps
        source_frames = max(1, int(round(source_duration * actual_source_fps)))
        source_clip_frames = max(1, int(round((clip_dur / fps) * actual_source_fps)))
        file_url = _file_path_url(v_file)
        video_clip_id = f"video-{idx + 1}"
        audio_clip_id = f"audio-{idx + 1}" if video_meta["has_audio"] else None
        file_id = f"file-shot-{idx + 1}"

        clip_item = ET.SubElement(track, "clipitem", {"id": video_clip_id})
        ET.SubElement(clip_item, "name").text = v_file.name
        ET.SubElement(clip_item, "enabled").text = "TRUE"
        ET.SubElement(clip_item, "duration").text = str(clip_dur)
        _append_rate(clip_item, fps)
        ET.SubElement(clip_item, "in").text = "0"
        ET.SubElement(clip_item, "out").text = str(source_clip_frames)
        ET.SubElement(clip_item, "start").text = str(start_frame)
        ET.SubElement(clip_item, "end").text = str(end_frame)

        reel = ET.SubElement(clip_item, "reel")
        ET.SubElement(reel, "name").text = v_file.stem

        file_node = ET.SubElement(clip_item, "file", {"id": file_id})
        ET.SubElement(file_node, "name").text = v_file.name
        ET.SubElement(file_node, "pathurl").text = file_url
        _append_rate(file_node, source_fps, source_ntsc)
        ET.SubElement(file_node, "duration").text = str(source_frames)
        media_node = ET.SubElement(file_node, "media")
        video_node = ET.SubElement(media_node, "video")
        sample_chars = ET.SubElement(video_node, "samplecharacteristics")
        ET.SubElement(sample_chars, "width").text = str(video_meta["width"])
        ET.SubElement(sample_chars, "height").text = str(video_meta["height"])
        _append_rate(sample_chars, source_fps, source_ntsc)
        if video_meta["has_audio"]:
            source_audio_node = ET.SubElement(media_node, "audio")
            source_sample_chars = ET.SubElement(source_audio_node, "samplecharacteristics")
            ET.SubElement(source_sample_chars, "depth").text = str(video_meta["depth"])
            ET.SubElement(source_sample_chars, "samplerate").text = str(video_meta["samplerate"])
            ET.SubElement(source_sample_chars, "channelcount").text = str(video_meta["channels"])
        source_track = ET.SubElement(clip_item, "sourcetrack")
        ET.SubElement(source_track, "mediatype").text = "video"
        ET.SubElement(source_track, "trackindex").text = "1"
        _append_clip_link(clip_item, video_clip_id, "video", 1, idx + 1)
        print(
            f"[INFO] {v_file.name}: {video_meta['width']}x{video_meta['height']} "
            f"@ {video_meta['fps']} fps; embedded audio: "
            f"{'yes' if video_meta['has_audio'] else 'no'}."
        )
        shot_clips.append(
            {
                "video_id": video_clip_id,
                "audio_id": audio_clip_id,
                "file_id": file_id,
                "file_name": v_file.name,
                "metadata": video_meta,
                "timeline_start": start_frame,
                "timeline_duration": clip_dur,
            }
        )

    audio_track = ET.SubElement(media, "audio")
    ET.SubElement(audio_track, "numOutputChannels").text = str(channel_count)
    audio_format = ET.SubElement(audio_track, "format")
    audio_sample_chars = ET.SubElement(audio_format, "samplecharacteristics")
    ET.SubElement(audio_sample_chars, "depth").text = str(audio_depth)
    ET.SubElement(audio_sample_chars, "samplerate").text = str(sample_rate)
    ET.SubElement(audio_sample_chars, "channelcount").text = str(channel_count)
    audio_track_node = ET.SubElement(audio_track, "track")
    ET.SubElement(audio_track_node, "enabled").text = "TRUE"
    ET.SubElement(audio_track_node, "locked").text = "FALSE"
    ET.SubElement(audio_track_node, "outputchannelindex").text = "1"
    audio_clip_item = ET.SubElement(audio_track_node, "clipitem", {"id": "master-audio"})
    ET.SubElement(audio_clip_item, "name").text = f"{slug}_master_audio.wav"
    ET.SubElement(audio_clip_item, "enabled").text = "TRUE"
    ET.SubElement(audio_clip_item, "duration").text = str(total_frames)
    _append_rate(audio_clip_item, fps)
    ET.SubElement(audio_clip_item, "in").text = "0"
    ET.SubElement(audio_clip_item, "out").text = str(total_frames)
    ET.SubElement(audio_clip_item, "start").text = "0"
    ET.SubElement(audio_clip_item, "end").text = str(total_frames)

    audio_file_node = ET.SubElement(audio_clip_item, "file", {"id": "file-master-audio"})
    ET.SubElement(audio_file_node, "name").text = f"{slug}_master_audio.wav"
    ET.SubElement(audio_file_node, "pathurl").text = _file_path_url(audio_wav)
    _append_rate(audio_file_node, fps)
    ET.SubElement(audio_file_node, "duration").text = str(total_frames)
    audio_media = ET.SubElement(audio_file_node, "media")
    audio_container = ET.SubElement(audio_media, "audio")
    sample_chars = ET.SubElement(audio_container, "samplecharacteristics")
    ET.SubElement(sample_chars, "depth").text = str(audio_depth)
    ET.SubElement(sample_chars, "samplerate").text = str(sample_rate)
    ET.SubElement(sample_chars, "channelcount").text = str(channel_count)
    source_track = ET.SubElement(audio_clip_item, "sourcetrack")
    ET.SubElement(source_track, "mediatype").text = "audio"
    ET.SubElement(source_track, "trackindex").text = "1"

    shot_audio_clips = [clip for clip in shot_clips if clip["audio_id"]]
    if shot_audio_clips:
        shot_audio_track = ET.SubElement(audio_track, "track")
        ET.SubElement(shot_audio_track, "enabled").text = "TRUE"
        ET.SubElement(shot_audio_track, "locked").text = "FALSE"
        ET.SubElement(shot_audio_track, "outputchannelindex").text = "1"

        for audio_index, clip in enumerate(shot_audio_clips, start=1):
            metadata = clip["metadata"]
            audio_duration = metadata["audio_duration"] or metadata["duration"]
            if audio_duration <= 0:
                raise ValueError(
                    f"Could not determine embedded audio duration for {clip['file_name']}."
                )
            audio_clip_frames = min(
                clip["timeline_duration"],
                max(1, int(round(audio_duration * fps))),
            )

            audio_item = ET.SubElement(
                shot_audio_track, "clipitem", {"id": clip["audio_id"]}
            )
            ET.SubElement(audio_item, "name").text = clip["file_name"]
            ET.SubElement(audio_item, "enabled").text = "TRUE"
            ET.SubElement(audio_item, "duration").text = str(audio_clip_frames)
            _append_rate(audio_item, fps)
            ET.SubElement(audio_item, "in").text = "0"
            ET.SubElement(audio_item, "out").text = str(audio_clip_frames)
            ET.SubElement(audio_item, "start").text = str(clip["timeline_start"])
            ET.SubElement(audio_item, "end").text = str(
                clip["timeline_start"] + audio_clip_frames
            )
            ET.SubElement(audio_item, "file", {"id": clip["file_id"]})
            source_track = ET.SubElement(audio_item, "sourcetrack")
            ET.SubElement(source_track, "mediatype").text = "audio"
            ET.SubElement(source_track, "trackindex").text = "1"

            video_index = int(clip["video_id"].rsplit("-", 1)[1])
            _append_clip_link(audio_item, clip["video_id"], "video", 1, video_index)
            _append_clip_link(audio_item, clip["audio_id"], "audio", 2, audio_index)
            video_item = track.find(f"clipitem[@id='{clip['video_id']}']")
            if video_item is None:
                raise RuntimeError(f"Missing generated video clip item: {clip['video_id']}")
            _append_clip_link(video_item, clip["audio_id"], "audio", 2, audio_index)

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    xml_content = xml_bytes.decode("utf-8")
    ET.fromstring(xml_content)

    timeline_xml = output_dir / f"{slug}_davinci_timeline.xml"
    if dry_run:
        print(f"[DRY-RUN] Would write {timeline_xml}")
        return timeline_xml
    timeline_xml.write_text(xml_content, encoding="utf-8")
    print(f"[SUCCESS] Timeline XML successfully written to: {timeline_xml.name}")
    return timeline_xml


def dry_run_pipeline(
    audio_path: str,
    renders_dir: str,
    slug: str,
    target_bpm: float = 170.0,
    duration: float = 40.0,
) -> None:
    """Validate and print a pipeline plan without changing source or output files."""
    audio_file = Path(audio_path).resolve()
    render_root = Path(renders_dir).resolve()
    _validate_audio_analysis_size(audio_file)
    _validate_bpm(target_bpm)
    duration = _validate_duration(duration)
    if not render_root.is_dir():
        raise NotADirectoryError(f"Renders folder does not exist: {render_root}")

    audio_metadata = probe_media(audio_file)
    if not audio_metadata["has_audio"]:
        raise ValueError(f"No audio stream found in master audio: {audio_file}")

    extensions = {".mp4", ".mov", ".mkv"}
    video_files = sorted(
        (
            path for path in render_root.iterdir()
            if path.is_file() and path.suffix.lower() in extensions
        ),
        key=lambda path: natural_sort_key(path.name),
    )
    if not video_files:
        raise ValueError(f"No video files ({', '.join(sorted(extensions))}) found in {render_root}")

    output_dir = Path.cwd() / "output"
    print(f"[DRY-RUN] Track: {slug}; target BPM: {target_bpm:g}; duration: {duration:g}s.")
    print(f"[DRY-RUN] Master audio: {audio_file.name}.")
    print(f"[DRY-RUN] Found {len(video_files)} source shot(s):")
    for index, video_file in enumerate(video_files, start=1):
        metadata = probe_media(video_file)
        if not metadata["has_video"]:
            raise ValueError(f"Render does not contain a video stream: {video_file.name}")
        target_name = f"shot{index}.mp4"
        print(
            f"[DRY-RUN] Rename {video_file.name} -> {target_name}; "
            f"{metadata['width']}x{metadata['height']} @ {metadata['fps']} fps; "
            f"embedded audio: {'yes' if metadata['has_audio'] else 'no'}."
        )
    for suffix in RollbackStore.OUTPUT_SUFFIXES:
        destination = output_dir / f"{slug}{suffix}"
        action = "backup and replace" if destination.exists() else "create"
        print(f"[DRY-RUN] Would {action} {destination}")
    print("[DRY-RUN] No files were changed.")


def execute_pipeline(
    audio_path: str,
    renders_path: str,
    slug: str,
    bpm: float = 170.0,
    duration: float = 40.0,
    dry_run: bool = False,
) -> Path | None:
    dry_run = dry_run or is_dry_run()
    if dry_run:
        dry_run_pipeline(audio_path, renders_path, slug, bpm, duration)
        return None

    store = RollbackStore()
    run_id = store.begin_run(slug, audio_path, renders_path)
    print(f"[INFO] Recovery manifest created: rollback/{run_id}/manifest.json")
    try:
        print(f"\nSTARTING HMS MASTER PIPELINE: {slug.upper()} ({run_id})")
        run_step_0_audio_analysis(audio_path, slug, target_bpm=bpm, window_duration=duration)
        run_step_1_shot_renamer(
            renders_path,
            slug,
            rename_map_callback=lambda mapping, state: store.set_rename_map(
                run_id, mapping, state
            ),
        )
        run_step_2_audio_trimmer(audio_path, slug)
        run_step_3_sync_metadata(slug)
        xml_path = run_step_4_generate_davinci_xml(
            slug, renders_path, fps=24, total_duration=duration
        )
        beats_file = Path.cwd() / "output" / f"{slug}_thebeats.txt"
        marker_count = sum(bool(line.strip()) for line in beats_file.read_text(encoding="utf-8").splitlines())
        store.finish_run(run_id, "completed", marker_count=marker_count)
        print(f"[SUCCESS] COMPLETE PIPELINE FINISHED FOR: {slug}")
        print(f"[SUCCESS] Run {run_id} recorded; recovery data is in rollback/{run_id}.")
        print(f"Target XML: {xml_path}")
        return xml_path
    except Exception as error:
        store.finish_run(run_id, "failed", error=str(error))
        print(f"[ERROR] Run {run_id} failed and is available for rollback.")
        raise


def verify_pipeline_outputs(slug: str, renders_dir: str | None = None, duration: float = 40.0) -> bool:
    """Check generated files and validate the existing XML without modifying them."""
    duration = _validate_duration(duration)
    output_dir = Path.cwd() / "output"
    required = [
        output_dir / f"{slug}_hooktimestamp.txt",
        output_dir / f"{slug}_thebeats.txt",
        output_dir / f"{slug}_master_audio.wav",
        output_dir / f"{slug}_davinci_timeline.xml",
    ]
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Verify-only failed; required outputs are missing: "
            + ", ".join(str(path) for path in missing)
        )
    if renders_dir:
        renders_path = Path(renders_dir).resolve()
        if not renders_path.is_dir():
            raise NotADirectoryError(f"Renders folder does not exist: {renders_path}")
        if not any(path.is_file() for path in renders_path.glob("shot*.mp4")):
            raise FileNotFoundError(f"No sequenced shot*.mp4 files found in {renders_path}")

    from verify_timeline_xml import verify_davinci_xml

    xml_path = required[-1]
    if duration != 40.0:
        raise ValueError("The current timeline verifier requires a 40-second timeline.")
    if not verify_davinci_xml(str(xml_path)):
        raise RuntimeError(f"Timeline verification failed: {xml_path}")
    print(f"[SUCCESS] Existing pipeline outputs verified: {slug}")
    return True


def parse_cli() -> argparse.Namespace:
    """Parse the command-line options shared by HMS launchers."""
    return build_argument_parser().parse_args()


def cli_bootstrap() -> argparse.Namespace:
    """Handle CLI actions before launching the GUI."""
    parser = build_argument_parser()
    args = parse_cli()
    if args.dry_run:
        print("[INFO] HMS DRY-RUN mode enabled.")
    try:
        handled = dispatch_cli(args, gui_factory=HMSMasterGUI)
    except Exception as error:
        parser.error(str(error))
    if handled:
        raise SystemExit(0)
    return args


# ==============================================================================
# TKINTER MASTER GUI
# ==============================================================================

class HMSMasterGUI(tk.Tk):
    def __init__(self, dry_run: bool = False):
        super().__init__()
        self.initial_dry_run = dry_run
        self.title("Hook Management System (HMS) v3.09 - 337 West Productions")
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

        print("[INFO] Hook Management System (HMS) v3.09 initialized.")
        print("[INFO] Environment: 24.0 fps | 1080p | 40.000s timeline standard.")

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TLabel", background=self.bg_color, foreground=self.fg_color, font=("Consolas", 10))
        style.configure("TButton", font=("Consolas", 10, "bold"), padding=4)
        style.configure("Header.TLabel", font=("Consolas", 12, "bold"), foreground=self.accent_color)

    def _create_widgets(self):
        header = ttk.Label(self, text="HMS v3.09 :: AUTOMATED DAVINCI RESOLVE INTERCHANGE", style="Header.TLabel")
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

        safety_row = tk.Frame(ctrl_frame, bg=self.bg_color)
        safety_row.pack(fill="x", padx=8, pady=(0, 6))

        self.dry_run_var = tk.BooleanVar(value=self.initial_dry_run)
        tk.Checkbutton(
            safety_row,
            text="DRY RUN",
            variable=self.dry_run_var,
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.panel_color,
            activebackground=self.bg_color,
            activeforeground=self.fg_color,
        ).pack(side="left", padx=4)
        tk.Button(
            safety_row,
            text="LIST RUNS",
            bg=self.btn_bg,
            fg=self.fg_color,
            command=self._list_runs_gui,
        ).pack(side="left", padx=4)
        tk.Button(
            safety_row,
            text="ROLLBACK LAST RUN",
            bg="#9c2b2e",
            fg="white",
            command=self._rollback_last_run_gui,
        ).pack(side="left", padx=4)
        tk.Button(
            safety_row,
            text="RESTORE RUN",
            bg="#715500",
            fg="white",
            command=self._restore_run_gui,
        ).pack(side="left", padx=4)

        verify_row = tk.Frame(ctrl_frame, bg=self.bg_color)
        verify_row.pack(fill="x", padx=8, pady=(0, 6))
        tk.Button(
            verify_row,
            text="VERIFY ONLY",
            bg=self.btn_bg,
            fg=self.fg_color,
            command=self._verify_only_async,
        ).pack(side="left", expand=True, fill="x", padx=2)

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
        dry_run = self.dry_run_var.get()
        threading.Thread(
            target=self._execute_pipeline_worker,
            args=(dry_run,),
            daemon=True,
        ).start()

    def _execute_pipeline_worker(self, dry_run: bool = False):
        set_dry_run(dry_run)
        try:
            audio_path = self.audio_var.get().strip()
            renders_path = self.renders_var.get().strip()
            slug = self.slug_var.get().strip()
            bpm = _validate_bpm(self.bpm_var.get().strip())
            duration = _validate_duration(self.duration_var.get().strip())

            if not audio_path:
                print("[ERROR] Please select a master audio file.")
                return

            xml_path = execute_pipeline(
                audio_path,
                renders_path,
                slug,
                bpm,
                duration,
                dry_run=dry_run,
            )
            if xml_path:
                print("Ready for DaVinci Resolve import (Ctrl + Shift + I).")

        except Exception as e:
            print(f"[ERROR] Pipeline failed: {str(e)}")
            print(traceback.format_exc())
        finally:
            self.run_all_btn.after(0, lambda: self.run_all_btn.config(state="normal"))

    def _run_step_async(self, step_idx):
        dry_run = self.dry_run_var.get()
        threading.Thread(
            target=self._step_worker,
            args=(step_idx, dry_run),
            daemon=True,
        ).start()

    def _step_worker(self, step_idx, dry_run: bool = False):
        set_dry_run(dry_run)
        try:
            audio_path = self.audio_var.get().strip()
            renders_path = self.renders_var.get().strip()
            slug = self.slug_var.get().strip()
            bpm = _validate_bpm(self.bpm_var.get().strip())
            duration = _validate_duration(self.duration_var.get().strip())
            if step_idx == 0:
                run_step_0_audio_analysis(audio_path, slug, target_bpm=bpm, window_duration=duration, dry_run=dry_run)
            elif step_idx == 1:
                run_step_1_shot_renamer(renders_path, slug, dry_run=dry_run)
            elif step_idx == 2:
                run_step_2_audio_trimmer(audio_path, slug, dry_run=dry_run)
            elif step_idx == 3:
                run_step_3_sync_metadata(slug)
            elif step_idx == 4:
                run_step_4_generate_davinci_xml(slug, renders_path, fps=24, total_duration=duration, dry_run=dry_run)
        except Exception as e:
            print(f"[ERROR] Step {step_idx} execution error: {str(e)}")
            print(traceback.format_exc())

    def _verify_only_async(self):
        threading.Thread(target=self._verify_only_worker, daemon=True).start()

    def _verify_only_worker(self):
        try:
            verify_pipeline_outputs(
                self.slug_var.get().strip(),
                self.renders_var.get().strip(),
                float(self.duration_var.get().strip()),
            )
        except Exception as error:
            print(f"[ERROR] Verify-only failed: {error}")
            print(traceback.format_exc())

    def _list_runs_gui(self):
        try:
            runs = ManifestStore().list_runs()
            if not runs:
                messagebox.showinfo("HMS", "No snapshots found.", parent=self)
                return
            report = [
                f"{run['run_id']}  |  {run.get('slug', '')}  |  "
                f"{run.get('timestamp', '')}  |  {run.get('status', '')}"
                for run in runs
            ]
            messagebox.showinfo(
                "Snapshot History", "\n".join(report), parent=self
            )
        except Exception as error:
            messagebox.showerror("Error", str(error), parent=self)

    def _rollback_last_run_gui(self):
        if not messagebox.askyesno("Rollback last run", "Restore the most recent completed or failed run?"):
            return
        threading.Thread(target=self._recovery_worker, args=(None,), daemon=True).start()

    def _restore_run_gui(self):
        run_id = simpledialog.askstring(
            "Restore run",
            "Enter a run ID (for example, run_003):",
            parent=self,
        )
        if not run_id:
            return
        if not messagebox.askyesno("Restore run", f"Restore {run_id} and undo its renames and outputs?"):
            return
        threading.Thread(target=self._recovery_worker, args=(run_id,), daemon=True).start()

    def _recovery_worker(self, run_id):
        try:
            store = RollbackStore()
            manifest = store.rollback_last_run() if run_id is None else store.restore_run(run_id)
            print(f"[SUCCESS] Restored run {manifest['run_id']}.")
        except Exception as error:
            print(f"[ERROR] Restore failed: {error}")
            print(traceback.format_exc())


if __name__ == "__main__":
    arguments = cli_bootstrap()
    app = HMSMasterGUI(dry_run=arguments.dry_run)
    app.mainloop()
