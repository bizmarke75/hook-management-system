import os
import pathlib
import re

def parse_time_string(val_str):
    """Parses pure floats ('164.281') or timecode strings ('02:44.281' or '02:44:16')."""
    if not val_str:
        return None
    val_str = val_str.strip()
    if not val_str:
        return None
    
    if ':' in val_str:
        parts = val_str.split(':')
        try:
            if len(parts) == 2:
                return float(parts[0]) * 60.0 + float(parts[1])
            elif len(parts) == 3:
                return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
            elif len(parts) == 4: # HH:MM:SS:FF at 24fps
                return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2]) + float(parts[3]) / 24.0
        except ValueError:
            pass
            
    try:
        return float(val_str)
    except ValueError:
        match = re.search(r"[-+]?\d*\.\d+|\d+", val_str)
        if match:
            return float(match.group())
    return None

def win_to_uri(path_str):
    clean = str(path_str).replace('\\', '/')
    if not clean.startswith('/'):
        clean = '/' + clean
    return f"file://localhost{clean}"

def run_track_pipeline(track_slug="dear_me", track_title="Dear Me", fps=24):
    """
    Track-Aware Automation Pipeline for Hook Management System (HMS).
    Dynamically prevents file overwrites by embedding the track_slug in all generated outputs.
    """
    print("=" * 65)
    print(f"🎬 HMS TRACK-AWARE TIMELINE BUILDER — [{track_slug.upper()}]")
    print("=" * 65)

    base_renders_dir = rf"C:\renders\{track_slug}"
    output_meta_dir = r"C:\renders\output"
    audio_dir = r"C:\audio"

    # Track-specific file names
    audio_master_path = os.path.join(audio_dir, f"{track_slug}_master.wav")
    trimmed_audio_path = os.path.join(audio_dir, f"{track_slug}_master_trimmed.wav")
    
    beats_file_track = os.path.join(output_meta_dir, f"{track_slug}_thebeats.txt")
    beats_file_generic = os.path.join(output_meta_dir, "thebeats.txt")

    hook_file_track = os.path.join(output_meta_dir, f"{track_slug}_hooktimestamp.txt")
    hook_file_generic_1 = os.path.join(output_meta_dir, "hooktimestamp.txt")
    hook_file_generic_2 = os.path.join(output_meta_dir, "hooktimestapm.txt")

    output_xml_path = os.path.join(base_renders_dir, f"{track_slug}_hook_timeline.xml")

    # 1. Locate and parse Hook Timestamp
    hook_start_sec = 164.281  # Default for Dear Me hook
    hook_file_used = None

    for candidate in [hook_file_track, hook_file_generic_1, hook_file_generic_2]:
        if os.path.exists(candidate):
            hook_file_used = candidate
            break

    if hook_file_used:
        print(f"📄 Found Hook Timestamp File: {hook_file_used}")
        with open(hook_file_used, "r", encoding="utf-8", errors="ignore") as f:
            parsed = parse_time_string(f.read())
            if parsed is not None:
                hook_start_sec = parsed
                print(f"  └─ Parsed Hook Start: {hook_start_sec:.3f}s")
    else:
        print(f"ℹ️ Hook timestamp file not found. Using default offset: {hook_start_sec:.3f}s")

    # 2. Locate and parse Beats File
    beat_timestamps = []
    beats_file_used = None

    for candidate in [beats_file_track, beats_file_generic]:
        if os.path.exists(candidate):
            beats_file_used = candidate
            break

    if beats_file_used:
        print(f"📄 Found Beats File: {beats_file_used}")
        with open(beats_file_used, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                t = parse_time_string(line)
                if t is not None:
                    beat_timestamps.append(t)
        print(f"  └─ Loaded {len(beat_timestamps)} beat timestamps.")
    else:
        print(f"ℹ️ Beats file not found. Will fallback to 123 BPM grid.")

    # 3. Detect Video Shots (shot1.mp4 ... shot5.mp4)
    shots = [
        {"filename": "shot1.mp4", "duration_sec": 5.7083},
        {"filename": "shot2.mp4", "duration_sec": 8.0000},
        {"filename": "shot3.mp4", "duration_sec": 10.0000},
        {"filename": "shot4.mp4", "duration_sec": 8.0000},
        {"filename": "shot5.mp4", "duration_sec": 8.2917},
    ]

    clips_data = []
    total_video_frames = 0
    for shot in shots:
        frames = round(shot["duration_sec"] * fps)
        fpath = os.path.join(base_renders_dir, shot["filename"])
        clips_data.append({"filename": shot["filename"], "path": fpath, "frames": frames})
        total_video_frames += frames

    hook_start_frames = round(hook_start_sec * fps)
    hook_end_sec = hook_start_sec + (total_video_frames / fps)

    # 4. Determine Active Audio Target
    # If trimmed audio exists, use trimmed audio at start=0; otherwise use master with in-point offset.
    if os.path.exists(trimmed_audio_path):
        active_audio_path = trimmed_audio_path
        audio_in_frame = 0
        audio_out_frame = total_video_frames
        print(f"🎧 Using Track-Specific Trimmed Audio: {trimmed_audio_path}")
    else:
        active_audio_path = audio_master_path
        audio_in_frame = hook_start_frames
        audio_out_frame = hook_start_frames + total_video_frames
        print(f"🎧 Using Master Audio with In-Point Offset: {audio_master_path}")

    # 5. Build FCP 7 XML (xmeml v5)
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE xmeml>',
        '<xmeml version="5">',
        '  <sequence>',
        f'    <name>{track_title} Hook Video ({track_slug})</name>',
        f'    <duration>{total_video_frames}</duration>',
        f'    <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
        '    <timecode>',
        f'      <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
        '      <string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat>',
        '    </timecode>',
        '    <media>',
        '      <video>',
        '        <format><samplecharacteristics><width>1280</width><height>720</height></samplecharacteristics></format>',
        '        <track>'
    ]

    current_frame = 0
    for i, clip in enumerate(clips_data):
        dur = clip["frames"]
        file_uri = win_to_uri(clip["path"])
        xml.extend([
            f'          <clipitem id="video_clip_{i+1}">',
            f'            <name>{clip["filename"]}</name>',
            f'            <duration>{dur}</duration>',
            f'            <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
            f'            <start>{current_frame}</start><end>{current_frame + dur}</end>',
            f'            <in>0</in><out>{dur}</out>',
            f'            <file id="file_vid_{i+1}">',
            f'              <name>{clip["filename"]}</name>',
            f'              <pathurl>{file_uri}</pathurl>',
            f'              <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
            '              <media><video/></media>',
            '            </file>',
            '          </clipitem>'
        ])
        current_frame += dur

    xml.extend(['        </track>', '      </video>', '      <audio>', '        <track>'])

    audio_uri = win_to_uri(active_audio_path)
    audio_filename = os.path.basename(active_audio_path)

    xml.extend([
        '          <clipitem id="audio_clip_1">',
        f'            <name>{audio_filename}</name>',
        f'            <duration>{total_video_frames}</duration>',
        f'            <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
        '            <start>0</start><end>{total_video_frames}</end>',
        f'            <in>{audio_in_frame}</in><out>{audio_out_frame}</out>',
        '            <file id="file_audio_master">',
        f'              <name>{audio_filename}</name>',
        f'              <pathurl>{audio_uri}</pathurl>',
        f'              <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
        '              <media><audio/></media>',
        '            </file>'
    ])

    # 6. Embed Markers
    marker_count = 0
    if beat_timestamps:
        for bt in beat_timestamps:
            # If beats are absolute time relative to master
            if hook_start_sec <= bt <= hook_end_sec:
                marker_frame = round((bt - hook_start_sec) * fps)
                marker_count += 1
                xml.extend([
                    '            <marker>',
                    f'              <name>Beat_{marker_count} ({bt:.3f}s)</name>',
                    f'              <in>{marker_frame}</in><out>{marker_frame}</out>',
                    '            </marker>'
                ])
            # Or if beats were pre-trimmed relative to 0s
            elif 0 <= bt <= (total_video_frames / fps) and not any(b > hook_end_sec for b in beat_timestamps):
                marker_frame = round(bt * fps)
                marker_count += 1
                xml.extend([
                    '            <marker>',
                    f'              <name>Beat_{marker_count} ({bt:.3f}s)</name>',
                    f'              <in>{marker_frame}</in><out>{marker_frame}</out>',
                    '            </marker>'
                ])
    else:
        # Default 123 BPM fallback grid
        beat_interval = 60.0 / 123.0
        curr_t = hook_start_sec
        while curr_t <= hook_end_sec:
            marker_frame = round((curr_t - hook_start_sec) * fps)
            marker_count += 1
            xml.extend([
                '            <marker>',
                f'              <name>Beat_{marker_count} ({curr_t:.3f}s)</name>',
                f'              <in>{marker_frame}</in><out>{marker_frame}</out>',
                '            </marker>'
            ])
            curr_t += beat_interval

    xml.extend(['          </clipitem>', '        </track>', '      </audio>', '    </media>', '  </sequence>', '</xmeml>'])

    os.makedirs(os.path.dirname(output_xml_path), exist_ok=True)
    with open(output_xml_path, "w", encoding="utf-8") as f:
        f.write("\n".join(xml))

    print(f"\n✅ SUCCESS! Generated Timeline XML: {output_xml_path}")
    print(f"🎯 Embedded {marker_count} beat markers onto the timeline.")
    print("=" * 65)

if __name__ == "__main__":
    run_track_pipeline(track_slug="dear_me", track_title="Dear Me")
