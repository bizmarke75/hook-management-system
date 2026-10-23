"""
337 West Productions - Hook Management System (HMS) v3.09
Module: inline_patcher.py
Purpose: Hardens PyInstaller hooks for Python 3.14, resolves hook collisions,
         compiles hms_master_gui.exe, and packages the portable release ZIP.
Standard: modular-python-builder
"""

import sys
import shutil
import subprocess
import traceback
from pathlib import Path

SPEC_CONTENT = """# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = [
    'soundfile',
    '_soundfile_data',
    'librosa',
    'scipy',
    'scipy.signal',
    'scipy.fft',
    'scipy.special',
    'numpy',
    'lazy_loader',
    'tkinter',
    'hms_safety',
    'hms_manifest',
    'hms_metadata',
    'hms_v31_patcher',
]

for pkg in ['soundfile', 'librosa']:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:
        print(f"[WARN] Skipped collect_all for {pkg}: {exc}")

block_cipher = None

a = Analysis(
    ['hms_master_gui.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],  # Must remain empty to avoid ExcludedModule collision in PyInstaller hook-distutils
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Strip broken Python 3.14 pkg_resources bootstrap runtime hook
a.scripts = [s for s in a.scripts if 'pkgres' not in str(s).lower()]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='hms_master_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Keeps console attached for live SafeLogRedirector stream
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='hms_master_gui',
)
"""

def patch_pyinstaller_setuptools_hook() -> bool:
    """
    Surgically patches PyInstaller's internal hook-setuptools.py in site-packages
    to prevent TypeError when setuptools_info.version evaluates to None on Python 3.14.
    """
    print("[RUN] Checking PyInstaller hook-setuptools.py for Python 3.14 compatibility...")
    try:
        import PyInstaller
        pyi_dir = Path(PyInstaller.__file__).parent
        hook_path = pyi_dir / "hooks" / "hook-setuptools.py"
        if not hook_path.exists():
            print(f"[INFO] hook-setuptools.py not found at {hook_path}, skipping.")
            return True

        content = hook_path.read_text(encoding="utf-8")
        target = "if setuptools_info.version < (71, 0):"
        replacement = "if getattr(setuptools_info, 'version', None) is not None and setuptools_info.version < (71, 0):"

        if target in content:
            content = content.replace(target, replacement)
            hook_path.write_text(content, encoding="utf-8")
            print("[SUCCESS] Patched hook-setuptools.py for Python 3.14.")
        else:
            print("[INFO] hook-setuptools.py already up to date.")
        return True
    except Exception as e:
        print(f"[WARN] Could not patch hook-setuptools.py: {e}")
        return True

def write_hardened_spec(spec_path: Path) -> bool:
    """Writes the sanitized PyInstaller spec file."""
    print(f"[RUN] Writing hardened spec to: {spec_path.name}")
    try:
        if spec_path.exists():
            backup_path = spec_path.with_suffix(".spec.bak")
            shutil.copy2(spec_path, backup_path)
            print(f"[INFO] Backup saved to: {backup_path.name}")
        spec_path.write_text(SPEC_CONTENT, encoding="utf-8")
        print(f"[SUCCESS] Spec configuration locked: {spec_path.name}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed writing spec file: {str(e)}")
        print(traceback.format_exc())
        return False

def clean_build_artifacts(root_dir: Path) -> None:
    """Removes cached build folders to prevent stale hook injection."""
    print("[RUN] Purging temporary build caches...")
    build_dir = root_dir / "build"
    if build_dir.exists():
        try:
            shutil.rmtree(build_dir)
            print(f"[INFO] Removed stale cache: {build_dir}")
        except Exception as e:
            print(f"[WARN] Could not purge build directory: {e}")

def compile_binary(spec_path: Path) -> bool:
    """Executes PyInstaller using the hardened spec configuration."""
    print("[RUN] Executing clean PyInstaller compilation...")
    cmd = [sys.executable, "-m", "PyInstaller", str(spec_path), "--noconfirm", "--clean"]
    try:
        subprocess.run(cmd, check=True, text=True)
        print("[SUCCESS] PyInstaller compilation finished with exit code 0.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] PyInstaller failed with exit code: {e.returncode}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected execution failure: {str(e)}")
        print(traceback.format_exc())
        return False

def audit_distribution(root_dir: Path) -> bool:
    """Audits the compiled binary and bundles the portable release archive."""
    print("[RUN] Auditing compiled distribution assets...")
    dist_dir = root_dir / "dist" / "hms_master_gui"
    exe_path = dist_dir / "hms_master_gui.exe"
    
    if not exe_path.exists():
        print(f"[ERROR] Target binary missing: {exe_path}")
        return False
        
    print(f"[SUCCESS] Target binary confirmed: {exe_path}")
    
    # Audit libsndfile presence
    sndfile_dlls = list(dist_dir.rglob("*sndfile*"))
    if sndfile_dlls:
        print(f"[INFO] SoundFile backend dynamic library detected: {sndfile_dlls[0].name}")
    else:
        print("[WARN] libsndfile DLL not explicitly matched in dist tree.")
        
    # Generate portable release ZIP
    zip_dest = root_dir / "dist" / "HMS_v3.09_Portable"
    print(f"[RUN] Packaging {dist_dir} into {zip_dest}.zip...")
    try:
        shutil.make_archive(str(zip_dest), 'zip', str(dist_dir))
        zip_file = root_dir / "dist" / "HMS_v3.09_Portable.zip"
        size_mb = zip_file.stat().st_size / (1024 * 1024)
        print(f"[SUCCESS] Portable distribution archive ready: {zip_file.name} ({size_mb:.2f} MB)")
    except Exception as e:
        print(f"[WARN] Automatic zip creation failed: {e}")
        
    return True

def main():
    print("=======================================================")
    print("HMS v3.09 INLINE PATCHER & COMPILER")
    print("=======================================================")
    root_dir = Path.cwd().resolve()
    spec_path = root_dir / "hms_master_gui.spec"

    if not (root_dir / "hms_master_gui.py").exists():
        print(f"[ERROR] hms_master_gui.py not found in current directory: {root_dir}")
        sys.exit(1)

    # 1. Patch PyInstaller site-packages hook
    patch_pyinstaller_setuptools_hook()

    # 2. Write Hardened Spec (excludes=[])
    if not write_hardened_spec(spec_path):
        sys.exit(1)

    # 3. Clean Cache
    clean_build_artifacts(root_dir)

    # 4. Compile
    if not compile_binary(spec_path):
        sys.exit(1)

    # 5. Audit & Package Release Archive
    if audit_distribution(root_dir):
        print("\n=======================================================")
        print("[SUCCESS] HMS v3.09 BUILD & PACKAGING COMPLETE")
        print(f"Binary: dist/hms_master_gui/hms_master_gui.exe")
        print(f"Archive: dist/HMS_v3.09_Portable.zip")
        print("=======================================================\n")
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()