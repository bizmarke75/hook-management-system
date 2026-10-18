import os
import subprocess
import sys

def build():
    print("=" * 60)
    print("  HMS Master GUI v2.8.0 - Standalone Executable Builder")
    print("=" * 60)

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
    ]

    if os.path.exists("337west_icon.ico"):
        cmd.extend([
            "--icon=337west_icon.ico",
            "--add-data=337west_icon.ico;."
        ])

    cmd.append("hms_master_gui.py")

    print("[*] Running command:", " ".join(cmd))
    res = subprocess.call(cmd)

    if res == 0:
        exe_path = os.path.abspath(os.path.join("dist", "hms_master_gui.exe"))
        print("\n" + "=" * 60)
        print(f" SUCCESS! Compiled executable ready at:\n {exe_path}")
        print("=" * 60)
    else:
        print("\n [ERROR] Build failed.")
        sys.exit(res)

if __name__ == "__main__":
    build()
