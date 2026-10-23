"""
Hook Management System (HMS) - Executable Compiler
Version: 3.09 | 337 West Productions
"""
import subprocess
import sys
from pathlib import Path


def build():
    print("[BUILD] Compiling HMS Master GUI v3.09...")
    spec_file = Path("hms_master_gui.spec")
    
    if not spec_file.exists():
        print(f"[ERROR] Specification file not found: {spec_file.resolve()}")
        sys.exit(1)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_file)
    ]

    try:
        subprocess.run(cmd, check=True)
        print("[SUCCESS] Build succeeded. Output binary: dist/hms_master_gui/hms_master_gui.exe")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] PyInstaller failed with exit code {e.returncode}")
        sys.exit(e.returncode)


if __name__ == "__main__":
    build()