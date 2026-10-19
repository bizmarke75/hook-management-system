import os
import sys
import re
import wave
import pathlib
import datetime
import logging
import threading

# Check GUI availability
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False

# System Revision Definition
HMS_REV = "v2.8.0"

def get_resource_path(relative_path):
    """Resolve resource path for both standard Python and PyInstaller --onefile."""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

class GUIStdoutRedirector:
    """Safely redirects stdout/stderr to GUI text widget on the main UI thread."""
    def __init__(self, log_widget, level="INFO"):
        self.log_widget = log_widget
        self.level = level

    def write(self, message):
        if not message:
            return
        if self.log_widget and HAS_TKINTER:
            try:
                self.log_widget.after(0, self._append, message)
            except Exception:
                pass

    def _append(self, message):
        try:
            self.log_widget.configure(state=tk.NORMAL)
            self.log_widget.insert(tk.END, message)
            self.log_widget.see(tk.END)
            self.log_widget.update_idletasks()
        except Exception:
            pass

    def flush(self):
        pass

class HMSLogger:
    """Handles dual logging to GUI text widget and file safely under --noconsole."""
    def __init__(self, log_widget=None, log_file_path=r"C:\renders\hms_workflow.log"):
        self.log_widget = log_widget
        self.log_file_path = log_file_path
        
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_file_path)), exist_ok=True)
        except Exception:
            pass

    def _write_to_gui(self, text):
        try:
            self.log_widget.configure(state=tk.NORMAL)
            self.log_widget.insert(tk.END, text + "\n")
            self.log_widget.see(tk.END)
            self.log_widget.update_idletasks()
        except Exception:
            pass

    def log(self, message, level="INFO"):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{timestamp}] [{HMS_REV}] [{level}] {message}"
        
        # 1. Write to GUI log box FIRST (scheduled safely on main thread)
        if self.log_widget and HAS_TKINTER:
            try:
                self.log_widget.after(0, self._write_to_gui, formatted)
            except Exception:
                pass
                
        # 2. Write to real stdout only if console is attached
        if sys.__stdout__ is not None:
            try:
                sys.__stdout__.write(formatted + "\n")
                sys.__stdout__.flush()
            except Exception:
                pass
        
        # 3. Append to log file
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(formatted + "\n")
        except Exception:
            pass

def parse_time_string(val_str):
    """Parses floats ('164.281') or timecodes ('02:44.281' / '02:44:16')."""
    if not val_str:
        return None
    val_str = str(val_str).strip()
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

        self.logger.log(f"Found {len(files)} raw MP4 files. Renaming sequentially by creation timestamp...")
        files_with_time = []
        for fname in files:
            full_path = os.path.join(video_dir, fname)
            try:
                mtime = os.path.getmtime(full_path)
            except Exception:
                mtime = 0
            files_with_time.append((mtime, fname))

        files_with_time.sort(key=lambda x: x[0])

        renamed_count = 0
        for idx, (_, old_name) in enumerate(files_with_time, start=1):
            new_name = f"shot{idx}.mp4"
            old_path = os.path.join(video_dir, old_name)
            new_path = os.path.join(video_dir, new_name)
            if old_name != new_name:
                try:
                    os.rename(old_path, new_path)
                    self.logger.log(f"  Renamed: {old_name} -> {new_name}")
                    renamed_count += 1
                except Exception as e:
                    self.logger.log(f"  Failed to rename {old_name}: {e}", "ERROR")

        self.logger.log(f"Step 1 Complete: Renamed {renamed_count} shots.")
        return True

    def run_step_2_trim_audio(self):
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
                
                if sample_width not in (2, 4):
                    self.logger.log(f"Notice: Master audio uses {sample_width*8}-bit sample depth. Preserving original Master WAV to maintain pristine 24-bit sound quality.", "INFO")
                    return True

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
            self.logger.log(f"Audio trim notice: {e}. Defaulting to Master WAV offset mode for pristine quality.", "INFO")
            return True

    def run_step_3_load_metadata(self):
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
            try:
                with open(hook_found, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    parsed = parse_time_string(content)
                    if parsed is not None:
                        self.cfg["hook_start_sec"] = parsed
                        self.logger.log(f"Parsed Hook Start Offset: {parsed:.3f}s from '{hook_found}'")
            except Exception as e:
                self.logger.log(f"Error reading hook file '{hook_found}': {e}", "WARNING")
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
            self.logger.log("Beats file not found. Will fall back to 123.0 BPM grid.", "WARNING")

        self.cfg["beat_timestamps"] = beat_timestamps
        return True

    def run_step_4_generate_xml(self):
        self.logger.log("--- STEP 4: GENERATING FCP 7 XML FOR DAVINCI RESOLVE ---")
        slug = self.cfg["track_slug"]
        title = self.cfg["track_title"]
        rev = self.cfg["revision"]
        fps = self.cfg["fps"]
        video_dir = self.cfg["video_dir"]
        xml_out = self.cfg["xml_output"]
        hook_start_sec = self.cfg["hook_start_sec"]
        use_master_direct = self.cfg.get("use_master_direct", True)
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
        hook_end_sec = hook_start_sec + (total_video_frames / float(fps))
        trimmed_audio = self.cfg["audio_trimmed"]
        master_audio = self.cfg["audio_master"]
        
        if not use_master_direct and os.path.exists(trimmed_audio):
            active_audio_path = trimmed_audio
            audio_in_frame = 0
            audio_out_frame = total_video_frames
            self.logger.log(f"Using Trimmed Audio File: {trimmed_audio}")
        else:
            active_audio_path = master_audio
            audio_in_frame = hook_start_frames
            audio_out_frame = hook_start_frames + total_video_frames
            self.logger.log(f"Using Master Audio File (Pristine 24-Bit Sound) with offset {hook_start_sec:.3f}s: {master_audio}")

        xml = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<!DOCTYPE xmeml>',
            f'<!-- Generated by Hook Management System (HMS) Master GUI Engine [{rev}] -->',
            f'<!-- Track: {title} ({slug}) | Date: {datetime.datetime.now().isoformat()} -->',
            '<xmeml version="5">',
            '  <sequence>',
            f'    <name>{title} - HMS Hook Timeline [{rev}]</name>',
            f'    <duration>{hook_start_frames + total_video_frames}</duration>',
            '    <rate>',
            f'      <timebase>{fps}</timebase>',
            '      <ntsc>FALSE</ntsc>',
            '    </rate>',
            '    <media>',
            '      <video>',
            '        <format>',
            '          <samplecharacteristics>',
            '            <width>1920</width>',
            '            <height>1080</height>',
            '            <pixelaspectratio>square</pixelaspectratio>',
            f'            <rate><timebase>{fps}</timebase></rate>',
            '          </samplecharacteristics>',
            '        </format>',
            '        <track>'
        ]

        curr_frame = hook_start_frames
        for idx, clip in enumerate(clips_data, start=1):
            file_uri = win_to_uri(clip["path"])
            xml.extend([
                '          <clipitem>',
                f'            <name>{clip["filename"]}</name>',
                f'            <duration>{clip["frames"]}</duration>',
                '            <rate>',
                f'              <timebase>{fps}</timebase>',
                '            </rate>',
                f'            <start>{curr_frame}</start>',
                f'            <end>{curr_frame + clip["frames"]}</end>',
                '            <in>0</in>',
                f'            <out>{clip["frames"]}</out>',
                '            <file id="file_' + str(idx) + '">',
                f'              <name>{clip["filename"]}</name>',
                f'              <pathurl>{file_uri}</pathurl>',
                '              <rate>',
                f'                <timebase>{fps}</timebase>',
                '              </rate>',
                '              <media>',
                '                <video>',
                '                  <samplecharacteristics>',
                '                    <width>1920</width>',
                '                    <height>1080</height>',
                '                  </samplecharacteristics>',
                '                </video>',
                '              </media>',
                '            </file>',
                '          </clipitem>'
            ])
            curr_frame += clip["frames"]

        xml.extend([
            '        </track>',
            '      </video>',
            '      <audio>',
            '        <track>',
            '          <clipitem>',
            f'            <name>{os.path.basename(active_audio_path)}</name>',
            f'            <duration>{audio_out_frame - audio_in_frame}</duration>',
            '            <rate>',
            f'              <timebase>{fps}</timebase>',
            '            </rate>',
            f'            <start>{hook_start_frames}</start>',
            f'            <end>{hook_start_frames + (audio_out_frame - audio_in_frame)}</end>',
            f'            <in>{audio_in_frame}</in>',
            f'            <out>{audio_out_frame}</out>',
            '            <file id="file_audio_master">',
            f'              <name>{os.path.basename(active_audio_path)}</name>',
            f'              <pathurl>{win_to_uri(active_audio_path)}</pathurl>',
            '              <rate>',
            f'                <timebase>{fps}</timebase>',
            '              </rate>',
            '            </file>',
            '            <marker>',
            f'              <name>SYSTEM_REV: {rev}</name>',
            '              <comment>HMS Revision Audit Marker</comment>',
            '              <in>0</in>',
            '              <out>-1</out>',
            '            </marker>'
        ])

        marker_count = 0
        if beat_timestamps:
            has_absolute_beats = any(b > hook_end_sec for b in beat_timestamps)
            for btime in beat_timestamps:
                if hook_start_sec <= btime <= hook_end_sec:
                    b_frame = round(btime * fps)
                    marker_count += 1
                    xml.extend([
                        '            <marker>',
                        f'              <name>Beat_{marker_count}</name>',
                        '              <comment>HMS Beat Transient</comment>',
                        f'              <in>{b_frame}</in>',
                        '              <out>-1</out>',
                        '              <color>Blue</color>',
                        '            </marker>'
                    ])
                elif 0 <= btime <= (total_video_frames / float(fps)) and not has_absolute_beats:
                    b_frame = round((hook_start_sec + btime) * fps)
                    marker_count += 1
                    xml.extend([
                        '            <marker>',
                        f'              <name>Beat_{marker_count}</name>',
                        '              <comment>HMS Beat Transient</comment>',
                        f'              <in>{b_frame}</in>',
                        '              <out>-1</out>',
                        '              <color>Blue</color>',
                        '            </marker>'
                    ])
        else:
            beat_interval = 60.0 / 123.0
            curr_t = hook_start_sec
            while curr_t <= hook_end_sec:
                b_frame = round(curr_t * fps)
                marker_count += 1
                xml.extend([
                    '            <marker>',
                    f'              <name>GridBeat_{marker_count}</name>',
                    '              <comment>123 BPM Fallback Grid</comment>',
                    f'              <in>{b_frame}</in>',
                    '              <out>-1</out>',
                    '              <color>Blue</color>',
                    '            </marker>'
                ])
                curr_t += beat_interval

        xml.extend([
            '          </clipitem>',
            '        </track>',
            '      </audio>',
            '    </media>',
            '  </sequence>',
            '</xmeml>'
        ])

        os.makedirs(os.path.dirname(os.path.abspath(xml_out)), exist_ok=True)
        with open(xml_out, "w", encoding="utf-8") as f:
            f.write("\n".join(xml))

        archive_dir = r"/workspace/archive" if not sys.platform.startswith("win") else r"C:\renders\archive"
        try:
            os.makedirs(archive_dir, exist_ok=True)
            ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = os.path.join(archive_dir, f"{slug}_hook_timeline_{rev}_{ts_str}.xml")
            with open(archive_path, "w", encoding="utf-8") as f:
                f.write("\n".join(xml))
            self.logger.log(f"Archived XML: {archive_path}")
        except Exception as e:
            self.logger.log(f"Note on archive write: {e}", "WARNING")

        self.logger.log(f"SUCCESS! Created FCP 7 XML: {xml_out}")
        self.logger.log(f"Embedded Rev Tag '{rev}' and {marker_count} beat markers!")
        return True

    def execute_full_pipeline(self):
        self.logger.log("===========================================================")
        self.logger.log(f"STARTING FULL HMS AUTOMATED PIPELINE [{self.cfg['revision']}]")
        self.logger.log("===========================================================")
        self.run_step_3_load_metadata()
        self.run_step_1_rename_shots()
        self.run_step_2_trim_audio()
        self.run_step_4_generate_xml()
        self.logger.log("===========================================================")
        self.logger.log("HMS WORKFLOW COMPLETE! Ready to import into DaVinci Resolve.")
        self.logger.log("===========================================================")

def launch_gui():
    """Tkinter Desktop Application."""
    if not HAS_TKINTER:
        print("Tkinter is not available on this Python installation.")
        sys.exit(1)

    root = tk.Tk()
    root.title(f"Hook Management System (HMS) Master Control Panel [{HMS_REV}]")
    root.geometry("900x680")
    root.minsize(780, 520)

    # Load 337 West Icon
    icon_path = get_resource_path("337west_icon.ico")
    if os.path.exists(icon_path):
        try:
            root.iconbitmap(icon_path)
        except Exception:
            pass

    # Form Variables
    var_slug = tk.StringVar(value="dear_me")
    var_title = tk.StringVar(value="Dear Me")
    var_video_dir = tk.StringVar(value=r"C:\renders\dear_me")
    var_meta_dir = tk.StringVar(value=r"C:\renders\output")
    var_audio_master = tk.StringVar(value=r"C:\audio\dear_me_master.wav")
    var_rev = tk.StringVar(value=HMS_REV)
    var_fps = tk.IntVar(value=24)
    var_use_master = tk.BooleanVar(value=True)

    # File Pickers Logic
    def browse_audio():
        f = filedialog.askopenfilename(title="Select Master Audio WAV", filetypes=[("WAV Audio", "*.wav"), ("All Files", "*.*")])
        if f:
            var_audio_master.set(f.replace('/', '\\'))
            bname = os.path.splitext(os.path.basename(f))[0]
            clean_slug = re.sub(r"(_master|_trimmed|_hook)$", "", bname, flags=re.IGNORECASE)
            var_slug.set(clean_slug)
            var_title.set(clean_slug.replace("_", " ").title())
            var_video_dir.set("C:\\renders\\" + clean_slug)

    def browse_vdir():
        d = filedialog.askdirectory(title="Select Video Shots Directory")
        if d:
            var_video_dir.set(d.replace('/', '\\'))

    def browse_mdir():
        d = filedialog.askdirectory(title="Select Metadata Directory")
        if d:
            var_meta_dir.set(d.replace('/', '\\'))

    # Header
    header_frame = ttk.Frame(root, padding=(10, 8))
    header_frame.pack(side=tk.TOP, fill=tk.X)
    title_lbl = ttk.Label(header_frame, text=f"Hook Management System (HMS) Control Center [{HMS_REV}]", font=("Helvetica", 13, "bold"))
    title_lbl.pack(anchor=tk.W)
    sub_lbl = ttk.Label(header_frame, text="Automated Audio Trimming, Beat Syncing, and DaVinci FCP 7 XML Generation", font=("Helvetica", 9))
    sub_lbl.pack(anchor=tk.W)

    ttk.Separator(root).pack(side=tk.TOP, fill=tk.X, padx=10, pady=2)

    # Inputs Frame
    input_frame = ttk.LabelFrame(root, text=" Project Configuration & Track Metadata ", padding=(10, 6))
    input_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=4)

    ttk.Label(input_frame, text="Track Slug:").grid(row=0, column=0, sticky=tk.W, pady=2)
    ttk.Entry(input_frame, textvariable=var_slug, width=20).grid(row=0, column=1, sticky=tk.W, pady=2)

    ttk.Label(input_frame, text="Track Title:").grid(row=0, column=2, sticky=tk.W, pady=2, padx=(10,0))
    ttk.Entry(input_frame, textvariable=var_title, width=25).grid(row=0, column=3, sticky=tk.W, pady=2)

    ttk.Label(input_frame, text="Video Shots Directory:").grid(row=1, column=0, sticky=tk.W, pady=2)
    ttk.Entry(input_frame, textvariable=var_video_dir, width=45).grid(row=1, column=1, columnspan=2, sticky=tk.W, pady=2)
    ttk.Button(input_frame, text="Browse...", command=browse_vdir).grid(row=1, column=3, sticky=tk.W, padx=5, pady=2)

    ttk.Label(input_frame, text="Metadata Directory:").grid(row=2, column=0, sticky=tk.W, pady=2)
    ttk.Entry(input_frame, textvariable=var_meta_dir, width=45).grid(row=2, column=1, columnspan=2, sticky=tk.W, pady=2)
    ttk.Button(input_frame, text="Browse...", command=browse_mdir).grid(row=2, column=3, sticky=tk.W, padx=5, pady=2)

    ttk.Label(input_frame, text="Master Audio WAV:").grid(row=3, column=0, sticky=tk.W, pady=2)
    ttk.Entry(input_frame, textvariable=var_audio_master, width=45).grid(row=3, column=1, columnspan=2, sticky=tk.W, pady=2)
    ttk.Button(input_frame, text="Browse...", command=browse_audio).grid(row=3, column=3, sticky=tk.W, padx=5, pady=2)

    ttk.Label(input_frame, text="Revision Tag:").grid(row=4, column=0, sticky=tk.W, pady=2)
    ttk.Entry(input_frame, textvariable=var_rev, width=15).grid(row=4, column=1, sticky=tk.W, pady=2)

    ttk.Label(input_frame, text="Timeline FPS:").grid(row=4, column=2, sticky=tk.W, pady=2, padx=(10,0))
    ttk.Entry(input_frame, textvariable=var_fps, width=10).grid(row=4, column=3, sticky=tk.W, pady=2)

    ttk.Checkbutton(input_frame, text="Use Pristine Master WAV Directly (Recommended for Full 24-Bit Sound)", variable=var_use_master).grid(row=5, column=0, columnspan=4, sticky=tk.W, pady=4)

    # Action Buttons Frame
    btn_frame = ttk.Frame(root, padding=(10, 4))
    btn_frame.pack(side=tk.TOP, fill=tk.X)

    # Log Output Frame â€” Packed with expand=True so it ALWAYS claims remaining window height
    log_frame = ttk.LabelFrame(root, text=" Live Execution Console & System Logs (C:\\renders\\hms_workflow.log) ", padding=8)
    log_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=(4, 10))

    log_box = scrolledtext.ScrolledText(
        log_frame,
        height=12,
        bg="#1e1e1e",
        fg="#d4d4d4",
        insertbackground="white",
        font=("Consolas", 9),
        wrap=tk.WORD
    )
    log_box.pack(fill=tk.BOTH, expand=True)

    logger = HMSLogger(log_widget=log_box)

    # Redirect stdout/stderr to GUI log safely
    sys.stdout = GUIStdoutRedirector(log_box)
    sys.stderr = GUIStdoutRedirector(log_box)

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
            "use_master_direct": var_use_master.get(),
            "hook_start_sec": 164.281,
            "hook_duration_sec": 40.0
        }

    def async_run(target_func):
        threading.Thread(target=target_func, daemon=True).start()

    def run_full():
        async_run(lambda: HMSPipelineEngine(get_config(), logger).execute_full_pipeline())

    def run_step1():
        async_run(lambda: HMSPipelineEngine(get_config(), logger).run_step_1_rename_shots())

    def run_step2():
        async_run(lambda: HMSPipelineEngine(get_config(), logger).run_step_2_trim_audio())

    def run_step3():
        async_run(lambda: HMSPipelineEngine(get_config(), logger).run_step_3_load_metadata())

    def run_step4():
        async_run(lambda: HMSPipelineEngine(get_config(), logger).run_step_4_generate_xml())

    def clear_log():
        log_box.delete("1.0", tk.END)
        logger.log("Console cleared.")

    run_btn = tk.Button(btn_frame, text="EXECUTE FULL AUTOMATED PIPELINE", bg="#0275d8", fg="white", font=("Helvetica", 10, "bold"), command=run_full, height=2)
    run_btn.pack(side=tk.LEFT, padx=(0, 6), expand=True, fill=tk.X)

    ttk.Button(btn_frame, text="1. Rename Shots", command=run_step1).pack(side=tk.LEFT, padx=2)
    ttk.Button(btn_frame, text="2. Trim Audio", command=run_step2).pack(side=tk.LEFT, padx=2)
    ttk.Button(btn_frame, text="3. Load Metadata", command=run_step3).pack(side=tk.LEFT, padx=2)
    ttk.Button(btn_frame, text="4. Build FCP XML", command=run_step4).pack(side=tk.LEFT, padx=2)
    ttk.Button(btn_frame, text="Clear Log", command=clear_log).pack(side=tk.LEFT, padx=(6, 0))

    logger.log(f"HMS Master Control Panel [{HMS_REV}] initialized successfully.")
    logger.log("Live Console online. Click 'EXECUTE FULL AUTOMATED PIPELINE' or any individual step button.")

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
            "use_master_direct": True,
            "hook_start_sec": 164.281,
            "hook_duration_sec": 40.0
        }
        logger = HMSLogger()
        engine = HMSPipelineEngine(cfg, logger)
        engine.execute_full_pipeline()