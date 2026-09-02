# tests/test_language_persists_across_sessions.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from PyQt6.QtCore import QSettings
from main_window.language import apply_language, get_language, DEFAULT_LANGUAGE


def test_language_choice_survives_a_new_settings_read():
    settings = QSettings("tcc-circuitos-tests", "PersistenceIntegrationTest")
    settings.clear()

    apply_language(app, "pt_BR", settings)

    # Simulate a fresh app start reading the same underlying QSettings scope.
    reread = QSettings("tcc-circuitos-tests", "PersistenceIntegrationTest")
    assert get_language(reread) == "pt_BR"

    apply_language(app, DEFAULT_LANGUAGE, settings)  # leave state clean
