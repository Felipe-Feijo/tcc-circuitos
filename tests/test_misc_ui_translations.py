"""Field example placeholders, scene file filter and font-size dialog follow
the UI language."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication, QGraphicsScene

app = QApplication.instance() or QApplication([])

from main_window.language import language_manager
from main_window import settings
from graphics.items.base.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder
from graphics.items.base.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve
from persistence.file_session import SceneFileSession


@pytest.fixture
def pt_br():
    language_manager.apply_language(app, "pt_BR")
    yield
    language_manager.apply_language(app, "en")


def _bore_placeholder():
    cyl = DoubleActingCylinder(domain="hydraulic")
    dialog = cyl.build_properties_dialog()
    try:
        return dialog._field_bore.placeholderText()
    finally:
        dialog.close()


def test_example_placeholder_en():
    assert _bore_placeholder() == "e.g. 0.05"


def test_example_placeholder_pt_br(pt_br):
    assert _bore_placeholder() == "ex.: 0.05"


def test_default_placeholder_pt_br(pt_br):
    valve = PilotOperatedReliefValve(domain="hydraulic")
    dialog = valve.build_properties_dialog()
    try:
        assert dialog._field_p_vent.placeholderText() == "3e5  (= 3 bar, padrão)"
    finally:
        dialog.close()


def test_scene_file_filter_pt_br(pt_br):
    session = SceneFileSession(QGraphicsScene(), None)
    with patch("persistence.file_session.QFileDialog.getOpenFileName", return_value=("", "")) as dlg:
        session.open()
    assert dlg.call_args.args[3] == "Arquivos de Cena (*.json)"


def test_font_size_dialog_pt_br(pt_br):
    with patch("main_window.settings.QInputDialog.getInt", return_value=(11, False)) as dlg:
        settings.prompt_and_apply_font_size(None)
    assert dlg.call_args.args[1:3] == ("Tamanho da Fonte", "Tamanho (pt):")
