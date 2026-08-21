"""Resolution of the project's base directory.

Works both when running via `python app.py` and in a build frozen by
PyInstaller (where `__file__` of compiled modules doesn't point to a
real .py file on disk).
"""

import sys
from pathlib import Path


def get_base_dir() -> Path:
    # `_MEIPASS` is set by PyInstaller in both onefile and onedir builds,
    # pointing to where the data (--add-data) was extracted.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent
