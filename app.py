"""Ponto de entrada da aplicação.

Inicializa o QApplication, carrega o stylesheet global e exibe a janela principal.
"""

import os
import sys
import faulthandler
from pathlib import Path

from paths import get_base_dir

os.chdir(get_base_dir())

if sys.stderr is None:
    # Build "windowed" (sem console): sys.stdout/stderr vêm None, e
    # faulthandler.enable() exige um stream real -- redireciona pra um
    # arquivo de log ao lado do executável em vez de deixar crashar.
    log_path = Path(sys.executable).parent / "circuit_editor.log"
    sys.stdout = sys.stderr = open(log_path, "w", encoding="utf-8")

from PyQt6.QtWidgets import QApplication
from main_window.main_window import MainWindow

faulthandler.enable()

app = QApplication(sys.argv)

with open("resources/styles.qss", "r") as f:
    app.setStyleSheet(f.read())

window = MainWindow()
window.resize(800, 600)
window.show()

sys.exit(app.exec())
