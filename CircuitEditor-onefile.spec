# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller CircuitEditor-onefile.spec
#
# Mesmo empacotamento de CircuitEditor.spec, mas em modo onefile: gera um
# unico CircuitEditor.exe (mais facil de mandar pra alguem), que se
# descompacta pra uma pasta temporaria (%TEMP%\_MEIxxxxxx, resolvida via
# sys._MEIPASS -- ver paths.get_base_dir()) toda vez que roda. Por isso
# inicia mais devagar que o modo onedir e pode disparar falso positivo de
# antivirus com mais frequencia.
#
# `graphics`, `circuit_generator`, `simulation`, `editor` e `persistence`
# sao incluidos tambem como dados brutos (alem de compilados) porque
# circuit_generator/sprite_metrics.py le .py de graphics/ como texto via
# regex em runtime, o node_registry descobre nos de graphics/ dinamicamente
# via os.walk + importlib (o que faz simulation/editor/persistence serem
# alcancados so em runtime, fora do grafo estatico de imports), e os
# *_layout_config.json de circuit_generator/ nao sao coletados
# automaticamente pelo PyInstaller.

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
    a.binaries,
    a.datas,
    [],
    exclude_binaries=False,
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
