import os
import subprocess
import sys

def get_hms_rev():
    """Extract HMS_REV dynamically from hms_master_gui.py."""
    gui_file = "hms_master_gui.py"
    if os.path.exists(gui_file):
        with open(gui_file, "r", encoding="utf-8") as f:
            for line in f:
                if "HMS_REV" in line and "=" in line:
                    parts = line.split("=")
                    rev = parts[1].strip().strip('"').strip("'")
                    if rev:
                        return rev
    return "v2.8.0"

def build():
    rev = get_hms_rev()
    print("=" * 60)
    print(f"  HMS Master GUI {rev} - Standalone Executable Builder")
    print("=" * 60)
    
    # Check PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("[*] PyInstaller not found. Installing pyinstaller...")
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
        print("\n" + "=" * 60)
        print(f" SUCCESS! Compiled executable ready at:\n {exe_path}")
        print("=" * 60)
    else:
        print("\n [ERROR] Build failed. Check error messages above.")

if __name__ == "__main__":
    build()
