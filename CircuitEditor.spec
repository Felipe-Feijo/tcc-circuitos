# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller CircuitEditor.spec
#
# Empacota o editor de circuitos (PyQt6 + matplotlib + numpy + scipy) num
# diretorio standalone (modo onedir) que roda sem Python instalado.
#
# `graphics` e `circuit_generator` sao incluidos tambem como dados brutos
# (alem de compilados) porque circuit_generator/sprite_metrics.py le alguns
# .py de graphics/ como texto via regex em runtime (fonte unica de verdade
# para spacing/offsets), e os *_layout_config.json de circuit_generator/ nao
# sao coletados automaticamente pelo PyInstaller.

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    # `resources` also carries resources/i18n/*.qm (Qt Linguist translation
    # catalogs) -- bundled automatically as part of the whole-directory copy,
    # no separate datas entry needed.
    datas=[
        ('resources', 'resources'),
        ('graphics', 'graphics'),
        ('circuit_generator', 'circuit_generator'),
        ('simulation', 'simulation'),
        ('editor', 'editor'),
        ('persistence', 'persistence'),
        *collect_data_files('imageio_ffmpeg'),
        # imageio/__init__.py reads its own version via
        # importlib.metadata.version("imageio") at import time; PyInstaller's
        # bundled hook-imageio.py only collects data files and plugin
        # submodules, not the dist-info metadata that call needs, so without
        # this the frozen app fails at startup with
        # importlib.metadata.PackageNotFoundError.
        *copy_metadata('imageio'),
    ],
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
    name='CircuitEditor',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CircuitEditor',
)
