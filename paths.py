"""Resolução do diretório base do projeto.

Funciona tanto rodando via `python app.py` quanto em um build congelado
pelo PyInstaller (onde `__file__` de módulos compilados não aponta para
um arquivo .py real em disco).
"""

import sys
from pathlib import Path


def get_base_dir() -> Path:
    # `_MEIPASS` é definido pelo PyInstaller tanto em builds onefile quanto
    # onedir, apontando para onde os dados (--add-data) foram extraídos.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent
