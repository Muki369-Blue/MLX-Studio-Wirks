# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path(SPECPATH)
ICON_PATH = ROOT / 'assets' / 'MLX-Moxy-Wirks.icns'


a = Analysis(
    ['desktop_entry.py'],
    pathex=[],
    binaries=[],
    datas=[('static', 'static'), ('scripts', 'scripts')],
    hiddenimports=[],
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
