"""
337 West Productions - Hook Management System (HMS) v3.16 Experimental
Module: hms_master_gui.py
Architecture: Tkinter Dark UI | SoundFile 24-bit Trimmer | Librosa Beat Tracker
Target: DaVinci Resolve Free 24fps FCP 7 XML (xmeml v5) Interchange
Standard: modular-python-builder
"""

import argparse
import fnmatch
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
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

from hms_metadata import probe_media
from hms_manifest import ManifestStore
from hms_safety import (
    LEGACY_MASTER_AUDIO_SUFFIX,
    MASTER_AUDIO_SUFFIX,
    RollbackStore,
    SUBTITLE_SUFFIX,
    is_dry_run,
    set_dry_run,
)
from hms_v31_patcher import build_argument_parser, dispatch_cli

import librosa
import numpy as np
import soundfile as sf
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

MAX_ANALYSIS_FILE_MB = 512
DEFAULT_TARGET_BPM = 170.0
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SUPPORTED_RENDER_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS


# ==============================================================================
# GLOBAL HELPERS
# ==============================================================================

def _resolve_output_dir(output_dir: str | Path | None = None) -> Path:
    return Path(output_dir).expanduser().resolve() if output_dir else (Path.cwd() / "output").resolve()


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


def estimate_audio_bpm(audio_path: str | Path) -> float:
    """Estimate tempo from the selected audio without using a previous track's BPM."""
    audio_file = Path(audio_path).expanduser().resolve()
    _validate_audio_analysis_size(audio_file)
    y, sr = librosa.load(str(audio_file), sr=22050, mono=True)
    onset_envelope = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
    if onset_envelope.size == 0 or float(np.max(onset_envelope)) <= 0:
        raise ValueError("No beat activity was detected in the selected audio.")
    tempos = librosa.feature.tempo(
        onset_envelope=onset_envelope,
        sr=sr,
        hop_length=512,
        aggregate=np.median,
        max_tempo=300.0,
    )
    tempo = float(np.asarray(tempos).reshape(-1)[0])
    return round(_validate_bpm(tempo), 2)


def parse_file_patterns(value: str) -> list[str]:
    return [pattern.strip() for pattern in re.split(r"[,;\n]", value) if pattern.strip()]


def _parse_srt_timestamp(value: str) -> int:
    match = re.fullmatch(r"(\d{2}):([0-5]\d):([0-5]\d)[,.](\d{3})", value.strip())
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value!r}")
    hours, minutes, seconds, milliseconds = map(int, match.groups())
    return (((hours * 60 + minutes) * 60 + seconds) * 1000) + milliseconds


def _format_srt_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def _render_srt_sidecar(
    source_path: str | Path,
    start_seconds: float,
    duration_seconds: float,
) -> str:
    """Return SRT cues clipped and retimed to a timeline segment."""
    source = Path(source_path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".srt":
        raise ValueError(f"Subtitle file must be an existing .srt file: {source}")

    content = source.read_text(encoding="utf-8-sig")
    segment_start = max(0, int(round(start_seconds * 1000)))
    segment_end = segment_start + int(round(duration_seconds * 1000))
    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", content.strip()):
        lines = block.splitlines()
        timing_index = next(
            (index for index, line in enumerate(lines) if "-->" in line), None
        )
        if timing_index is None:
            raise ValueError("Invalid SRT file: each subtitle block needs a timing line.")
        timing = re.fullmatch(
            r"\s*(\S+)\s*-->\s*(\S+)(?:\s+.*)?", lines[timing_index]
        )
        if timing is None:
            raise ValueError(f"Invalid SRT timing line: {lines[timing_index]!r}")
        cue_start, cue_end = (
            _parse_srt_timestamp(timing.group(1)),
            _parse_srt_timestamp(timing.group(2)),
        )
        if cue_end <= cue_start:
            raise ValueError("Invalid SRT cue: end time must be after start time.")
        text = "\n".join(lines[timing_index + 1 :]).strip()
        if not text:
            raise ValueError("Invalid SRT cue: subtitle text is empty.")
        clipped_start = max(cue_start, segment_start)
        clipped_end = min(cue_end, segment_end)
        if clipped_end > clipped_start:
            cues.append(
                (
                    clipped_start - segment_start,
                    clipped_end - segment_start,
                    text,
                )
            )

    if not cues:
        raise ValueError("No SRT subtitle cues overlap the selected timeline duration.")

    blocks = [
        f"{index}\n{_format_srt_timestamp(start)} --> "
        f"{_format_srt_timestamp(end)}\n{text}"
        for index, (start, end, text) in enumerate(cues, start=1)
    ]
    return "\n\n".join(blocks) + "\n"


def write_srt_sidecar(
    source_path: str | Path,
    output_path: str | Path,
    start_seconds: float,
    duration_seconds: float,
) -> Path:
    """Write SRT cues clipped and retimed to a timeline segment."""
    content = _render_srt_sidecar(source_path, start_seconds, duration_seconds)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return output


def derive_slug_from_audio(audio_path: str | Path) -> str:
    stem = Path(audio_path).stem
    for suffix in ("_master_trimmed", "_master_audio", "_trimmed", "_master"):
        if stem.casefold().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return re.sub(r"[^a-zA-Z0-9_]", "_", stem.lower()).strip("_")


def select_render_files(
    renders_dir: str | Path,
    include_patterns: Sequence[str] | None,
    exclude_patterns: Sequence[str] | None = None,
    extensions: set[str] | None = None,
) -> list[Path]:
    render_root = Path(renders_dir).expanduser().resolve()
    if not render_root.is_dir():
        raise NotADirectoryError(f"Renders folder does not exist: {render_root}")

    includes = [pattern.strip() for pattern in (include_patterns or ()) if pattern.strip()]
    excludes = [pattern.strip() for pattern in (exclude_patterns or ()) if pattern.strip()]
    if not includes:
        raise ValueError(
            "Select the intended shot clips with at least one include name or glob "
            "(for example: shot_2a*, shot_2b*). HMS will not rename every video "
            "in the folder by default."
        )
    if any("/" in pattern or "\\" in pattern for pattern in includes + excludes):
        raise ValueError("Clip include/exclude patterns must match file names, not paths.")

    allowed_extensions = extensions or VIDEO_EXTENSIONS
    candidates = [
        path for path in render_root.iterdir()
        if path.is_file() and path.suffix.lower() in allowed_extensions
    ]
    selected = []
    seen = set()
    for pattern in includes:
        matches = sorted(
            (
                path for path in candidates
                if fnmatch.fnmatchcase(path.name.casefold(), pattern.casefold())
                and not any(
                    fnmatch.fnmatchcase(path.name.casefold(), excluded.casefold())
                    for excluded in excludes
                )
            ),
            key=lambda path: (natural_sort_key(path.name), path.name.casefold()),
        )
        for path in matches:
            identity = str(path).casefold()
            if identity not in seen:
                selected.append(path)
                seen.add(identity)
    if not selected:
        raise ValueError(
            f"No render media matched include patterns {includes!r} "
            f"(exclude patterns: {excludes!r}) in {render_root}."
        )
    return selected


def _validate_selected_render_files(
    renders_dir: str | Path,
    selected_files: Sequence[str | Path] | None,
    extensions: set[str] | None = None,
) -> list[Path]:
    if not selected_files:
        raise ValueError("No shot clips were selected. Set include patterns before running this step.")
    render_root = Path(renders_dir).expanduser().resolve()
    allowed_extensions = extensions or SUPPORTED_RENDER_EXTENSIONS
    selected = []
    seen = set()
    for selected_file in selected_files:
        path = Path(selected_file).expanduser().resolve()
        if path.parent != render_root:
            raise ValueError(f"Selected clip must be directly inside the renders folder: {path}")
        if path.suffix.lower() not in allowed_extensions or not path.is_file():
            raise ValueError(f"Selected clip is missing or has an unsupported format: {path}")
        identity = str(path).casefold()
        if identity not in seen:
            selected.append(path)
            seen.add(identity)
    if not selected:
        raise ValueError("No valid shot clips were selected.")
    return selected


def _build_rename_map(renders_dir: str | Path, video_files: Sequence[Path]) -> list[dict]:
    render_root = Path(renders_dir).expanduser().resolve()
    rename_map = [
        {"original": current.name, "new": f"shot{index}{current.suffix.lower()}"}
        for index, current in enumerate(video_files, start=1)
    ]
    source_paths = {path.resolve() for path in video_files}
    collisions = [
        render_root / item["new"]
        for item in rename_map
        if (render_root / item["new"]).exists()
        and (render_root / item["new"]).resolve() not in source_paths
    ]
    if collisions:
        raise FileExistsError(
            "Shot rename blocked; target names already belong to unselected files: "
            + ", ".join(str(path) for path in collisions)
        )
    return rename_map


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


def _full_song_video_frame_distribution(
    total_duration: float,
    fps: int,
    metadata: Sequence[dict],
) -> list[int]:
    target_frames = int(round(total_duration * fps))
    source_frames = [
        max(1, int(round(float(item.get("duration", 0)) * fps)))
        for item in metadata
    ]
    available_frames = sum(source_frames)
    if available_frames < target_frames:
        available_duration = available_frames / fps
        raise ValueError(
            f"Selected video clips provide about {available_duration:.2f}s of footage, "
            f"but the full song needs {total_duration:.2f}s. Add more video shots/files "
            "before running the full-song video workflow."
        )

    allocations = []
    remaining_frames = target_frames
    for clip_frames in source_frames:
        allocation = min(clip_frames, remaining_frames)
        allocations.append(allocation)
        remaining_frames -= allocation
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
    output_dir: str | Path | None = None,
    full_song: bool = False,
) -> dict:
    """Find a hook window, or analyze the whole song for a full-length timeline."""
    dry_run = dry_run or is_dry_run()
    print(f"\n[RUN] Step 0: Analyzing audio dynamics and transient beat markers for '{slug}'...")
    audio_file = Path(audio_path).resolve()
    _validate_audio_analysis_size(audio_file)
    bpm = _validate_bpm(target_bpm)
    window_duration = _validate_duration(window_duration)

    output_dir = _resolve_output_dir(output_dir)

    print(f"[INFO] Reading '{audio_file.name}' for RMS sliding-window analysis...")
    y, sr = librosa.load(str(audio_file), sr=22050, mono=True)
    total_duration = librosa.get_duration(y=y, sr=sr)
    print(f"[INFO] Audio loaded: {total_duration:.2f}s total duration @ {sr} Hz.")

    if not full_song and total_duration < window_duration:
        raise ValueError(f"Audio duration ({total_duration:.2f}s) is shorter than target window ({window_duration}s).")

    hop_length = 512
    if full_song:
        window_duration = math.floor(total_duration * 1000) / 1000
        if window_duration <= 0:
            raise ValueError("The selected audio duration is too short for a full-song timeline.")
        hook_start_s = 0.0
        print(f"[INFO] Full-song mode: using the complete {total_duration:.3f}s track.")
    else:
        print(f"[INFO] Computing RMS energy curve across {window_duration}s window...")
        frame_length = 2048
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
    return tuple(
        (1, int(text)) if text.isdigit() else (0, text.casefold())
        for text in re.split(r"(\d+)", str(s))
    )


def run_step_1_shot_renamer(
    renders_dir: str,
    slug: str,
    dry_run: bool = False,
    rename_map_callback=None,
    selected_files: Sequence[str | Path] | None = None,
) -> list:
    """Renames render clips into a safe, zero-collision shot sequence."""
    dry_run = dry_run or is_dry_run()
    print(f"\n[RUN] Step 1: Auditing and standardizing render clips in '{renders_dir}'...")
    r_path = Path(renders_dir).resolve()
    video_files = _validate_selected_render_files(
        r_path, selected_files, VIDEO_EXTENSIONS
    )
    print(f"[INFO] Selected {len(video_files)} shot clip(s); other files will be left untouched.")

    rename_map = _build_rename_map(r_path, video_files)
    target_files = [r_path / item["new"] for item in rename_map]
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

    print(f"[SUCCESS] Confirmed {len(renamed_files)} sequential shot clips.")
    return renamed_files


# ==============================================================================
# PIPELINE STEP 2: SUB-SECOND 24-BIT PCM STEREO WAV TRIMMER (SOUNDFILE)
# ==============================================================================


def run_step_2_audio_trimmer(
    audio_path: str,
    slug: str,
    dry_run: bool = False,
    output_dir: str | Path | None = None,
) -> Path:
    """Trims master audio exactly to the configured hook window using SoundFile."""
    dry_run = dry_run or is_dry_run()
    print(f"\n[RUN] Step 2: Extracting 24-bit PCM master audio slice using SoundFile backend...")
    output_dir = _resolve_output_dir(output_dir)
    hook_file = output_dir / f"{slug}_hooktimestamp.txt"

    if not hook_file.exists():
        raise FileNotFoundError(f"Hook timestamps not found at {hook_file}. Execute Step 0 first.")

    lines = [line.strip() for line in hook_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    hook_start_s = float(lines[0])
    duration_s = float(lines[2]) if len(lines) > 2 else 40.0

    print(f"[INFO] Trimming audio: start = {hook_start_s:.3f}s, duration = {duration_s:.3f}s")
    target_wav = output_dir / f"{slug}{MASTER_AUDIO_SUFFIX}"
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


def run_step_3_sync_metadata(
    slug: str, output_dir: str | Path | None = None
) -> dict:
    """Validates output assets and reads cached beat transient timestamps."""
    print(f"\n[RUN] Step 3: Verifying pipeline state and metadata for '{slug}'...")
    output_dir = _resolve_output_dir(output_dir)
    hook_file = output_dir / f"{slug}_hooktimestamp.txt"
    beats_file = output_dir / f"{slug}_thebeats.txt"
    audio_wav = output_dir / f"{slug}{MASTER_AUDIO_SUFFIX}"

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
    output_dir: str | Path | None = None,
    selected_files: Sequence[str | Path] | None = None,
    full_song_video: bool = False,
) -> Path:
    """Generates a valid FCP7-compatible XML timeline using real media metadata."""
    dry_run = dry_run or is_dry_run()
    print(f"\n[RUN] Step 4: Assembling Apple FCP 7 XML timeline for '{slug}'...")
    total_duration = _validate_duration(total_duration)

    output_dir = _resolve_output_dir(output_dir)
    audio_wav = output_dir / f"{slug}{MASTER_AUDIO_SUFFIX}"
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
    video_files = _validate_selected_render_files(
        r_path, selected_files, SUPPORTED_RENDER_EXTENSIONS
    )

    video_metadata = [probe_media(video_file) for video_file in video_files]
    for video_file, metadata in zip(video_files, video_metadata):
        if not metadata["has_video"]:
            raise ValueError(f"Render does not contain a video stream: {video_file.name}")
        is_still = video_file.suffix.lower() in IMAGE_EXTENSIONS
        if metadata["duration"] <= 0 and not is_still:
            raise ValueError(f"ffprobe did not report the video duration: {video_file.name}")
        if is_still:
            metadata["fps"] = str(fps)
            metadata["duration"] = 0.01

    if full_song_video:
        frame_alloc = _full_song_video_frame_distribution(
            total_duration, fps, video_metadata
        )
    else:
        frame_alloc = _frame_distribution_by_duration(
            video_files, total_duration, fps, video_metadata
        )
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

    clip_index = 0
    for idx, (v_file, video_meta) in enumerate(zip(video_files, video_metadata)):
        clip_dur = frame_alloc[idx]
        if clip_dur <= 0:
            print(f"[INFO] Skipping {v_file.name}; the full-song timeline already ends.")
            continue
        clip_index += 1
        start_frame = current_frame
        end_frame = current_frame + clip_dur
        current_frame = end_frame

        is_still = v_file.suffix.lower() in IMAGE_EXTENSIONS
        source_fps, source_ntsc, actual_source_fps = _fcpxml_rate(
            fps if is_still else video_meta["fps"]
        )
        source_duration = clip_dur / fps if is_still else video_meta["duration"]
        source_frames = max(1, int(round(source_duration * actual_source_fps)))
        source_clip_frames = max(1, int(round((clip_dur / fps) * actual_source_fps)))
        file_url = _file_path_url(v_file)
        video_clip_id = f"video-{clip_index}"
        file_id = f"file-shot-{clip_index}"

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
        _append_clip_link(clip_item, video_clip_id, "video", 1, clip_index)
        print(
            f"[INFO] {v_file.name}: {video_meta['width']}x{video_meta['height']} "
            f"@ {video_meta['fps']} fps; embedded audio: "
            f"{'muted' if video_meta['has_audio'] else 'none'}."
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
    ET.SubElement(audio_clip_item, "name").text = audio_wav.name
    ET.SubElement(audio_clip_item, "enabled").text = "TRUE"
    ET.SubElement(audio_clip_item, "duration").text = str(total_frames)
    _append_rate(audio_clip_item, fps)
    ET.SubElement(audio_clip_item, "in").text = "0"
    ET.SubElement(audio_clip_item, "out").text = str(total_frames)
    ET.SubElement(audio_clip_item, "start").text = "0"
    ET.SubElement(audio_clip_item, "end").text = str(total_frames)

    audio_file_node = ET.SubElement(audio_clip_item, "file", {"id": "file-master-audio"})
    ET.SubElement(audio_file_node, "name").text = audio_wav.name
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
    output_dir: str | Path | None = None,
    include_patterns: Sequence[str] | None = None,
    exclude_patterns: Sequence[str] | None = None,
    image_only: bool = False,
    full_song: bool = False,
    subtitle_path: str | Path | None = None,
) -> None:
    """Validate and print a pipeline plan without changing source or output files."""
    audio_file = Path(audio_path).resolve()
    render_root = Path(renders_dir).resolve()
    _validate_audio_analysis_size(audio_file)
    _validate_bpm(target_bpm)
    duration = _validate_duration(duration)
    extensions = IMAGE_EXTENSIONS if image_only else VIDEO_EXTENSIONS
    video_files = select_render_files(
        render_root, include_patterns, exclude_patterns, extensions
    )
    rename_map = [] if image_only else _build_rename_map(render_root, video_files)

    audio_metadata = probe_media(audio_file)
    if not audio_metadata["has_audio"]:
        raise ValueError(f"No audio stream found in master audio: {audio_file}")
    if full_song:
        duration = _validate_duration(audio_metadata["duration"])
        duration = math.floor(duration * 1000) / 1000
    media_metadata = [probe_media(video_file) for video_file in video_files]
    if full_song and not image_only:
        for video_file, metadata in zip(video_files, media_metadata):
            if not metadata["has_video"] or metadata.get("duration", 0) <= 0:
                raise ValueError(
                    f"Full-song video mode requires valid video footage: {video_file.name}"
                )
        _full_song_video_frame_distribution(duration, 24, media_metadata)
    if subtitle_path:
        subtitle_file = Path(subtitle_path).expanduser().resolve()
        if not subtitle_file.is_file() or subtitle_file.suffix.lower() != ".srt":
            raise ValueError(f"Subtitle file must be an existing .srt file: {subtitle_file}")
        _render_srt_sidecar(subtitle_file, 0.0, audio_metadata["duration"])

    output_dir = _resolve_output_dir(output_dir)
    pipeline_mode = (
        "image-only full-song" if full_song and image_only
        else "full-song video" if full_song
        else "image-only hook" if image_only
        else "standard hook video"
    )
    print(f"[DRY-RUN] Mode: {pipeline_mode}.")
    print(f"[DRY-RUN] Track: {slug}; target BPM: {target_bpm:g}; duration: {duration:g}s.")
    print(f"[DRY-RUN] Master audio: {audio_file.name}.")
    print(f"[DRY-RUN] Found {len(video_files)} source media file(s):")
    for index, (video_file, metadata) in enumerate(
        zip(video_files, media_metadata), start=1
    ):
        if not metadata["has_video"]:
            raise ValueError(f"Render does not contain a video stream: {video_file.name}")
        is_still = video_file.suffix.lower() in IMAGE_EXTENSIONS
        if not is_still and metadata.get("duration", 0) <= 0:
            raise ValueError(f"ffprobe did not report the video duration: {video_file.name}")
        target_name = (
            video_file.name if image_only else rename_map[index - 1]["new"]
        )
        print(
            f"[DRY-RUN] {'Use still' if is_still else 'Use video'} {target_name}; "
            f"{metadata['width']}x{metadata['height']}; "
            f"embedded audio: {'muted' if metadata['has_audio'] else 'none'}."
        )
    for suffix in RollbackStore.OUTPUT_SUFFIXES:
        if suffix == SUBTITLE_SUFFIX and not subtitle_path:
            continue
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
    output_dir: str | Path | None = None,
    include_patterns: Sequence[str] | None = None,
    exclude_patterns: Sequence[str] | None = None,
    image_only: bool = False,
    full_song: bool = False,
    subtitle_path: str | Path | None = None,
) -> Path | None:
    output_path = _resolve_output_dir(output_dir)
    dry_run = dry_run or is_dry_run()
    if full_song:
        _validate_audio_analysis_size(Path(audio_path).expanduser().resolve())
        audio_metadata = probe_media(audio_path)
        if not audio_metadata["has_audio"]:
            raise ValueError(f"No audio stream found in master audio: {audio_path}")
        duration = _validate_duration(audio_metadata["duration"])

    extensions = IMAGE_EXTENSIONS if image_only else VIDEO_EXTENSIONS
    if dry_run:
        dry_run_pipeline(
            audio_path,
            renders_path,
            slug,
            bpm,
            duration,
            output_path,
            include_patterns,
            exclude_patterns,
            image_only,
            full_song,
            subtitle_path,
        )
        return None

    selected_files = select_render_files(
        renders_path, include_patterns, exclude_patterns, extensions
    )
    if full_song and not image_only:
        video_metadata = [probe_media(video_file) for video_file in selected_files]
        for video_file, metadata in zip(selected_files, video_metadata):
            if not metadata["has_video"] or metadata.get("duration", 0) <= 0:
                raise ValueError(
                    f"Full-song video mode requires valid video footage: {video_file.name}"
                )
        _full_song_video_frame_distribution(duration, 24, video_metadata)
    if not image_only:
        _build_rename_map(renders_path, selected_files)
    store = RollbackStore()
    run_id = store.begin_run(slug, audio_path, renders_path, output_path)
    print(f"[INFO] Generated files will be saved in: {output_path}")
    print(f"[INFO] Recovery manifest created: rollback/{run_id}/manifest.json")
    try:
        print(f"\nSTARTING HMS MASTER PIPELINE: {slug.upper()} ({run_id})")
        analysis_result = run_step_0_audio_analysis(
            audio_path,
            slug,
            target_bpm=bpm,
            window_duration=duration,
            output_dir=output_path,
            full_song=full_song,
        )
        if full_song and analysis_result:
            duration = analysis_result["duration"]
        if subtitle_path:
            hook_start = 0.0
            if not full_song:
                hook_file = output_path / f"{slug}_hooktimestamp.txt"
                hook_start = float(
                    hook_file.read_text(encoding="utf-8").splitlines()[0]
                )
            write_srt_sidecar(
                subtitle_path,
                output_path / f"{slug}_subtitles.srt",
                hook_start,
                duration,
            )
        if image_only:
            timeline_files = selected_files
        else:
            timeline_files = run_step_1_shot_renamer(
                renders_path,
                slug,
                rename_map_callback=lambda mapping, state: store.set_rename_map(
                    run_id, mapping, state
                ),
                selected_files=selected_files,
            )
        run_step_2_audio_trimmer(audio_path, slug, output_dir=output_path)
        run_step_3_sync_metadata(slug, output_path)
        xml_path = run_step_4_generate_davinci_xml(
            slug,
            renders_path,
            fps=24,
            total_duration=duration,
            output_dir=output_path,
            selected_files=timeline_files,
            full_song_video=full_song and not image_only,
        )
        beats_file = output_path / f"{slug}_thebeats.txt"
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


def verify_pipeline_outputs(
    slug: str,
    renders_dir: str | None = None,
    duration: float = 40.0,
    output_dir: str | Path | None = None,
    image_only: bool = False,
    include_subtitles: bool = False,
) -> bool:
    """Check generated files and validate the existing XML without modifying them."""
    duration = _validate_duration(duration)
    output_dir = _resolve_output_dir(output_dir)
    master_wav = output_dir / f"{slug}{MASTER_AUDIO_SUFFIX}"
    if not master_wav.is_file():
        legacy_master_wav = output_dir / f"{slug}{LEGACY_MASTER_AUDIO_SUFFIX}"
        if legacy_master_wav.is_file():
            master_wav = legacy_master_wav
    required = [
        output_dir / f"{slug}_hooktimestamp.txt",
        output_dir / f"{slug}_thebeats.txt",
        master_wav,
        output_dir / f"{slug}_davinci_timeline.xml",
    ]
    subtitle_file = output_dir / f"{slug}_subtitles.srt"
    if include_subtitles:
        required.append(subtitle_file)
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
        expected_extensions = IMAGE_EXTENSIONS if image_only else VIDEO_EXTENSIONS
        if not any(
            path.is_file()
            and path.suffix.lower() in expected_extensions
            and (image_only or path.name.casefold().startswith("shot"))
            for path in renders_path.iterdir()
        ):
            media_type = "image" if image_only else "sequenced shot clips"
            raise FileNotFoundError(f"No {media_type} media found in {renders_path}")

    from hms_v31_patcher import verify_davinci_xml

    xml_path = output_dir / f"{slug}_davinci_timeline.xml"
    if not verify_davinci_xml(str(xml_path)):
        raise RuntimeError(f"Timeline verification failed: {xml_path}")
    if include_subtitles and not subtitle_file.is_file():
        raise FileNotFoundError(f"Missing generated subtitle sidecar: {subtitle_file}")
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
    def __init__(
        self, dry_run: bool = False, output_dir: str | Path | None = None
    ):
        super().__init__()
        self.initial_dry_run = dry_run
        self.initial_output_dir = _resolve_output_dir(output_dir)
        self._audio_selection_generation = 0
        self._bpm_estimation_pending = False
        self._pipeline_running = False
        self.title("HMS v3.16 EXPERIMENTAL - 337 West Productions")
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

        print("[WARNING] HMS v3.16 EXPERIMENTAL TEST BUILD - test only; not production-ready.")
        print("[INFO] Environment: 24.0 fps | 1080p | 40.000s timeline standard.")

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TLabel", background=self.bg_color, foreground=self.fg_color, font=("Consolas", 10))
        style.configure("TButton", font=("Consolas", 10, "bold"), padding=4)
        style.configure("Header.TLabel", font=("Consolas", 12, "bold"), foreground=self.accent_color)

    def _create_widgets(self):
        header = ttk.Label(self, text="HMS v3.16 EXPERIMENTAL :: TESTING ONLY", style="Header.TLabel")
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

        tk.Label(param_frame, text="Output Dir:", bg=self.bg_color, fg=self.fg_color, font=("Consolas", 9)).grid(row=2, column=0, sticky="w", padx=8, pady=4)
        self.output_var = tk.StringVar(value=str(self.initial_output_dir))
        self.output_entry = tk.Entry(param_frame, textvariable=self.output_var, width=65, bg=self.panel_color, fg=self.fg_color, insertbackground=self.fg_color)
        self.output_entry.grid(row=2, column=1, padx=4, pady=4)
        tk.Button(param_frame, text="Browse Folder", command=self._browse_output, bg=self.btn_bg, fg=self.fg_color).grid(row=2, column=2, padx=6, pady=4)

        tk.Label(
            param_frame,
            text="Include Clips:",
            bg=self.bg_color,
            fg=self.fg_color,
            font=("Consolas", 9),
        ).grid(row=3, column=0, sticky="w", padx=8, pady=4)
        self.include_var = tk.StringVar(value="")
        tk.Entry(
            param_frame,
            textvariable=self.include_var,
            width=65,
            bg=self.panel_color,
            fg=self.fg_color,
            insertbackground=self.fg_color,
        ).grid(row=3, column=1, padx=4, pady=4)
        tk.Button(
            param_frame,
            text="Choose Files",
            bg=self.btn_bg,
            fg=self.fg_color,
            command=self._choose_render_clips,
        ).grid(row=3, column=2, sticky="w", padx=6, pady=4)

        tk.Label(
            param_frame,
            text="Exclude Clips:",
            bg=self.bg_color,
            fg=self.fg_color,
            font=("Consolas", 9),
        ).grid(row=4, column=0, sticky="w", padx=8, pady=4)
        self.exclude_var = tk.StringVar(value="")
        tk.Entry(
            param_frame,
            textvariable=self.exclude_var,
            width=65,
            bg=self.panel_color,
            fg=self.fg_color,
            insertbackground=self.fg_color,
        ).grid(row=4, column=1, padx=4, pady=4)
        tk.Label(
            param_frame,
            text="Optional; excluded files are never renamed",
            bg=self.bg_color,
            fg="#aaaaaa",
            font=("Consolas", 8),
        ).grid(row=4, column=2, sticky="w", padx=6, pady=4)

        workflow_frame = tk.Frame(param_frame, bg=self.bg_color)
        workflow_frame.grid(row=5, column=0, columnspan=3, sticky="w", padx=8, pady=4)
        tk.Label(
            workflow_frame, text="Workflow:", bg=self.bg_color, fg=self.fg_color,
            font=("Consolas", 9),
        ).pack(side="left")
        self.media_mode_var = tk.StringVar(value="Standard Hook Video")
        tk.OptionMenu(
            workflow_frame,
            self.media_mode_var,
            "Standard Hook Video",
            "Image-only Lyric Video",
        ).pack(side="left", padx=(4, 12))
        tk.Label(
            workflow_frame, text="Timeline duration:", bg=self.bg_color, fg=self.fg_color,
            font=("Consolas", 9),
        ).pack(side="left")
        self.image_duration_var = tk.StringVar(value="Hook")
        tk.OptionMenu(
            workflow_frame,
            self.image_duration_var,
            "Hook",
            "Full song",
        ).pack(side="left", padx=(4, 12))
        self.subtitles_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            workflow_frame,
            text="Include SRT subtitles",
            variable=self.subtitles_var,
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.panel_color,
        ).pack(side="left")
        tk.Button(
            workflow_frame,
            text="Choose SRT",
            command=self._browse_subtitles,
            bg=self.btn_bg,
            fg=self.fg_color,
        ).pack(side="left", padx=6)
        self.subtitle_var = tk.StringVar(value="")

        meta_subframe = tk.Frame(param_frame, bg=self.bg_color)
        meta_subframe.grid(row=6, column=0, columnspan=3, sticky="w", padx=8, pady=6)

        tk.Label(meta_subframe, text="Track Slug:", bg=self.bg_color, fg=self.fg_color, font=("Consolas", 9)).pack(side="left")
        self.slug_var = tk.StringVar(value="paper_dolls")
        tk.Entry(meta_subframe, textvariable=self.slug_var, width=18, bg=self.panel_color, fg=self.fg_color).pack(side="left", padx=(4, 16))

        tk.Label(meta_subframe, text="Target BPM:", bg=self.bg_color, fg=self.fg_color, font=("Consolas", 9)).pack(side="left")
        self.bpm_var = tk.StringVar(value="170.0")
        self.bpm_entry = tk.Entry(
            meta_subframe,
            textvariable=self.bpm_var,
            width=8,
            bg=self.panel_color,
            fg=self.fg_color,
        )
        self.bpm_entry.pack(side="left", padx=(4, 16))

        tk.Label(meta_subframe, text="Duration (s):", bg=self.bg_color, fg=self.fg_color, font=("Consolas", 9)).pack(side="left")
        self.duration_var = tk.StringVar(value="40.0")
        tk.Entry(meta_subframe, textvariable=self.duration_var, width=8, bg=self.panel_color, fg=self.fg_color).pack(side="left", padx=(4, 16))

        ctrl_frame = tk.LabelFrame(self, text=" Pipeline Execution ", bg=self.bg_color, fg=self.accent_color, font=("Consolas", 10, "bold"))
        ctrl_frame.pack(fill="x", padx=15, pady=6)

        self.run_all_btn = tk.Button(ctrl_frame, text="RUN COMPLETE PIPELINE (Steps 0 -> 4)", bg=self.accent_color, fg="white", font=("Consolas", 11, "bold"), command=self._start_complete_pipeline)
        self.run_all_btn.pack(fill="x", padx=8, pady=6)

        step_row = tk.Frame(ctrl_frame, bg=self.bg_color)
        step_row.pack(fill="x", padx=8, pady=(0, 6))

        self.step_0_btn = tk.Button(
            step_row,
            text="Step 0 (RMS/Beats)",
            bg=self.btn_bg,
            fg=self.fg_color,
            command=lambda: self._run_step_async(0),
        )
        self.step_0_btn.pack(side="left", expand=True, fill="x", padx=2)
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
            derived_slug = derive_slug_from_audio(file_path)
            self.slug_var.set(derived_slug)
            print(f"[INFO] Audio source selected: {Path(file_path).name} (Derived slug: '{derived_slug}')")
            self._audio_selection_generation += 1
            generation = self._audio_selection_generation
            self._bpm_estimation_pending = True
            self.bpm_var.set(f"{DEFAULT_TARGET_BPM:.1f}")
            self.bpm_entry.configure(state="disabled")
            self._refresh_bpm_dependent_controls()
            print("[INFO] Estimating BPM for the newly selected audio...")
            threading.Thread(
                target=self._estimate_bpm_worker,
                args=(file_path, generation),
                daemon=True,
            ).start()

    def _browse_subtitles(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select timed subtitle file",
            filetypes=[("SubRip subtitles", "*.srt"), ("All Files", "*.*")],
        )
        if file_path:
            self.subtitle_var.set(file_path)
            self.subtitles_var.set(True)
            print(f"[INFO] SRT subtitles selected: {Path(file_path).name}")

    def _estimate_bpm_worker(self, audio_path: str, generation: int) -> None:
        try:
            tempo = estimate_audio_bpm(audio_path)
            error_message = None
        except Exception as error:
            tempo = DEFAULT_TARGET_BPM
            error_message = str(error)
        try:
            self.after(
                0,
                self._apply_bpm_estimate,
                audio_path,
                generation,
                tempo,
                error_message,
            )
        except tk.TclError:
            return

    def _apply_bpm_estimate(
        self,
        audio_path: str,
        generation: int,
        tempo: float,
        error_message: str | None,
    ) -> None:
        if generation != self._audio_selection_generation:
            return
        if Path(self.audio_var.get()).expanduser().resolve() != Path(audio_path).expanduser().resolve():
            return
        self.bpm_var.set(f"{tempo:.2f}")
        self.bpm_entry.configure(state="normal")
        self._bpm_estimation_pending = False
        self._refresh_bpm_dependent_controls()
        if error_message:
            print(
                f"[WARN] BPM estimation failed for {Path(audio_path).name}: "
                f"{error_message}. Using default {DEFAULT_TARGET_BPM:.1f} BPM; "
                "please verify or edit the Target BPM."
            )
        else:
            print(f"[SUCCESS] Estimated Target BPM for this audio: {tempo:.2f}.")

    def _refresh_bpm_dependent_controls(self) -> None:
        estimating = self.__dict__.get("_bpm_estimation_pending", False)
        running = self.__dict__.get("_pipeline_running", False)
        run_all_btn = self.__dict__.get("run_all_btn")
        step_0_btn = self.__dict__.get("step_0_btn")
        if run_all_btn is not None:
            run_all_btn.config(
                state="disabled" if estimating or running else "normal"
            )
        if step_0_btn is not None:
            step_0_btn.config(state="disabled" if estimating else "normal")

    def _browse_renders(self):
        folder_path = filedialog.askdirectory(
            initialdir=self.renders_var.get() or str(Path.cwd())
        )
        if folder_path:
            render_root = Path(folder_path).expanduser().resolve()
            self.renders_var.set(str(render_root))
            self.include_var.set("")
            print(f"[INFO] Renders directory selected: {render_root}")
            self._choose_render_clips(render_root)

    def _choose_render_clips(self, renders_dir: str | Path | None = None) -> None:
        render_root = Path(
            renders_dir or self.renders_var.get().strip()
        ).expanduser().resolve()
        if not render_root.is_dir():
            print(f"[ERROR] Renders folder does not exist: {render_root}")
            return
        mode_var = self.__dict__.get("media_mode_var")
        image_mode = mode_var is not None and mode_var.get() == "Image-only Lyric Video"
        selected_paths = filedialog.askopenfilenames(
            title="Select still images to include" if image_mode else "Select video clips to include",
            initialdir=str(render_root),
            filetypes=[
                ("Still images", "*.jpg *.jpeg *.png")
                if image_mode
                else ("Video clips", "*.mp4 *.mov *.mkv"),
                ("All files", "*.*"),
            ],
        )
        if not selected_paths:
            return

        selected_files = [Path(path).expanduser().resolve() for path in selected_paths]
        invalid_files = [
            path
            for path in selected_files
            if path.parent != render_root
            or path.suffix.lower()
            not in (IMAGE_EXTENSIONS if image_mode else VIDEO_EXTENSIONS)
            or not path.is_file()
        ]
        if invalid_files:
            print(
                "[ERROR] Select only supported media files directly inside the chosen renders folder: "
                + ", ".join(str(path) for path in invalid_files)
            )
            return

        self.include_var.set(", ".join(path.name for path in selected_files))
        print(
            f"[INFO] Selected {len(selected_files)} render file(s) for inclusion: "
            + ", ".join(path.name for path in selected_files)
        )

    def _browse_output(self):
        folder_path = filedialog.askdirectory(
            initialdir=self.output_var.get() or str(Path.cwd())
        )
        if folder_path:
            self.output_var.set(folder_path)
            print(f"[INFO] Output directory selected: {folder_path}")

    def _start_complete_pipeline(self):
        if self.__dict__.get("_bpm_estimation_pending", False):
            print("[WARN] Wait for BPM estimation to finish before starting the pipeline.")
            return
        self._pipeline_running = True
        self._refresh_bpm_dependent_controls()
        dry_run = self.dry_run_var.get()
        output_dir = self.output_var.get().strip()
        include_patterns = parse_file_patterns(self.include_var.get())
        exclude_patterns = parse_file_patterns(self.exclude_var.get())
        threading.Thread(
            target=self._execute_pipeline_worker,
            args=(dry_run, output_dir, include_patterns, exclude_patterns),
            daemon=True,
        ).start()

    def _execute_pipeline_worker(
        self,
        dry_run: bool = False,
        output_dir: str | None = None,
        include_patterns: Sequence[str] | None = None,
        exclude_patterns: Sequence[str] | None = None,
    ):
        set_dry_run(dry_run)
        try:
            if self.__dict__.get("_bpm_estimation_pending", False):
                print("[WARN] Pipeline cancelled because BPM estimation is still in progress.")
                return
            audio_path = self.audio_var.get().strip()
            renders_path = self.renders_var.get().strip()
            slug = self.slug_var.get().strip()
            bpm = _validate_bpm(self.bpm_var.get().strip())
            duration = _validate_duration(self.duration_var.get().strip())

            if not audio_path:
                print("[ERROR] Please select a master audio file.")
                return

            media_mode_var = self.__dict__.get("media_mode_var")
            image_only = (
                media_mode_var is not None
                and media_mode_var.get() == "Image-only Lyric Video"
            )
            duration_mode_var = self.__dict__.get("image_duration_var")
            full_song = (
                duration_mode_var is not None
                and duration_mode_var.get() == "Full song"
            )
            subtitles_var = self.__dict__.get("subtitles_var")
            subtitle_var = self.__dict__.get("subtitle_var")
            subtitle_path = None
            if subtitles_var is not None and subtitles_var.get():
                if subtitle_var is None or not subtitle_var.get().strip():
                    raise ValueError(
                        "Choose an SRT subtitle file or turn off Include SRT subtitles."
                    )
                subtitle_path = subtitle_var.get().strip()

            xml_path = execute_pipeline(
                audio_path,
                renders_path,
                slug,
                bpm,
                duration,
                dry_run=dry_run,
                output_dir=output_dir,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                image_only=image_only,
                full_song=full_song,
                subtitle_path=subtitle_path,
            )
            if xml_path:
                print("Ready for DaVinci Resolve import (Ctrl + Shift + I).")
                if subtitle_path:
                    print(
                        "Import the generated _subtitles.srt as a separate subtitle "
                        "track in Resolve; subtitles are not embedded in FCP 7 XML."
                    )

        except Exception as e:
            print(f"[ERROR] Pipeline failed: {str(e)}")
            print(traceback.format_exc())
        finally:
            self.run_all_btn.after(0, self._complete_pipeline_ui)

    def _complete_pipeline_ui(self) -> None:
        self._pipeline_running = False
        self._refresh_bpm_dependent_controls()

    def _run_step_async(self, step_idx):
        if step_idx == 0 and self.__dict__.get("_bpm_estimation_pending", False):
            print("[WARN] Wait for BPM estimation to finish before running Step 0.")
            return
        dry_run = self.dry_run_var.get()
        output_dir = self.output_var.get().strip()
        include_patterns = parse_file_patterns(self.include_var.get())
        exclude_patterns = parse_file_patterns(self.exclude_var.get())
        threading.Thread(
            target=self._step_worker,
            args=(step_idx, dry_run, output_dir, include_patterns, exclude_patterns),
            daemon=True,
        ).start()

    def _step_worker(
        self,
        step_idx,
        dry_run: bool = False,
        output_dir: str | None = None,
        include_patterns: Sequence[str] | None = None,
        exclude_patterns: Sequence[str] | None = None,
    ):
        if step_idx == 0 and self.__dict__.get("_bpm_estimation_pending", False):
            print("[WARN] Step 0 cancelled because BPM estimation is still in progress.")
            return
        set_dry_run(dry_run)
        try:
            audio_path = self.audio_var.get().strip()
            renders_path = self.renders_var.get().strip()
            slug = self.slug_var.get().strip()
            bpm = _validate_bpm(self.bpm_var.get().strip())
            duration = _validate_duration(self.duration_var.get().strip())
            mode_var = self.__dict__.get("media_mode_var")
            image_only = (
                mode_var is not None
                and mode_var.get() == "Image-only Lyric Video"
            )
            duration_mode_var = self.__dict__.get("image_duration_var")
            full_song = (
                duration_mode_var is not None
                and duration_mode_var.get() == "Full song"
            )
            if step_idx == 0:
                if full_song:
                    duration = _validate_duration(probe_media(audio_path)["duration"])
                run_step_0_audio_analysis(
                    audio_path,
                    slug,
                    target_bpm=bpm,
                    window_duration=duration,
                    dry_run=dry_run,
                    output_dir=output_dir,
                    full_song=full_song,
                )
            elif step_idx == 1:
                if image_only:
                    raise ValueError(
                        "Image-only mode preserves source image filenames; use the complete pipeline."
                    )
                selected_files = select_render_files(
                    renders_path, include_patterns, exclude_patterns
                )
                run_step_1_shot_renamer(
                    renders_path,
                    slug,
                    dry_run=dry_run,
                    selected_files=selected_files,
                )
            elif step_idx == 2:
                run_step_2_audio_trimmer(audio_path, slug, dry_run=dry_run, output_dir=output_dir)
            elif step_idx == 3:
                run_step_3_sync_metadata(slug, output_dir)
            elif step_idx == 4:
                extensions = IMAGE_EXTENSIONS if image_only else VIDEO_EXTENSIONS
                selected_files = select_render_files(
                    renders_path, include_patterns, exclude_patterns, extensions
                )
                if full_song:
                    hook_file = _resolve_output_dir(output_dir) / f"{slug}_hooktimestamp.txt"
                    duration = _validate_duration(
                        float(hook_file.read_text(encoding="utf-8").splitlines()[2])
                    )
                run_step_4_generate_davinci_xml(
                    slug,
                    renders_path,
                    fps=24,
                    total_duration=duration,
                    dry_run=dry_run,
                    output_dir=output_dir,
                    selected_files=selected_files,
                    full_song_video=full_song and not image_only,
                )
        except Exception as e:
            print(f"[ERROR] Step {step_idx} execution error: {str(e)}")
            print(traceback.format_exc())

    def _verify_only_async(self):
        mode_var = self.__dict__.get("media_mode_var")
        image_only = mode_var is not None and mode_var.get() == "Image-only Lyric Video"
        subtitles_var = self.__dict__.get("subtitles_var")
        include_subtitles = subtitles_var is not None and subtitles_var.get()
        threading.Thread(
            target=self._verify_only_worker,
            args=(
                self.slug_var.get().strip(),
                self.renders_var.get().strip(),
                self.duration_var.get().strip(),
                self.output_var.get().strip(),
                image_only,
                include_subtitles,
            ),
            daemon=True,
        ).start()

    def _verify_only_worker(
        self,
        slug: str,
        renders_dir: str,
        duration: str,
        output_dir: str,
        image_only: bool = False,
        include_subtitles: bool = False,
    ):
        try:
            verify_pipeline_outputs(
                slug,
                renders_dir,
                float(duration),
                output_dir,
                image_only,
                include_subtitles,
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


def main():
    arguments = cli_bootstrap()
    app = HMSMasterGUI(
        dry_run=arguments.dry_run,
        output_dir=arguments.output_dir,
    )
    app.mainloop()


if __name__ == "__main__":
    main()
