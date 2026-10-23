# -*- mode: python ; coding: utf-8 -*-
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
