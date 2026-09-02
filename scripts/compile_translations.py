"""Compiles every Qt Linguist .ts source file under resources/i18n into a
sibling .qm binary catalog, via the pyside6-lrelease console script.

Dev-only tool: requires requirements-dev.txt (PySide6) to be installed.
Not used by the packaged app, which only ever reads the committed .qm files.

This script only COMPILES .ts -> .qm. It does not extract source strings --
that's a separate step, run manually:
    pylupdate6 app.py <every .py under main_window/ graphics/ persistence/
    editor/ circuit_generator/ simulation/> -ts resources/i18n/circuiteditor_en.ts
    (repeat with circuiteditor_pt_BR.ts -- this build's pylupdate6 only
    accepts one -ts output file per invocation)

GOTCHA when re-running pylupdate6: it only recognizes `self.tr(...)` and
`QCoreApplication.translate(...)` call sites via static source scanning. Any
`main_window.tr(...)` call made from a module-level function -- every
factory in main_window/actions/*.py, plus menus.py/toolbars.py/
node_palette_dock.py -- is invisible to it and will NOT get a <message>
entry, even though it resolves fine at runtime (PyQt derives a tr() call's
context from the bound object's runtime class, always "MainWindow" here).
After re-running pylupdate6, diff the regenerated circuiteditor_pt_BR.ts
against git HEAD and manually restore/add any missing <message> entries
under the <name>MainWindow</name> context with their translation, before
running this compile step. See main_window/actions/__init__.py's module
docstring and .superpowers/sdd/2026-09-01-language-switching/task-10-report.md
for the full list and how this was verified.

RELATED GOTCHA: a `self.tr(...)` call written in a base class, when run via
an inherited (unoverridden) method on a subclass instance, resolves its Qt
context to the *subclass's* runtime class at runtime, not the base class
pylupdate6 statically attributes it to -- so the catalog entry under the
base class's context never matches. Fix at the call site: use
`QCoreApplication.translate("<BaseClassName>", "...")` instead of
`self.tr(...)`. See main_window/actions/__init__.py's module docstring and
.superpowers/sdd/2026-09-01-language-switching/task-11-report.md for the
worked examples (NodeItem.extend_context_menu, PropertiesDialog).
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
