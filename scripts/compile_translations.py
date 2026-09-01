"""Compiles every Qt Linguist .ts source file under resources/i18n into a
sibling .qm binary catalog, via the pyside6-lrelease console script.

Dev-only tool: requires requirements-dev.txt (PySide6) to be installed.
Not used by the packaged app, which only ever reads the committed .qm files.
"""

import shutil
import subprocess
import sys
from pathlib import Path

_I18N_DIR = Path(__file__).resolve().parent.parent / "resources" / "i18n"


def _lrelease_executable() -> str:
    exe = shutil.which("pyside6-lrelease")
    if not exe:
        raise FileNotFoundError(
            "pyside6-lrelease not found on PATH. Install dev dependencies: "
            "pip install -r requirements-dev.txt"
        )
    return exe


def compile_all(i18n_dir: Path = _I18N_DIR) -> list[Path]:
    """Compiles every *.ts file in i18n_dir to a sibling *.qm. Returns the
    list of .qm paths written, in the same order as the .ts files found."""
    lrelease = _lrelease_executable()
    produced = []
    for ts_path in sorted(i18n_dir.glob("*.ts")):
        qm_path = ts_path.with_suffix(".qm")
        subprocess.run(
            [lrelease, str(ts_path), "-qm", str(qm_path)],
            check=True,
            capture_output=True,
        )
        produced.append(qm_path)
    return produced


if __name__ == "__main__":
    written = compile_all()
    for path in written:
        print(f"compiled {path}")
    sys.exit(0)
