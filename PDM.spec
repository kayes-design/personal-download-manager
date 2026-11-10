# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

imageio_datas = collect_data_files('imageio_ffmpeg')

a = Analysis(
    ['pdm/main.py'],
    pathex=[],
    binaries=[],
    datas=[('pdm', 'pdm'), ('icon.ico', '.')] + imageio_datas,
    hiddenimports=['imageio_ffmpeg', 'yt_dlp', 'yt_dlp.extractor', 'socksio'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PDM',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PDM',
)
