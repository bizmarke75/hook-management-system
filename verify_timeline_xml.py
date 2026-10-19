"""
337 West Productions - Hook Management System (HMS) v3.0.0
Module: verify_timeline_xml.py
Purpose: Headless audit tool for DaVinci Resolve Free FCP 7 XML (xmeml v5) timelines.
Standard: modular-python-builder
"""

import sys
import os
import urllib.parse
from pathlib import Path
import xml.etree.ElementTree as ET


def verify_davinci_xml(xml_path_str: str) -> bool:
    """
    Audits timeline XML schema, gapless video continuity, audio integrity,
    and transient marker frame boundaries for 24fps / 960 frame conformance.
    """
    xml_path = Path(xml_path_str).resolve()
    print(f"[RUN] Auditing timeline XML: {xml_path}")

    if not xml_path.exists():
        print(f"[ERROR] File does not exist on disk: {xml_path}")
        return False

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"[ERROR] XML Parse Error: {str(e)}")
        return False

    # 1. Rate & Sequence Validation
    rate_node = root.find(".//rate/timebase")
    if rate_node is None:
        print("[ERROR] Missing <rate><timebase> node in sequence.")
        return False

    fps = int(rate_node.text.strip())
    if fps != 24:
        print(f"[ERROR] Timebase mismatch: Expected 24 fps, found {fps} fps.")
        return False
    print(f"[INFO] Timebase confirmed: {fps} fps.")

    # 2. Video Track & Gapless Continuity Check
    video_clips = root.findall(".//media/video/track/clipitem")
    if not video_clips:
        print("[ERROR] No video <clipitem> elements found in timeline.")
        return False

    print(f"[INFO] Auditing {len(video_clips)} video clip segments...")
    current_timeline_frame = 0

    for idx, clip in enumerate(video_clips, start=1):
        name = clip.findtext("name", f"shot_{idx}")
        start_txt = clip.findtext("start", "-1").strip()
        end_txt = clip.findtext("end", "-1").strip()

        try:
            start_frame = int(start_txt)
            end_frame = int(end_txt)
        except ValueError:
            print(f"[ERROR] Non-integer start/end frame on video clip '{name}': start='{start_txt}', end='{end_txt}'")
            return False

        if start_frame != current_timeline_frame:
            gap = start_frame - current_timeline_frame
            print(f"[ERROR] Track continuity violation at clip {idx} ('{name}'): Expected start {current_timeline_frame}, found {start_frame} (Gap/Overlap: {gap} frames)")
            return False

        clip_duration = end_frame - start_frame
        if clip_duration <= 0:
            print(f"[ERROR] Invalid clip duration for '{name}': {clip_duration} frames.")
            return False

        # Verify underlying media file path
        pathurl = clip.findtext(".//file/pathurl")
        if pathurl:
            parsed = urllib.parse.urlparse(pathurl)
            file_disk_path = urllib.parse.unquote(parsed.path)
            if os.name == "nt" and file_disk_path.startswith("/"):
                file_disk_path = file_disk_path[1:]
            if not Path(file_disk_path).exists():
                print(f"[WARN] Video asset on disk not found: {file_disk_path}")

        current_timeline_frame = end_frame

    if current_timeline_frame != 960:
        print(f"[ERROR] Total video frame count mismatch: Expected exactly 960 frames (40.0s), got {current_timeline_frame}")
        return False
    print(f"[INFO] Video continuity verified: 0 to 960 frames (gapless).")

    # 3. Audio Track Validation
    audio_clips = root.findall(".//media/audio/track/clipitem")
    if not audio_clips:
        print("[ERROR] No audio <clipitem> elements found in timeline.")
        return False

    audio_clip = audio_clips[0]
    raw_dur = audio_clip.findtext("duration", "-1").strip()

    # Guard against un-interpolated template placeholders
    if raw_dur.startswith("{") and raw_dur.endswith("}"):
        print(f"[ERROR] XML Template Leak Detected: Audio <duration> contains literal placeholder '{raw_dur}' instead of evaluated frame count.")
        return False

    try:
        a_dur = int(raw_dur)
    except ValueError:
        print(f"[ERROR] Invalid integer for audio duration node: '{raw_dur}'")
        return False

    if a_dur != 960:
        print(f"[ERROR] Audio duration mismatch: Expected 960 frames, found {a_dur}")
        return False
    print(f"[INFO] Audio track duration confirmed: {a_dur} frames (40.000s @ 24fps).")

    # Verify audio file reference
    audio_url = audio_clip.findtext(".//file/pathurl")
    if audio_url:
        parsed_audio = urllib.parse.urlparse(audio_url)
        audio_disk_path = urllib.parse.unquote(parsed_audio.path)
        if os.name == "nt" and audio_disk_path.startswith("/"):
            audio_disk_path = audio_disk_path[1:]
        if Path(audio_disk_path).exists():
            file_size_mb = Path(audio_disk_path).stat().st_size / (1024 * 1024)
            print(f"[INFO] Master audio located: {Path(audio_disk_path).name} ({file_size_mb:.2f} MB)")
        else:
            print(f"[WARN] Master audio file referenced but not present at: {audio_disk_path}")

    # 4. Marker Integrity Check
    markers = root.findall(".//marker")
    print(f"[INFO] Auditing {len(markers)} timeline markers...")

    if not markers:
        print("[WARN] No transient beat markers detected in XML.")
    else:
        out_of_bounds = 0
        for marker in markers:
            m_in_txt = marker.findtext("in", "-1").strip()
            try:
                m_in = int(m_in_txt)
            except ValueError:
                print(f"[ERROR] Invalid marker frame value: '{m_in_txt}'")
                return False

            if m_in < 0 or m_in >= 960:
                out_of_bounds += 1

        if out_of_bounds > 0:
            print(f"[ERROR] {out_of_bounds} marker(s) fall outside the 960-frame timeline window.")
            return False

        print(f"[INFO] Marker audit: {len(markers)} transient pins verified within 0 <= frame < 960.")

    print("[SUCCESS] XML timeline verification passed with zero schema or continuity errors.")
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = "output/paper_dolls_davinci_timeline.xml"

    success = verify_davinci_xml(target)
    sys.exit(0 if success else 1)