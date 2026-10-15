import os
import sys
import subprocess

def build():
    print("=" * 60)
    print("HMS Master GUI Executable Builder (PyInstaller v2.6.0)")
    print("=" * 60)
    
    # Ensure pyinstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    cmd = [
        "pyinstaller",
        "--noconsole",
        "--onefile",
        "--icon=337west_icon.ico",
        "--name=hms_master_gui",
        "hms_master_gui.py"
    ]
    
    print("\nExecuting build command:")
    print(" ".join(cmd))
    print("-" * 60)
    
    res = subprocess.run(cmd)
    
    if res.returncode == 0:
        exe_path = os.path.join("dist", "hms_master_gui.exe")
        print("\n" + "=" * 60)
        print(f"✅ SUCCESS! Standalone executable created with 337West Icon at:\n   {os.path.abspath(exe_path)}")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ BUILD FAILED! Check error output above.")
        print("=" * 60)

if __name__ == "__main__":
    build()
