import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from main_window.ui.palette.node_palette import NodePalette


def test_add_section_keeps_canonical_key_separate_from_translated_title():
    palette = NodePalette()
    palette.add_section("Pneumatic", "Pneumático")

    assert "Pneumatic" in palette.sections          # lookup key unchanged
    assert palette.sections["Pneumatic"].header.text() == "▾ Pneumático"  # displayed title translated


def test_add_section_defaults_title_to_key_when_not_given():
    palette = NodePalette()
    palette.add_section("Electric")

    assert palette.sections["Electric"].header.text() == "▾ Electric"


def test_retranslate_updates_section_titles_and_tier_tooltips():
    palette = NodePalette()
    palette.add_section("Hydraulic", "Hydraulic")

    palette.retranslate_ui({"Hydraulic": "Hidráulico"})

    assert palette.sections["Hydraulic"].header.text() == "▾ Hidráulico"
    assert palette.tier_buttons["small"].toolTip() == "Small"


def test_tier_button_labels_are_the_first_letter_of_the_tooltip_word():
    palette = NodePalette()

    assert palette.tier_buttons["small"].text() == "S"
    assert palette.tier_buttons["medium"].text() == "M"
    assert palette.tier_buttons["large"].text() == "L"


def test_retranslate_updates_tier_button_labels_to_portuguese():
    from PyQt6.QtCore import QTranslator
    from pathlib import Path
    from PyQt6.QtWidgets import QApplication as _QApp

    translator = QTranslator()
    qm_path = Path(__file__).parent.parent / "resources" / "i18n" / "circuiteditor_pt_BR.qm"
    assert translator.load(str(qm_path))
    _QApp.instance().installTranslator(translator)
    try:
        palette = NodePalette()
        palette.retranslate_ui({})

        assert palette.tier_buttons["small"].text() == "P"
        assert palette.tier_buttons["medium"].text() == "M"
        assert palette.tier_buttons["large"].text() == "G"
    finally:
        _QApp.instance().removeTranslator(translator)


def test_title_label_is_stored_and_set_on_construction():
    palette = NodePalette()

    assert palette.title_label.text() == "Nodes"


def test_retranslate_updates_title_label():
    palette = NodePalette()
    palette.title_label.setText("stale")

    palette.retranslate_ui({})

    assert palette.title_label.text() == "Nodes"
