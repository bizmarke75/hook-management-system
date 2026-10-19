import os
import subprocess
import sys

def build():
    print("="*60)
    print("  HMS Master GUI v2.6.0 - Standalone Executable Builder")
    print("="*60)
    
    # Check pyinstaller
    try:
        import PyInstaller
    except ImportError:
        print("[*] Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name=hms_master_gui",
        "hms_master_gui.py"
    ]
    
    print("[*] Running command:", " ".join(cmd))
    res = subprocess.call(cmd)
    
    if res == 0:
        exe_path = os.path.abspath(os.path.join("dist", "hms_master_gui.exe"))
        print("
" + "="*60)
        print(f" SUCCESS! Compiled executable ready at:
 {exe_path}")
        print("="*60)
    else:
        print("
 [ERROR] Build failed.")

if __name__ == "__main__":
    build()
