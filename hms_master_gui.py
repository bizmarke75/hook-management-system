"""
Hook Management System (HMS) - Master Unified Pipeline GUI
Version: 3.0.0
Copyright: (c) 337 West Productions | Lancaster, PA
Description: Unified Tkinter control panel integrating Step 0 (Librosa RMS Hook & Beat Analysis),
             file browser hooks, chronological shot renaming, native 24-bit audio trimming,
             metadata synchronization, and DaVinci Resolve FCP 7 XML (xmeml v5) timeline generation.
"""

import os
import sys
import threading
import queue
import wave
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

# Safe stream redirection for PyInstaller --noconsole mode
class SafeLogRedirector:
    def __init__(self, log_queue, tag="stdout"):
        self.log_queue = log_queue
        self.tag = tag

    def write(self, message):
        if message:
            self.log_queue.put((self.tag, message))

    def flush(self):
        pass


class HMSMasterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Hook Management System (HMS) - v3.0.0 | 337 West Productions")
        self.geometry("920x760")
        self.minsize(820, 600)
        self.configure(bg="#121212")

        self.log_queue = queue.Queue()
        self.track_slug = tk.StringVar(value="grace_deficit")
        self.audio_path = tk.StringVar(value="C:/audio/grace_deficit_master.wav")
        self.render_dir = tk.StringVar(value="C:/renders/grace_deficit")
        self.hook_start = tk.DoubleVar(value=0.0)
        self.hook_end = tk.DoubleVar(value=40.0)
        self.beats = []

        self._apply_branding()
        self._build_ui()
        self._setup_logging()

    def _apply_branding(self):
        icon_path = Path("337west_icon.ico")
        if not icon_path.exists():
            icon_path = Path(getattr(sys, "_MEIPASS", ".")) / "337west_icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

    def _browse_audio(self):
        chosen = filedialog.askopenfilename(
            title="Select Master Audio WAV",
            filetypes=[("WAV Audio Files", "*.wav"), ("All Files", "*.*")]
        )
        if chosen:
            clean_path = str(Path(chosen)).replace("\\", "/")
            self.audio_path.set(clean_path)

            p = Path(chosen)
            slug = p.stem
            if slug.endswith("_master"):
                slug = slug[:-7]
            self.track_slug.set(slug)

            default_render = Path(f"C:/renders/{slug}")
            if default_render.exists():
                self.render_dir.set(str(default_render).replace("\\", "/"))
            print(f"[PATH] Master Audio: {clean_path}")
            print(f"[PATH] Active Slug: {slug}")

    def _browse_renders(self):
        chosen = filedialog.askdirectory(title="Select Video Renders Folder")
        if chosen:
            clean_path = str(Path(chosen)).replace("\\", "/")
            self.render_dir.set(clean_path)
            print(f"[PATH] Renders Folder: {clean_path}")

    def _build_ui(self):
        header = tk.Frame(self, bg="#1a1a1a", height=60, padx=15, pady=10)
        header.pack(fill=tk.X, side=tk.TOP)

        title_lbl = tk.Label(
            header,
            text="HOOK MANAGEMENT SYSTEM v3.0.0",
            font=("Segoe UI", 14, "bold"),
            fg="#ffffff",
            bg="#1a1a1a"
        )
        title_lbl.pack(side=tk.LEFT)

        subtitle_lbl = tk.Label(
            header,
            text="337 West Productions",
            font=("Segoe UI", 10, "italic"),
            fg="#888888",
            bg="#1a1a1a"
        )
        subtitle_lbl.pack(side=tk.RIGHT)

        config_frame = tk.LabelFrame(
            self,
            text=" Project Paths & Configuration ",
            font=("Segoe UI", 10, "bold"),
            bg="#181818",
            fg="#cccccc",
            padx=15,
            pady=10
        )
        config_frame.pack(fill=tk.X, padx=15, pady=10)

        # Track Slug
        tk.Label(
            config_frame, text="Track Slug:",
            font=("Segoe UI", 9, "bold"), fg="#e0e0e0", bg="#181818"
        ).grid(row=0, column=0, sticky=tk.W, pady=4)

        slug_entry = tk.Entry(
            config_frame, textvariable=self.track_slug,
            font=("Consolas", 10), bg="#282828", fg="#00ffcc", insertbackground="#ffffff", width=25
        )
        slug_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=4)

        # Master Audio File + Browse
        tk.Label(
            config_frame, text="Master WAV:",
            font=("Segoe UI", 9), fg="#e0e0e0", bg="#181818"
        ).grid(row=1, column=0, sticky=tk.W, pady=4)

        audio_entry = tk.Entry(
            config_frame, textvariable=self.audio_path,
            font=("Consolas", 9), bg="#282828", fg="#ffffff", insertbackground="#ffffff", width=60
        )
        audio_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=4)

        btn_browse_audio = tk.Button(
            config_frame, text="Browse Audio...", font=("Segoe UI", 8, "bold"),
            bg="#005577", fg="#ffffff", activebackground="#0077aa",
            command=self._browse_audio, padx=8
        )
        btn_browse_audio.grid(row=1, column=2, padx=5, pady=4)

        # Renders Folder + Browse
        tk.Label(
            config_frame, text="Renders Dir:",
            font=("Segoe UI", 9), fg="#e0e0e0", bg="#181818"
        ).grid(row=2, column=0, sticky=tk.W, pady=4)

        renders_entry = tk.Entry(
            config_frame, textvariable=self.render_dir,
            font=("Consolas", 9), bg="#282828", fg="#ffffff", insertbackground="#ffffff", width=60
        )
        renders_entry.grid(row=2, column=1, sticky=tk.W, padx=5, pady=4)

        btn_browse_renders = tk.Button(
            config_frame, text="Browse Folder...", font=("Segoe UI", 8, "bold"),
            bg="#005577", fg="#ffffff", activebackground="#0077aa",
            command=self._browse_renders, padx=8
        )
        btn_browse_renders.grid(row=2, column=2, padx=5, pady=4)

        # Pipeline Steps
        action_frame = tk.LabelFrame(
            self,
            text=" Pipeline Steps ",
            font=("Segoe UI", 10, "bold"),
            bg="#181818",
            fg="#cccccc",
            padx=15,
            pady=10
        )
        action_frame.pack(fill=tk.X, padx=15, pady=5)

        btn_style = {"font": ("Segoe UI", 9, "bold"), "width": 38, "pady": 5}

        self.btn_step0 = tk.Button(
            action_frame,
            text="Step 0: Analyze Audio (RMS Hook & Beats)",
            bg="#006688",
            fg="#ffffff",
            activebackground="#0088bb",
            command=lambda: self._run_async(self.run_step_0_analyze_audio),
            **btn_style
        )
        self.btn_step0.grid(row=0, column=0, padx=5, pady=4, sticky=tk.W)

        self.btn_step1 = tk.Button(
            action_frame,
            text="Step 1: Rename Video Shots (shot1...shotN)",
            bg="#333333",
            fg="#ffffff",
            activebackground="#444444",
            command=lambda: self._run_async(self.run_step_1_rename_shots),
            **btn_style
        )
        self.btn_step1.grid(row=0, column=1, padx=5, pady=4, sticky=tk.W)

        self.btn_step2 = tk.Button(
            action_frame,
            text="Step 2: Sub-Second Audio Trim (24-bit PCM)",
            bg="#333333",
            fg="#ffffff",
            activebackground="#444444",
            command=lambda: self._run_async(self.run_step_2_trim_audio),
            **btn_style
        )
        self.btn_step2.grid(row=1, column=0, padx=5, pady=4, sticky=tk.W)

        self.btn_step3 = tk.Button(
            action_frame,
            text="Step 3: Load Output Metadata",
            bg="#333333",
            fg="#ffffff",
            activebackground="#444444",
            command=lambda: self._run_async(self.run_step_3_load_metadata),
            **btn_style
        )
        self.btn_step3.grid(row=1, column=1, padx=5, pady=4, sticky=tk.W)

        self.btn_step4 = tk.Button(
            action_frame,
            text="Step 4: Generate DaVinci FCP 7 XML (xmeml v5)",
            bg="#2d6a4f",
            fg="#ffffff",
            activebackground="#40916c",
            command=lambda: self._run_async(self.run_step_4_generate_xml),
            **btn_style
        )
        self.btn_step4.grid(row=2, column=0, columnspan=2, padx=5, pady=6, sticky=tk.NSEW)

        # Embedded Terminal Console
        log_frame = tk.LabelFrame(
            self,
            text=" Real-Time Diagnostic Console ",
            font=("Segoe UI", 10, "bold"),
            bg="#181818",
            fg="#cccccc",
            padx=10,
            pady=5
        )
        log_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        self.console = scrolledtext.ScrolledText(
            log_frame,
            bg="#101010",
            fg="#d4d4d4",
            insertbackground="#ffffff",
            font=("Consolas", 9),
            state=tk.DISABLED,
            wrap=tk.CHAR
        )
        self.console.pack(fill=tk.BOTH, expand=True)

        self.console.tag_config("stdout", foreground="#d4d4d4")
        self.console.tag_config("stderr", foreground="#ff6b6b")

    def _setup_logging(self):
        sys.stdout = SafeLogRedirector(self.log_queue, "stdout")
        sys.stderr = SafeLogRedirector(self.log_queue, "stderr")
        self.after(100, self._process_log_queue)
        print("[INFO] HMS Master GUI v3.0.0 mounted.")
        print("[INFO] File browser hooks enabled.")

    def _process_log_queue(self):
        while not self.log_queue.empty():
            tag, msg = self.log_queue.get()
            self.console.configure(state=tk.NORMAL)
            self.console.insert(tk.END, msg, tag)
            self.console.see(tk.END)
            self.console.configure(state=tk.DISABLED)
        self.after(100, self._process_log_queue)

    def _run_async(self, func):
        threading.Thread(target=func, daemon=True).start()

    # --- PIPELINE STEP METHODS ---

    def run_step_0_analyze_audio(self):
        audio_file = Path(self.audio_path.get().strip())
        slug = self.track_slug.get().strip()

        if not audio_file.exists():
            print(f"[ERROR] Audio file not found: {audio_file}")
            print("        Click 'Browse Audio...' to select your WAV file.")
            return

        print(f"\n[RUN] Step 0: Analyzing RMS hook window & beats for {audio_file.name}...")
        try:
            import numpy as np
            import librosa

            y, sr = librosa.load(str(audio_file), sr=22050, mono=True)
            duration = librosa.get_duration(y=y, sr=sr)
            print(f"[INFO] Audio decoded: {duration:.2f}s @ {sr}Hz")

            hop_length = 512
            frame_length = 2048
            rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
            frames_per_sec = sr / hop_length
            window_size = int(40.0 * frames_per_sec)

            if len(rms) > window_size:
                window_sums = np.convolve(rms, np.ones(window_size), mode="valid")
                best_start_frame = int(np.argmax(window_sums))
                start_sec = best_start_frame / frames_per_sec
            else:
                start_sec = 0.0

            end_sec = min(start_sec + 40.0, duration)

            self.after(0, lambda: self.hook_start.set(round(start_sec, 3)))
            self.after(0, lambda: self.hook_end.set(round(end_sec, 3)))

            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
            beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)
            hook_beats = [float(b) for b in beat_times if start_sec <= b <= end_sec]
            self.beats = hook_beats

            os.makedirs("output", exist_ok=True)
            ts_path = Path(f"output/{slug}_hooktimestamp.txt")
            beats_path = Path(f"output/{slug}_thebeats.txt")

            with open(ts_path, "w", encoding="utf-8") as f:
                f.write(f"START:{start_sec:.3f}\nEND:{end_sec:.3f}\nDURATION:40.000\n")

            with open(beats_path, "w", encoding="utf-8") as f:
                for b in hook_beats:
                    f.write(f"{b:.3f}\n")

            bpm_val = float(np.atleast_1d(tempo)[0])
            print(f"[SUCCESS] Hook Window Located: {start_sec:.3f}s -> {end_sec:.3f}s (~{bpm_val:.1f} BPM)")
            print(f"[SUCCESS] Wrote timestamps: {ts_path}")
            print(f"[SUCCESS] Wrote {len(hook_beats)} beat transients: {beats_path}")

        except Exception as e:
            import traceback
            print(f"[ERROR] Step 0 failed: {str(e)}")
            print(traceback.format_exc())

    def run_step_1_rename_shots(self):
        render_dir = Path(self.render_dir.get().strip())
        if not render_dir.exists():
            print(f"[ERROR] Render directory not found: {render_dir}")
            print("        Click 'Browse Folder...' to select your video renders folder.")
            return

        print(f"\n[RUN] Step 1: Sorting and renaming video shots in {render_dir}...")
        try:
            files = [f for f in render_dir.iterdir() if f.suffix.lower() in [".mp4", ".mov"]]
            files.sort(key=lambda x: x.stat().st_mtime)

            if not files:
                print(f"[WARN] No .mp4 or .mov video files located in {render_dir}")
                return

            for idx, file_path in enumerate(files, start=1):
                target_name = f"shot{idx}.mp4"
                target_path = render_dir / target_name
                if file_path.name != target_name:
                    file_path.rename(target_path)
                    print(f"  [RENAME] {file_path.name} -> {target_name}")

            print(f"[SUCCESS] Renamed {len(files)} shots sequentially (shot1.mp4 ... shot{len(files)}.mp4).")
        except Exception as e:
            print(f"[ERROR] Step 1 failed: {str(e)}")

    def run_step_2_trim_audio(self):
        src_audio = Path(self.audio_path.get().strip())
        slug = self.track_slug.get().strip()
        dst_audio = src_audio.with_name(f"{slug}_master_trimmed.wav")

        if not src_audio.exists():
            print(f"[ERROR] Master audio file not found: {src_audio}")
            return

        start_s = self.hook_start.get()
        end_s = self.hook_end.get()

        print(f"\n[RUN] Step 2: Slicing native WAV [{start_s:.3f}s -> {end_s:.3f}s]...")
        try:
            with wave.open(str(src_audio), "rb") as wf:
                nchannels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                nframes = wf.getnframes()

                start_frame = int(start_s * framerate)
                end_frame = int(end_s * framerate)
                total_to_read = max(0, min(end_frame - start_frame, nframes - start_frame))

                wf.setpos(start_frame)
                raw_frames = wf.readframes(total_to_read)

            with wave.open(str(dst_audio), "wb") as out_wf:
                out_wf.setnchannels(nchannels)
                out_wf.setsampwidth(sampwidth)
                out_wf.setframerate(framerate)
                out_wf.writeframes(raw_frames)

            bit_depth = sampwidth * 8
            print(f"[SUCCESS] Exported trimmed audio: {dst_audio}")
            print(f"[INFO] Preserved: {bit_depth}-bit PCM, {framerate} Hz, {nchannels} channels.")
        except Exception as e:
            print(f"[ERROR] Step 2 failed: {str(e)}")

    def run_step_3_load_metadata(self):
        slug = self.track_slug.get().strip()
        ts_path = Path(f"output/{slug}_hooktimestamp.txt")
        beats_path = Path(f"output/{slug}_thebeats.txt")

        print(f"\n[RUN] Step 3: Loading metadata for '{slug}'...")
        try:
            if ts_path.exists():
                with open(ts_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("START:"):
                            self.hook_start.set(float(line.split(":")[1].strip()))
                        elif line.startswith("END:"):
                            self.hook_end.set(float(line.split(":")[1].strip()))
                print(f"[INFO] Hook Window: {self.hook_start.get():.3f}s -> {self.hook_end.get():.3f}s")

            if beats_path.exists():
                with open(beats_path, "r", encoding="utf-8") as f:
                    self.beats = [float(line.strip()) for line in f if line.strip()]
                print(f"[INFO] Loaded {len(self.beats)} transient beat markers.")

            print("[SUCCESS] Metadata synchronized.")
        except Exception as e:
            print(f"[ERROR] Step 3 failed: {str(e)}")

    def run_step_4_generate_xml(self):
        slug = self.track_slug.get().strip()
        render_dir = Path(self.render_dir.get().strip())
        src_audio = Path(self.audio_path.get().strip())
        trimmed_audio = src_audio.with_name(f"{slug}_master_trimmed.wav")
        xml_out = Path(f"output/{slug}_davinci_timeline.xml")

        print(f"\n[RUN] Step 4: Generating FCP 7 XML (xmeml v5) interchange...")
        try:
            fps = 24
            shots = sorted([f for f in render_dir.iterdir() if f.name.startswith("shot") and f.suffix == ".mp4"])
            if not shots:
                print(f"[ERROR] No shot*.mp4 files found in {render_dir}")
                return

            xml_lines = [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<!DOCTYPE xmeml>',
                '<xmeml version="5">',
                '  <sequence>',
                f'    <name>HMS_{slug.upper()}_TIMELINE</name>',
                '    <duration>960</duration>',
                '    <rate>',
                '      <timebase>24</timebase>',
                '      <ntsc>FALSE</ntsc>',
                '    </rate>',
                '    <media>',
                '      <video>',
                '        <format>',
                '          <samplecharacteristics>',
                '            <width>1920</width>',
                '            <height>1080</height>',
                '          </samplecharacteristics>',
                '        </format>',
                '        <track>'
            ]

            current_frame = 0
            shot_duration = 960 // len(shots)

            for idx, shot in enumerate(shots):
                dur = shot_duration if idx < len(shots) - 1 else (960 - current_frame)
                in_f = 0
                out_f = dur
                xml_lines.extend([
                    '          <clipitem>',
                    f'            <name>{shot.name}</name>',
                    f'            <duration>{dur}</duration>',
                    '            <rate><timebase>24</timebase></rate>',
                    f'            <start>{current_frame}</start>',
                    f'            <end>{current_frame + dur}</end>',
                    f'            <in>{in_f}</in>',
                    f'            <out>{out_f}</out>',
                    f'            <file id="file_{idx}">',
                    f'              <name>{shot.name}</name>',
                    f'              <pathurl>file://localhost/{str(shot).replace(os.sep, "/")}</pathurl>',
                    '              <rate><timebase>24</timebase></rate>',
                    '            </file>',
                    '          </clipitem>'
                ])
                current_frame += dur

            xml_lines.extend([
                '        </track>',
                '      </video>',
                '      <audio>',
                '        <track>'
            ])

            audio_url = f"file://localhost/{str(trimmed_audio).replace(os.sep, '/')}"
            xml_lines.extend([
                '          <clipitem>',
                f'            <name>{trimmed_audio.name}</name>',
                '            <duration>960</duration>',
                '            <rate><timebase>24</timebase></rate>',
                '            <start>0</start>',
                '            <end>960</end>',
                '            <in>0</in>',
                '            <out>960</out>',
                '            <file id="audio_master">',
                f'              <name>{trimmed_audio.name}</name>',
                f'              <pathurl>{audio_url}</pathurl>',
                '              <rate><timebase>24</timebase></rate>',
                '            </file>'
            ])

            hook_start = self.hook_start.get()
            for b in self.beats:
                rel_sec = b - hook_start
                if 0 <= rel_sec <= 40.0:
                    marker_frame = int(rel_sec * fps)
                    xml_lines.extend([
                        '            <marker>',
                        '              <name>BEAT</name>',
                        '              <comment>Transient Pin</comment>',
                        f'              <in>{marker_frame}</in>',
                        '              <out>-1</out>',
                        '              <color>Blue</color>',
                        '            </marker>'
                    ])

            xml_lines.extend([
                '          </clipitem>',
                '        </track>',
                '      </audio>',
                '    </media>',
                '  </sequence>',
                '</xmeml>'
            ])

            with open(xml_out, "w", encoding="utf-8") as f:
                f.write("\n".join(xml_lines))

            print(f"[SUCCESS] Timeline XML Interchange written: {xml_out}")
            print("[INFO] Ready for DaVinci Resolve Free import (File -> Import -> Timeline).")
        except Exception as e:
            print(f"[ERROR] Step 4 failed: {str(e)}")


if __name__ == "__main__":
    app = HMSMasterApp()
    app.mainloop()