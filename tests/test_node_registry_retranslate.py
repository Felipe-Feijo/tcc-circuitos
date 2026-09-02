# tests/test_node_registry_retranslate.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from PyQt6.QtCore import QTranslator
from main_window.ui.palette.node_palette import NodePalette
from main_window.ui.registry.node_registry import register_nodes, retranslate_nodes

_QM_PATH = Path(__file__).parent.parent / "resources" / "i18n" / "circuiteditor_pt_BR.qm"


def _install_pt_br() -> QTranslator:
    translator = QTranslator()
    assert translator.load(str(_QM_PATH))
    app.installTranslator(translator)
    return translator


def test_register_nodes_stashes_the_originating_class_on_each_item():
    palette = NodePalette()
    palette.add_section("Hydraulic")
    register_nodes(palette, on_add_node=lambda node_desc: None)

    items = palette.sections["Hydraulic"]._items
    assert len(items) > 0
    for item in items:
        assert hasattr(item, "_node_cls")
        assert item._node_cls is not None


def test_retranslate_nodes_updates_names_to_portuguese():
    palette = NodePalette()
    palette.add_section("Hydraulic")
    register_nodes(palette, on_add_node=lambda node_desc: None)

    translator = _install_pt_br()
    try:
        retranslate_nodes(palette)
        names = {item.text_label.text() for item in palette.sections["Hydraulic"]._items}
        assert "Acumulador" in names
        assert "Reservatório" in names
    finally:
        app.removeTranslator(translator)


def test_retranslate_nodes_reverts_to_english_after_removing_translator():
    palette = NodePalette()
    palette.add_section("Hydraulic")
    register_nodes(palette, on_add_node=lambda node_desc: None)

    translator = _install_pt_br()
    retranslate_nodes(palette)
    app.removeTranslator(translator)
    retranslate_nodes(palette)

    names = {item.text_label.text() for item in palette.sections["Hydraulic"]._items}
    assert "Accumulator" in names
    assert "Reservoir" in names


def test_main_window_retranslates_component_names_on_language_switch():
    from main_window.main_window import MainWindow
    from main_window.language import language_manager

    window = MainWindow()
    try:
        names_by_item = {
            id(item): item.text_label
            for item in window.node_palette.sections["Hydraulic"]._items
        }
        assert any(label.text() == "Accumulator" for label in names_by_item.values())

        language_manager.apply_language(app, "pt_BR")
        window.retranslate_ui()
        assert any(label.text() == "Acumulador" for label in names_by_item.values())

        language_manager.apply_language(app, "en")
        window.retranslate_ui()
        assert any(label.text() == "Accumulator" for label in names_by_item.values())
    finally:
        window.close()
