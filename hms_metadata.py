"""Strict ffprobe-based media metadata utilities for HMS."""

import json
import subprocess
from fractions import Fraction
from pathlib import Path


def probe_media(path: str | Path) -> dict:
    """Return validated stream metadata, raising errors for invalid media."""
    media_path = Path(path)
    if not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")

    command = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(media_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)

    def as_float(value, default):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def as_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    duration = as_float(data.get("format", {}).get("duration"), 0.0)
    if duration <= 0 and video:
        duration = as_float(video.get("duration"), 0.0)
    if duration <= 0 and audio:
        duration = as_float(audio.get("duration"), 0.0)

    width = as_int(video.get("width"), 0) if video else 0
    height = as_int(video.get("height"), 0) if video else 0
    video_fps = None
    if video:
        if width <= 0 or height <= 0:
            raise ValueError(f"ffprobe did not report valid video dimensions for {media_path}.")
        for candidate in (video.get("avg_frame_rate"), video.get("r_frame_rate")):
            if not candidate:
                continue
            try:
                if Fraction(str(candidate)) > 0:
                    video_fps = str(candidate)
                    break
            except (ValueError, ZeroDivisionError):
                continue
        if video_fps is None:
            raise ValueError(f"ffprobe did not report a valid video frame rate for {media_path}.")

    return {
        "width": width,
        "height": height,
        "fps": video_fps,
        "has_video": video is not None,
        "has_audio": audio is not None,
        "samplerate": as_int(audio.get("sample_rate"), 44100) if audio else 44100,
        "sample_rate": as_int(audio.get("sample_rate"), 44100) if audio else 44100,
        "channels": as_int(audio.get("channels"), 2) if audio else 2,
        "depth": as_int(
            (audio or {}).get("bits_per_raw_sample")
            or (audio or {}).get("bits_per_sample"),
            24,
        ),
        "duration": duration if duration > 0 else 0.0,
        "audio_duration": (
            as_float(audio.get("duration"), duration) if audio else 0.0
        ),
    }


def safe_probe(path: str | Path) -> dict:
    """Log probe errors and return an empty, consistently shaped metadata record."""
    try:
        return probe_media(path)
    except Exception as error:
        print(f"[WARN] Probe failed for {path}: {error}")
        return {
            "width": 0,
            "height": 0,
            "fps": None,
            "has_video": False,
            "has_audio": False,
            "samplerate": 44100,
            "sample_rate": 44100,
            "channels": 2,
            "depth": 24,
            "duration": 0.0,
            "audio_duration": 0.0,
        }
