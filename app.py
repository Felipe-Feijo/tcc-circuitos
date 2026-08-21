"""Application entry point.

Initializes the QApplication, loads the global stylesheet and shows the main window.
"""

import os
import sys
import faulthandler
from pathlib import Path

from paths import get_base_dir

os.chdir(get_base_dir())

if sys.stderr is None:
    # Windowed build (no console): sys.stdout/stderr come back None, and
    # faulthandler.enable() requires a real stream -- redirect to a log
    # file next to the executable instead of letting it crash.
    log_path = Path(sys.executable).parent / "circuit_editor.log"
    sys.stdout = sys.stderr = open(log_path, "w", encoding="utf-8")

from PyQt6.QtWidgets import QApplication
from main_window.main_window import MainWindow
from main_window import settings

faulthandler.enable()

app = QApplication(sys.argv)
settings.apply_font_from_settings(app)

window = MainWindow()
window.resize(800, 600)
window.show()

sys.exit(app.exec())
