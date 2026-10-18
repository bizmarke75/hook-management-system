import os
import xml.etree.ElementTree as ET

def generate_final_xml():
    video_dir_win = r"C:\renders\dear_me"
    audio_file_win = r"C:\audio\dear_me_master.wav"
    audio_filename = "dear_me_master.wav"
    output_xml_path = "/workspace/scratch/dear_me_hook_final.xml"
    fps = 24
    hook_start_sec = 164.281  # 02:44.281
    
    shots = [
        {"filename": "shot1.mp4", "duration_sec": 5.7083, "frames": 137},
        {"filename": "shot2.mp4", "duration_sec": 8.0000, "frames": 192},
        {"filename": "shot3.mp4", "duration_sec": 10.0000, "frames": 240},
        {"filename": "shot4.mp4", "duration_sec": 8.0000, "frames": 192},
        {"filename": "shot5.mp4", "duration_sec": 8.2917, "frames": 199},
    ]

    total_video_frames = sum(s["frames"] for s in shots)
    hook_start_frames = round(hook_start_sec * fps)
    hook_end_frames = hook_start_frames + total_video_frames

    def win_to_uri(path_str):
        clean = path_str.replace('\\', '/')
        if not clean.startswith('/'):
            clean = '/' + clean
        return f"file://localhost{clean}"

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE xmeml>',
        '<xmeml version="5">',
        '  <sequence>',
        '    <name>Dear Me Hook Video (123 BPM Final)</name>',
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
    for i, shot in enumerate(shots):
        dur = shot["frames"]
        file_path = f"{video_dir_win}\\{shot['filename']}"
        file_uri = win_to_uri(file_path)
        xml.extend([
            f'          <clipitem id="video_clip_{i+1}">',
            f'            <name>{shot["filename"]}</name>',
            f'            <duration>{dur}</duration>',
            f'            <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
            f'            <start>{current_frame}</start><end>{current_frame + dur}</end>',
            f'            <in>0</in><out>{dur}</out>',
            f'            <file id="file_vid_{i+1}">',
            f'              <name>{shot["filename"]}</name>',
            f'              <pathurl>{file_uri}</pathurl>',
            f'              <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
            '              <media><video/></media>',
            '            </file>',
            '          </clipitem>'
        ])
        current_frame += dur

    xml.extend(['        </track>', '      </video>', '      <audio>', '        <track>'])

    audio_uri = win_to_uri(audio_file_win)
    
    xml.extend([
        '          <clipitem id="audio_clip_1">',
        f'            <name>{audio_filename}</name>',
        f'            <duration>{total_video_frames}</duration>',
        f'            <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
        '            <start>0</start>',
        f'            <end>{total_video_frames}</end>',
        f'            <in>{hook_start_frames}</in>',
        f'            <out>{hook_end_frames}</out>',
        '            <file id="file_audio_master">',
        f'              <name>{audio_filename}</name>',
        f'              <pathurl>{audio_uri}</pathurl>',
        f'              <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
        '              <media><audio/></media>',
        '            </file>'
    ])

    # Generate 123.0 BPM Beat Transient Markers (Quarter notes @ 0.4878s = 11.707 frames)
    beat_interval_sec = 60.0 / 123.0  # ~0.487804878s
    num_beats = int(40.0 / beat_interval_sec)
    for b in range(num_beats + 1):
        bt_sec = hook_start_sec + b * beat_interval_sec
        marker_frame = round(b * beat_interval_sec * fps)
        if marker_frame <= total_video_frames:
            xml.extend([
                '            <marker>',
                f'              <name>Snare/Beat_{b+1} ({bt_sec:.3f}s)</name>',
                f'              <in>{marker_frame}</in><out>{marker_frame}</out>',
                '            </marker>'
            ])

    xml.extend([
        '          </clipitem>',
        '        </track>',
        '      </audio>',
        '    </media>',
        '  </sequence>',
        '</xmeml>'
    ])

    xml_content = "\n".join(xml)
    
    with open(output_xml_path, "w", encoding="utf-8") as f:
        f.write(xml_content)

    print(f"✅ Generated XML successfully at {output_xml_path}")

    # Validate XML parsing
    ET.fromstring(xml_content)
    print("✅ XML structure is valid!")

if __name__ == "__main__":
    generate_final_xml()
