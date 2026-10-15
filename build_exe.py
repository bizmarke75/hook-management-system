import os
import sys
import subprocess

# Force UTF-8 output encoding for Windows runners
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def main():
    print("============================================================")
    print(" Hook Management System (HMS) - PyInstaller Build Engine ")
    print("============================================================")
    
    script_path = "hms_master_gui.py"
    icon_path = "337west_icon.ico"
    app_name = "hms_master_gui"
    
    if not os.path.exists(script_path):
        print(f"Error: {script_path} not found in current directory.")
        sys.exit(1)
        
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        f"--name={app_name}",
        script_path
    ]
    
    if os.path.exists(icon_path):
        cmd.insert(4, f"--icon={icon_path}")
        print(f"Using icon: {icon_path}")
    else:
        print("Warning: 337west_icon.ico not found. Building with default icon.")
        
    print(f"Executing build command:\n{' '.join(cmd)}")
    print("------------------------------------------------------------")
    
    try:
        subprocess.run(cmd, check=True)
        print("------------------------------------------------------------")
        print("[SUCCESS] BUILD COMPLETE!")
        print(f"Executable generated at: {os.path.abspath(os.path.join('dist', f'{app_name}.exe'))}")
        print("============================================================")
    except subprocess.CalledProcessError as e:
        print("------------------------------------------------------------")
        print("[FAILED] BUILD FAILED! Check error output above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
