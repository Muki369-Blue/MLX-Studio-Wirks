# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)
ICON_PATH = ROOT / 'assets' / 'MLX-Moxy-Wirks.icns'
MLX_DATA, MLX_BINARIES, MLX_HIDDENIMPORTS = collect_all('mlx')
MLX_WHISPER_DATA, MLX_WHISPER_BINARIES, MLX_WHISPER_HIDDENIMPORTS = collect_all('mlx_whisper')


a = Analysis(
    ['desktop_entry.py'],
    pathex=[],
    binaries=[*MLX_BINARIES, *MLX_WHISPER_BINARIES],
    datas=[('static', 'static'), ('scripts', 'scripts'), *MLX_DATA, *MLX_WHISPER_DATA],
    hiddenimports=[*MLX_HIDDENIMPORTS, *MLX_WHISPER_HIDDENIMPORTS],
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
    name='MLX-Moxy-Wirks',
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
    icon=[str(ICON_PATH)],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MLX-Moxy-Wirks',
)
app = BUNDLE(
    coll,
    name='MLX-Moxy-Wirks.app',
    icon=str(ICON_PATH),
    bundle_identifier='com.muki369blue.mlxmoxywirks',
)
