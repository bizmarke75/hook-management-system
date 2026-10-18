import os
import wave

def trim_master_audio(
    input_wav=r"C:\audio\dear_me_master.wav",
    output_wav=r"C:\audio\dear_me_hook_trimmed.wav",
    start_sec=164.281, # 02:44.281 hook offset
    duration_sec=40.0   # 40-second hook duration
):
    """
    Trims the master audio file so 0:00 of the new file aligns exactly with the start of the hook.
    Uses standard built-in Python wave module (no pip installs needed).
    """
    print("=" * 60)
    print("✂️ HOOK MANAGEMENT SYSTEM — AUDIO TRIMMER")
    print("=" * 60)
    
    if not os.path.exists(input_wav):
        print(f"❌ Input audio file not found: {input_wav}")
        print("Please verify the path to your master WAV file and try again.")
        return

    try:
        with wave.open(input_wav, 'rb') as infile:
            nchannels = infile.getnchannels()
            sampwidth = infile.getsampwidth()
            framerate = infile.getframerate()
            nframes = infile.getnframes()
            
            start_frame = int(start_sec * framerate)
            num_frames_to_read = int(duration_sec * framerate)
            
            if start_frame >= nframes:
                print(f"❌ Start time ({start_sec}s) exceeds total audio length!")
                return
                
            infile.setpos(start_frame)
            data = infile.readframes(num_frames_to_read)
            
        out_dir = os.path.dirname(os.path.abspath(output_wav))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            
        with wave.open(output_wav, 'wb') as outfile:
            outfile.setnchannels(nchannels)
            outfile.setsampwidth(sampwidth)
            outfile.setframerate(framerate)
            outfile.writeframes(data)
            
        print(f"✅ Trimmed audio successfully created!")
        print(f"  └─ Source File : {input_wav}")
        print(f"  └─ Cut Start   : {start_sec:.3f}s (02:44.281)")
        print(f"  └─ Duration    : {duration_sec:.1f}s")
        print(f"  └─ Output File : {output_wav}")
        print("\n0:00 of this new WAV file now aligns EXACTLY with the beginning of the hook!")
        
    except Exception as e:
        print(f"❌ Error trimming WAV file: {e}")

if __name__ == "__main__":
    trim_master_audio()
