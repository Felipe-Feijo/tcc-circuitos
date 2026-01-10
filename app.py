# app.py
import sys
from PyQt6.QtWidgets import QApplication
from main_window.main_window import MainWindow

app = QApplication(sys.argv)
window = MainWindow()
window.resize(800, 600)
window.show()
sys.exit(app.exec())

