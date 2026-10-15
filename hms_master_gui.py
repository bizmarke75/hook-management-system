import os
import sys
import re
import wave
import pathlib
import datetime
import logging

# Check GUI availability
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False

# System Revision Definition
HMS_REV = "v2.6.0"

class HMSLogger:
    """Handles dual logging to GUI text widget and file."""
    def __init__(self, log_widget=None, log_file_path=r"C:\renders\hms_workflow.log"):
        self.log_widget = log_widget
        self.log_file_path = log_file_path
        
        # Ensure log directory exists
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_file_path)), exist_ok=True)
        except Exception:
            pass

    def log(self, message, level="INFO"):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{timestamp}] [{HMS_REV}] [{level}] {message}"
        
        # Print to stdout
        print(formatted)
        
        # Append to log file
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(formatted + "\n")
        except Exception as e:
            print(f"Warning: Could not write to log file: {e}")
            
        # Update GUI if present
        if self.log_widget and HAS_TKINTER:
            try:
                self.log_widget.insert(tk.END, formatted + "\n")
                self.log_widget.see(tk.END)
            except Exception:
                pass

def parse_time_string(val_str):
    """Parses floats ('164.281') or timecodes ('02:44.281' / '02:44:16')."""
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
            elif len(parts) == 4:
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

class HMSPipelineEngine:
    """Core workflow engine executing steps sequentially."""
    def __init__(self, config, logger):
        self.cfg = config
        self.logger = logger

    def run_step_1_rename_shots(self):
        """Step 1: Validate and rename MP4 files to shot1.mp4 ... shotN.mp4"""
        self.logger.log("--- STEP 1: VALIDATING AND RENAMING SHOTS ---")
        video_dir = self.cfg["video_dir"]
        
        if not os.path.exists(video_dir):
            self.logger.log(f"Video directory does not exist: {video_dir}", "ERROR")
            return False

        files = [f for f in os.listdir(video_dir) if f.lower().endswith(".mp4")]
        if not files:
            self.logger.log(f"No MP4 files found in {video_dir}", "WARNING")
            return False

        shot_files = [f for f in files if re.match(r"^shot\d+\.mp4$", f, re.IGNORECASE)]
        if len(shot_files) == len(files):
            self.logger.log(f"All {len(shot_files)} shots already formatted properly (shot1.mp4...shot{len(shot_files)}.mp4).")
            return True

        files.sort(key=lambda x: os.path.getmtime(os.path.join(video_dir, x)))
        self.logger.log(f"Found {len(files)} raw MP4 files. Renaming sequentially by creation timestamp...")

        renamed_count = 0
        for i, filename in enumerate(files):
            old_path = os.path.join(video_dir, filename)
            new_name = f"shot{i+1}.mp4"
            new_path = os.path.join(video_dir, new_name)
            
            if old_path != new_path:
                try:
                    os.rename(old_path, new_path)
                    self.logger.log(f"  Renamed: {filename} -> {new_name}")
                    renamed_count += 1
                except Exception as e:
                    self.logger.log(f"  Failed to rename {filename}: {e}", "ERROR")

        self.logger.log(f"Step 1 Complete: Renamed {renamed_count} shots.")
        return True

    def run_step_2_trim_audio(self):
        """Step 2: Trim master audio starting from hook timestamp."""
        self.logger.log("--- STEP 2: TRIMMING MASTER AUDIO ---")
        audio_master = self.cfg["audio_master"]
        trimmed_output = self.cfg["audio_trimmed"]
        hook_start_sec = self.cfg["hook_start_sec"]
        duration_sec = self.cfg["hook_duration_sec"]

        if not os.path.exists(audio_master):
            self.logger.log(f"Master audio not found: {audio_master}. Skipping audio trim (will use full master with offset).", "WARNING")
            return False

        try:
            with wave.open(audio_master, 'rb') as wav_in:
                params = wav_in.getparams()
                n_channels, sample_width, framerate, n_frames = params[:4]
                
                start_frame = int(hook_start_sec * framerate)
                total_trim_frames = int(duration_sec * framerate)
                
                if start_frame >= n_frames:
                    self.logger.log(f"Hook start {hook_start_sec}s exceeds total audio frames ({n_frames/framerate:.2f}s)", "ERROR")
                    return False
                    
                wav_in.setpos(start_frame)
                frames_to_read = min(total_trim_frames, n_frames - start_frame)
                raw_data = wav_in.readframes(frames_to_read)
                
                os.makedirs(os.path.dirname(os.path.abspath(trimmed_output)), exist_ok=True)
                with wave.open(trimmed_output, 'wb') as wav_out:
                    wav_out.setparams(params)
                    wav_out.writeframes(raw_data)
                    
            self.logger.log(f"Step 2 Complete: Trimmed audio saved to '{trimmed_output}' (Duration: {frames_to_read/framerate:.2f}s).")
            return True
        except Exception as e:
            self.logger.log(f"Audio trimming failed: {e}", "ERROR")
            return False

    def run_step_3_load_metadata(self):
        """Step 3: Parse track-aware beat transients and hook timestamps."""
        self.logger.log("--- STEP 3: LOADING METADATA & BEATS ---")
        slug = self.cfg["track_slug"]
        meta_dir = self.cfg["meta_dir"]

        hook_candidates = [
            os.path.join(meta_dir, f"{slug}_hooktimestamp.txt"),
            os.path.join(meta_dir, "hooktimestamp.txt"),
            os.path.join(meta_dir, "hooktimestapm.txt")
        ]
        
        hook_found = None
        for cand in hook_candidates:
            if os.path.exists(cand):
                hook_found = cand
                break
                
        if hook_found:
            with open(hook_found, "r", encoding="utf-8", errors="ignore") as f:
                parsed = parse_time_string(f.read())
                if parsed is not None:
                    self.cfg["hook_start_sec"] = parsed
                    self.logger.log(f"Parsed Hook Start Offset: {parsed:.3f}s from '{hook_found}'")
        else:
            self.logger.log(f"Hook file not found in {meta_dir}. Using default offset: {self.cfg['hook_start_sec']:.3f}s")

        beats_candidates = [
            os.path.join(meta_dir, f"{slug}_thebeats.txt"),
            os.path.join(meta_dir, "thebeats.txt")
        ]
        
        beats_found = None
        for cand in beats_candidates:
            if os.path.exists(cand):
                beats_found = cand
                break
                
        beat_timestamps = []
        if beats_found:
            with open(beats_found, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    t = parse_time_string(line)
                    if t is not None:
                        beat_timestamps.append(t)
            self.logger.log(f"Loaded {len(beat_timestamps)} transient timestamps from '{beats_found}'")
        else:
            self.logger.log(f"Beats file not found. Will fall back to 123.0 BPM grid.", "WARNING")

        self.cfg["beat_timestamps"] = beat_timestamps
        return True

    def run_step_4_generate_xml(self):
        """Step 4: Build FCP 7 XML (xmeml v5) with revision tracking metadata."""
        self.logger.log("--- STEP 4: GENERATING FCP 7 XML FOR DAVINCI RESOLVE ---")
        slug = self.cfg["track_slug"]
        title = self.cfg["track_title"]
        rev = self.cfg["revision"]
        fps = self.cfg["fps"]
        video_dir = self.cfg["video_dir"]
        xml_out = self.cfg["xml_output"]
        hook_start_sec = self.cfg["hook_start_sec"]
        beat_timestamps = self.cfg.get("beat_timestamps", [])

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
            fpath = os.path.join(video_dir, shot["filename"])
            clips_data.append({"filename": shot["filename"], "path": fpath, "frames": frames})
            total_video_frames += frames

        hook_start_frames = round(hook_start_sec * fps)
        hook_end_sec = hook_start_sec + (total_video_frames / fps)

        trimmed_audio = self.cfg["audio_trimmed"]
        master_audio = self.cfg["audio_master"]
        
        if os.path.exists(trimmed_audio):
            active_audio_path = trimmed_audio
            audio_in_frame = 0
            audio_out_frame = total_video_frames
            self.logger.log(f"Using Trimmed Audio File: {trimmed_audio}")
        else:
            active_audio_path = master_audio
            audio_in_frame = hook_start_frames
            audio_out_frame = hook_start_frames + total_video_frames
            self.logger.log(f"Using Master Audio File with offset: {master_audio}")

        xml = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<!DOCTYPE xmeml>',
            f'<!-- Generated by Hook Management System (HMS) Master GUI Engine [{rev}] -->',
            f'<!-- Track: {title} ({slug}) | Date: {datetime.datetime.now().isoformat()} -->',
            '<xmeml version="5">',
            '  <sequence>',
            f'    <name>{title} Hook Video [{rev}]</name>',
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
            '            </file>',
            '            <marker>',
            f'              <name>SYSTEM_REV: {rev}</name>',
            '              <in>0</in><out>0</out>',
            '            </marker>'
        ])

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
            beat_interval = 60.0 / 123.0
            curr_t = hook_start_sec
            while curr_t <= hook_end_sec:
                marker_frame = round((curr_t - hook_start_sec) * fps)
                marker_count += 1
                xml.extend([
                    '            <marker>',
                    f'              <name>GridBeat_{marker_count} ({curr_t:.3f}s)</name>',
                    f'              <in>{marker_frame}</in><out>{marker_frame}</out>',
                    '            </marker>'
                ])
                curr_t += beat_interval

        xml.extend(['          </clipitem>', '        </track>', '      </audio>', '    </media>', '  </sequence>', '</xmeml>'])

        os.makedirs(os.path.dirname(os.path.abspath(xml_out)), exist_ok=True)
        with open(xml_out, "w", encoding="utf-8") as f:
            f.write("\n".join(xml))

        self.logger.log(f"✅ SUCCESS! Created FCP 7 XML: {xml_out}")
        self.logger.log(f"🎯 Embedded Rev Tag '{rev}' and {marker_count} beat markers!")
        return True

    def execute_full_pipeline(self):
        """Runs all 4 steps sequentially."""
        self.logger.log(f"===========================================================")
        self.logger.log(f"🚀 STARTING FULL HMS AUTOMATED PIPELINE [{self.cfg['revision']}]")
        self.logger.log(f"===========================================================")
        
        self.run_step_3_load_metadata()
        self.run_step_1_rename_shots()
        self.run_step_2_trim_audio()
        self.run_step_4_generate_xml()
        
        self.logger.log(f"===========================================================")
        self.logger.log(f"🎉 HMS WORKFLOW COMPLETE! Ready to import into DaVinci Resolve.")
        self.logger.log(f"===========================================================")

def launch_gui():
    """Tkinter Desktop Application."""
    if not HAS_TKINTER:
        print("Tkinter is not available on this Python installation.")
        sys.exit(1)

    root = tk.Tk()
    root.title(f"Hook Management System (HMS) Master Control Panel [{HMS_REV}]")
    root.geometry("880x720")

    # Form Variables
    var_slug = tk.StringVar(value="dear_me")
    var_title = tk.StringVar(value="Dear Me")
    var_video_dir = tk.StringVar(value=r"C:\renders\dear_me")
    var_meta_dir = tk.StringVar(value=r"C:\renders\output")
    var_audio_master = tk.StringVar(value=r"C:\audio\dear_me_master.wav")
    var_rev = tk.StringVar(value=HMS_REV)
    var_fps = tk.IntVar(value=24)

    # Header
    header_frame = ttk.Frame(root, padding=10)
    header_frame.pack(fill=tk.X)
    title_lbl = ttk.Label(header_frame, text=f"🎬 Hook Management System (HMS) Control Center [{HMS_REV}]", font=("Helvetica", 14, "bold"))
    title_lbl.pack(anchor=tk.W)
    sub_lbl = ttk.Label(header_frame, text="Automated Audio Trimming, Beat Syncing, and DaVinci FCP 7 XML Generation", font=("Helvetica", 9))
    sub_lbl.pack(anchor=tk.W)

    ttk.Separator(root).pack(fill=tk.X, padx=10, pady=5)

    # Inputs Frame
    input_frame = ttk.LabelFrame(root, text=" Project Configuration & Track Metadata ", padding=10)
    input_frame.pack(fill=tk.X, padx=10, pady=5)

    # Helper File Dialog Handlers
    def browse_vdir():
        chosen = filedialog.askdirectory(title="Select Video Shots Directory", initialdir=var_video_dir.get())
        if chosen:
            var_video_dir.set(chosen.replace('/', '\\'))

    def browse_mdir():
        chosen = filedialog.askdirectory(title="Select Metadata Directory", initialdir=var_meta_dir.get())
        if chosen:
            var_meta_dir.set(chosen.replace('/', '\\'))

    def browse_audio():
        chosen = filedialog.askopenfilename(title="Select Master Audio WAV File", filetypes=[("WAV Audio Files", "*.wav"), ("All Files", "*.*")], initialdir=os.path.dirname(var_audio_master.get()))
        if chosen:
            var_audio_master.set(chosen.replace('/', '\\'))

    # Grid Form Layout
    ttk.Label(input_frame, text="Track Slug:").grid(row=0, column=0, sticky=tk.W, pady=3)
    ttk.Entry(input_frame, textvariable=var_slug, width=20).grid(row=0, column=1, sticky=tk.W, pady=3)

    ttk.Label(input_frame, text="Track Title:").grid(row=0, column=2, sticky=tk.W, pady=3, padx=(15,0))
    ttk.Entry(input_frame, textvariable=var_title, width=25).grid(row=0, column=3, sticky=tk.W, pady=3)

    ttk.Label(input_frame, text="Video Shots Directory:").grid(row=1, column=0, sticky=tk.W, pady=3)
    ttk.Entry(input_frame, textvariable=var_video_dir, width=45).grid(row=1, column=1, columnspan=3, sticky=tk.W, pady=3)
    ttk.Button(input_frame, text="Browse...", command=browse_vdir).grid(row=1, column=4, padx=5, pady=3)

    ttk.Label(input_frame, text="Metadata Directory:").grid(row=2, column=0, sticky=tk.W, pady=3)
    ttk.Entry(input_frame, textvariable=var_meta_dir, width=45).grid(row=2, column=1, columnspan=3, sticky=tk.W, pady=3)
    ttk.Button(input_frame, text="Browse...", command=browse_mdir).grid(row=2, column=4, padx=5, pady=3)

    ttk.Label(input_frame, text="Master Audio WAV:").grid(row=3, column=0, sticky=tk.W, pady=3)
    ttk.Entry(input_frame, textvariable=var_audio_master, width=45).grid(row=3, column=1, columnspan=3, sticky=tk.W, pady=3)
    ttk.Button(input_frame, text="Browse...", command=browse_audio).grid(row=3, column=4, padx=5, pady=3)

    ttk.Label(input_frame, text="Revision Tag:").grid(row=4, column=0, sticky=tk.W, pady=3)
    ttk.Entry(input_frame, textvariable=var_rev, width=15).grid(row=4, column=1, sticky=tk.W, pady=3)

    ttk.Label(input_frame, text="Timeline FPS:").grid(row=4, column=2, sticky=tk.W, pady=3, padx=(15,0))
    ttk.Entry(input_frame, textvariable=var_fps, width=10).grid(row=4, column=3, sticky=tk.W, pady=3)

    # Action Buttons Frame
    btn_frame = ttk.Frame(root, padding=10)
    btn_frame.pack(fill=tk.X)

    log_box = scrolledtext.ScrolledText(root, height=15, font=("Consolas", 9))
    logger = HMSLogger(log_widget=log_box)

    def get_config():
        slug = var_slug.get().strip()
        vdir = var_video_dir.get().strip()
        mdir = var_meta_dir.get().strip()
        audio = var_audio_master.get().strip()
        
        return {
            "track_slug": slug,
            "track_title": var_title.get().strip(),
            "video_dir": vdir,
            "meta_dir": mdir,
            "audio_master": audio,
            "audio_trimmed": os.path.join(os.path.dirname(audio), f"{slug}_master_trimmed.wav"),
            "xml_output": os.path.join(vdir, f"{slug}_hook_timeline.xml"),
            "revision": var_rev.get().strip(),
            "fps": var_fps.get(),
            "hook_start_sec": 164.281,
            "hook_duration_sec": 40.0
        }

    def run_full():
        engine = HMSPipelineEngine(get_config(), logger)
        engine.execute_full_pipeline()

    def run_step1():
        engine = HMSPipelineEngine(get_config(), logger)
        engine.run_step_1_rename_shots()

    def run_step2():
        engine = HMSPipelineEngine(get_config(), logger)
        engine.run_step_2_trim_audio()

    def run_step3():
        engine = HMSPipelineEngine(get_config(), logger)
        engine.run_step_3_load_metadata()

    def run_step4():
        engine = HMSPipelineEngine(get_config(), logger)
        engine.run_step_4_generate_xml()

    run_btn = tk.Button(btn_frame, text="🚀 EXECUTE FULL AUTOMATED PIPELINE", bg="#0275d8", fg="white", font=("Helvetica", 10, "bold"), command=run_full, height=2)
    run_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

    s1_btn = ttk.Button(btn_frame, text="1. Rename Shots", command=run_step1)
    s1_btn.pack(side=tk.LEFT, padx=2)

    s2_btn = ttk.Button(btn_frame, text="2. Trim Audio", command=run_step2)
    s2_btn.pack(side=tk.LEFT, padx=2)

    s3_btn = ttk.Button(btn_frame, text="3. Load Metadata", command=run_step3)
    s3_btn.pack(side=tk.LEFT, padx=2)

    s4_btn = ttk.Button(btn_frame, text="4. Build FCP XML", command=run_step4)
    s4_btn.pack(side=tk.LEFT, padx=2)

    # Log Output Frame
    log_frame = ttk.LabelFrame(root, text=" Live Execution Console & System Logs ", padding=10)
    log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    log_box.pack(in_=log_frame, fill=tk.BOTH, expand=True)

    logger.log(f"HMS Master Control Panel [{HMS_REV}] initialized successfully.")
    logger.log(f"Ready to process project tracks with interactive directory browsing.")

    root.mainloop()

if __name__ == "__main__":
    if HAS_TKINTER and len(sys.argv) == 1:
        launch_gui()
    else:
        cfg = {
            "track_slug": "dear_me",
            "track_title": "Dear Me",
            "video_dir": r"C:\renders\dear_me",
            "meta_dir": r"C:\renders\output",
            "audio_master": r"C:\audio\dear_me_master.wav",
            "audio_trimmed": r"C:\audio\dear_me_master_trimmed.wav",
            "xml_output": r"C:\renders\dear_me\dear_me_hook_timeline.xml",
            "revision": HMS_REV,
            "fps": 24,
            "hook_start_sec": 164.281,
            "hook_duration_sec": 40.0
        }
        logger = HMSLogger()
        engine = HMSPipelineEngine(cfg, logger)
        engine.execute_full_pipeline()
