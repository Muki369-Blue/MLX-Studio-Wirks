# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)
ICON_PATH = ROOT / 'assets' / 'MLX-Moxy-Wirks.icns'
MLX_LM_DATA, MLX_LM_BINARIES, MLX_LM_HIDDENIMPORTS = collect_all('mlx_lm')
MLX_DATA, MLX_BINARIES, MLX_HIDDENIMPORTS = collect_all('mlx')
MLX_WHISPER_DATA, MLX_WHISPER_BINARIES, MLX_WHISPER_HIDDENIMPORTS = collect_all('mlx_whisper')
WATCHDOG_DATA, WATCHDOG_BINARIES, WATCHDOG_HIDDENIMPORTS = collect_all('watchdog')
# XTTS v2 neural voice cloning + transitive deps. Adds ~3 GB to bundle.
TTS_DATA, TTS_BINARIES, TTS_HIDDENIMPORTS = collect_all('TTS')
TORCH_DATA, TORCH_BINARIES, TORCH_HIDDENIMPORTS = collect_all('torch')
TORCHAUDIO_DATA, TORCHAUDIO_BINARIES, TORCHAUDIO_HIDDENIMPORTS = collect_all('torchaudio')
TRANSFORMERS_DATA, TRANSFORMERS_BINARIES, TRANSFORMERS_HIDDENIMPORTS = collect_all('transformers')
LIBROSA_DATA, LIBROSA_BINARIES, LIBROSA_HIDDENIMPORTS = collect_all('librosa')
SOUNDFILE_DATA, SOUNDFILE_BINARIES, SOUNDFILE_HIDDENIMPORTS = collect_all('soundfile')
# coqui-tts transitive deps PyInstaller misses without an explicit collect_all.
# Import names: ko_speech_tools, coqpit, trainer (PyPI: coqui-tts-trainer).
KO_DATA, KO_BINARIES, KO_HIDDENIMPORTS = collect_all('ko_speech_tools')
COQPIT_DATA, COQPIT_BINARIES, COQPIT_HIDDENIMPORTS = collect_all('coqpit')
TRAINER_DATA, TRAINER_BINARIES, TRAINER_HIDDENIMPORTS = collect_all('trainer')
# FLUX.1 image generation
MFLUX_DATA, MFLUX_BINARIES, MFLUX_HIDDENIMPORTS = collect_all('mflux')


a = Analysis(
    ['desktop_entry.py'],
    pathex=[],
    # Coqui-TTS / coqpit / trainer use inspect.getsource() at runtime to
    # parse config classes — fails on .pyc-only bundles. Force PyInstaller
    # to ship raw .py source for the whole TTS dependency chain.
    module_collection_mode={
        'TTS': 'py',
        'coqpit': 'py',
        'trainer': 'py',
        'coqui_tts_trainer': 'py',
        'ko_speech_tools': 'py',
        # inflect & typeguard call inspect.getsource on their @typechecked
        # decorated classes during module init — must ship as .py source.
        'inflect': 'py',
        'typeguard': 'py',
        # Belt-and-braces for other coqui-tts deps that introspect.
        'pysbd': 'py',
        'num2words': 'py',
        'anyascii': 'py',
    },
    binaries=[
        *MLX_LM_BINARIES, *MLX_BINARIES, *MLX_WHISPER_BINARIES, *WATCHDOG_BINARIES,
        *TTS_BINARIES, *TORCH_BINARIES, *TORCHAUDIO_BINARIES,
        *TRANSFORMERS_BINARIES, *LIBROSA_BINARIES, *SOUNDFILE_BINARIES,
        *KO_BINARIES, *COQPIT_BINARIES, *TRAINER_BINARIES, *MFLUX_BINARIES,
    ],
    datas=[
        ('static', 'static'), ('scripts', 'scripts'), ('persona', 'persona'),
        *MLX_LM_DATA, *MLX_DATA, *MLX_WHISPER_DATA, *WATCHDOG_DATA,
        *TTS_DATA, *TORCH_DATA, *TORCHAUDIO_DATA,
        *TRANSFORMERS_DATA, *LIBROSA_DATA, *SOUNDFILE_DATA,
        *KO_DATA, *COQPIT_DATA, *TRAINER_DATA, *MFLUX_DATA,
    ],
    hiddenimports=[
        *MLX_LM_HIDDENIMPORTS, *MLX_HIDDENIMPORTS, *MLX_WHISPER_HIDDENIMPORTS,
        *WATCHDOG_HIDDENIMPORTS, 'watchdog.observers', 'watchdog.events', 'difflib',
        *TTS_HIDDENIMPORTS, *TORCH_HIDDENIMPORTS, *TORCHAUDIO_HIDDENIMPORTS,
        *TRANSFORMERS_HIDDENIMPORTS, *LIBROSA_HIDDENIMPORTS, *SOUNDFILE_HIDDENIMPORTS,
        *KO_HIDDENIMPORTS, *COQPIT_HIDDENIMPORTS, *TRAINER_HIDDENIMPORTS,
        *MFLUX_HIDDENIMPORTS,
        'TTS.api', 'TTS.tts.models.xtts', 'TTS.tts.configs.xtts_config',
        'ko_speech_tools.data', 'ko_speech_tools.g2p', 'ko_speech_tools.romanize',
        'mflux.models.flux.variants.txt2img.flux',
    ],
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
