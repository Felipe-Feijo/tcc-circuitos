"""Ações de edição: deletar, copiar e colar."""

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtCore import Qt

def create_edit_actions(main_window):
    actions = {}

    actions["delete"] = QAction("Delete", main_window)
    actions["delete"].setShortcut(QKeySequence.StandardKey.Delete)
    actions["delete"].setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    actions["delete"].triggered.connect(
        main_window.delete_selected_items
    )

    actions["copy"] = QAction("Copy", main_window)
    actions["copy"].setShortcut(QKeySequence.StandardKey.Copy)  # Ctrl+C
    actions["copy"].setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    actions["copy"].triggered.connect(
        lambda: main_window.clipboard_manager.copy(main_window.scene)
    )

    actions["paste"] = QAction("Paste", main_window)
    actions["paste"].setShortcut(QKeySequence.StandardKey.Paste)  # Ctrl+V
    actions["paste"].setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)

    def _do_paste():
        from PyQt6.QtWidgets import QMessageBox
        from editor.mode import EditorMode
        if main_window.state.mode == EditorMode.SIMULATE:
            QMessageBox.information(
                main_window,
                "Simulação em execução",
                "Pare a simulação para editar o diagrama.",
            )
            return
        main_window.clipboard_manager.paste(main_window.scene, main_window.state)
        main_window.cancel_current_mode()

    actions["paste"].triggered.connect(_do_paste)

    actions["open_palette"] = QAction("Add", main_window)
    actions["open_palette"].setCheckable(True)
    actions["open_palette"].toggled.connect(
        main_window.palette_dock.setVisible
    )

    return actions