"""Ação que abre o diálogo de geração automática de circuito."""

from PyQt6.QtGui import QAction
from main_window.ui.circuit_generator_dialog import CircuitGeneratorDialog
from circuit_generator.circuit_generator import generate_and_load
from editor.mode import EditorMode


def create_generator_actions(main_window) -> dict:
    actions = {}

    act = QAction("Novo a partir de Sequência...", main_window)
    act.setShortcut("Ctrl+G")
    act.triggered.connect(lambda: _open_dialog(main_window))
    actions["new_from_sequence"] = act

    return actions


def _open_dialog(main_window):
    dialog = CircuitGeneratorDialog(main_window)
    if dialog.exec():
        generate_and_load(
            dialog.sequence,
            dialog.method,
            dialog.sub_type,
            main_window.scene,
            main_window.state,
        )
        main_window.set_mode(EditorMode.SELECT)
        main_window.zoom_to_contents()