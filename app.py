"""Ponto de entrada da aplicação.

Inicializa o QApplication, carrega o stylesheet global e exibe a janela principal.
"""

import sys
import faulthandler

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
