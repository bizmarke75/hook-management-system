import os
import pathlib
import re

def parse_time_string(val_str):
    """Parses pure floats ('164.281') or timecode strings ('02:44.281')."""
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

def generate_final_xml(
    output_dir_win=r"C:\renders\output",
    video_dir_win=r"C:\renders\dear_me",
    audio_file_win=r"C:\audio\dear_me_master.wav",
    output_xml_path=r"C:\renders\dear_me_hook_final.xml",
    fps=24
):
    print("=" * 60)
    print("🎬 HOOK MANAGEMENT SYSTEM — FINAL TIMELINE BUILDER")
    print("=" * 60)
    
    # 1. Parse Hook Timestamp
    hook_file_names = ["hooktimestapm.txt", "hooktimestamp.txt"]
    hook_start_sec = 164.281  # Default fallback (02:44.281)
    
    found_hook_file = None
    for hname in hook_file_names:
        hpath = os.path.join(output_dir_win, hname)
        if os.path.exists(hpath):
            found_hook_file = hpath
            break
            
    if found_hook_file and os.path.exists(found_hook_file):
        print(f"📄 Found Hook Timestamp File: {found_hook_file}")
        with open(found_hook_file, "r", encoding="utf-8", errors="ignore") as f:
            parsed_time = parse_time_string(f.read())
            if parsed_time is not None:
                hook_start_sec = parsed_time
                print(f"  └─ Parsed Hook Start: {hook_start_sec:.3f}s")
    else:
        print(f"ℹ️ Hook file not found in {output_dir_win}. Using default offset: {hook_start_sec:.3f}s.")

    # 2. Parse Beats
    beats_file = os.path.join(output_dir_win, "thebeats.txt")
    beat_timestamps = []
    
    if os.path.exists(beats_file):
        print(f"📄 Found Beats File: {beats_file}")
        with open(beats_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                t = parse_time_string(line)
                if t is not None:
                    beat_timestamps.append(t)
        print(f"  └─ Loaded {len(beat_timestamps)} beat timestamps.")

    # 3. Shot Durations (24 fps)
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
        fpath = os.path.join(video_dir_win, shot["filename"])
        clips_data.append({"filename": shot["filename"], "path": fpath, "frames": frames})
        total_video_frames += frames

    hook_start_frames = round(hook_start_sec * fps)
    hook_end_sec = hook_start_sec + (total_video_frames / fps)

    # 4. Construct FCP 7 XML (xmeml v5)
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE xmeml>',
        '<xmeml version="5">',
        '  <sequence>',
        '    <name>Dear Me Hook Video (123 BPM)</name>',
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

    audio_uri = win_to_uri(audio_file_win)
    audio_filename = os.path.basename(audio_file_win)
    
    xml.extend([
        '          <clipitem id="audio_clip_1">',
        f'            <name>{audio_filename}</name>',
        f'            <duration>{total_video_frames}</duration>',
        f'            <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
        '            <start>0</start><end>{total_video_frames}</end>',
        f'            <in>{hook_start_frames}</in><out>{hook_start_frames + total_video_frames}</out>',
        '            <file id="file_audio_master">',
        f'              <name>{audio_filename}</name>',
        f'              <pathurl>{audio_uri}</pathurl>',
        f'              <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
        '              <media><audio/></media>',
        '            </file>'
    ])

    # Embed Transient Markers from thebeats.txt (or generate quarter-note markers if none found)
    marker_count = 0
    if beat_timestamps:
        for bt in beat_timestamps:
            if hook_start_sec <= bt <= hook_end_sec:
                marker_frame = round((bt - hook_start_sec) * fps)
                marker_count += 1
                xml.extend([
                    '            <marker>',
                    f'              <name>Beat_{marker_count} ({bt:.3f}s)</name>',
                    f'              <in>{marker_frame}</in><out>{marker_frame}</out>',
                    '            </marker>'
                ])
    else:
        # Fallback to 123 BPM grid markers
        beat_interval = 60.0 / 123.0  # 0.4878s
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

    out_dir = os.path.dirname(os.path.abspath(output_xml_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        
    with open(output_xml_path, "w", encoding="utf-8") as f:
        f.write("\n".join(xml))
        
    print(f"\n✅ SUCCESS! Generated Timeline XML at: {output_xml_path}")
    print(f"🎯 Embedded {marker_count} beat markers onto the timeline!")

if __name__ == "__main__":
    generate_final_xml()
