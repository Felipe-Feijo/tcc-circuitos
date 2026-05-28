"""Edit actions: delete, copy, paste, undo, redo, and rotate."""

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

    # ── Undo / Redo ──────────────────────────────────────────────────────────
    # Note: Ctrl+Z is used by the simulation (step_back) when SIMULATE mode
    # is active. These actions are enabled only outside simulation;
    # the toggle logic is handled in MainWindow.update_simulation_actions().

    actions["undo"] = QAction("Undo", main_window)
    actions["undo"].setShortcut(QKeySequence.StandardKey.Undo)  # Ctrl+Z
    actions["undo"].setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    actions["undo"].triggered.connect(
        lambda: main_window.state.undo_stack.undo()
    )

    actions["redo"] = QAction("Redo", main_window)
    actions["redo"].setShortcut(QKeySequence.StandardKey.Redo)  # Ctrl+Shift+Z
    actions["redo"].setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    actions["redo"].triggered.connect(
        lambda: main_window.state.undo_stack.redo()
    )

    # ── Rotate ───────────────────────────────────────────────────────────────
    actions["rotate"] = QAction("Rotate 90°", main_window)
    actions["rotate"].setShortcut(QKeySequence("R"))
    actions["rotate"].setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    actions["rotate"].setToolTip("Rotate selected component 90° clockwise (R)")

    def _do_rotate():
        from editor.mode import EditorMode
        from graphics.items.base.nodes.node_item import NodeItem

        if main_window.state.mode == EditorMode.SIMULATE:
            return

        scene = main_window.scene
        selected_nodes = [
            item for item in scene.selectedItems()
            if isinstance(item, NodeItem)
        ]
        if not selected_nodes:
            return

        undo_stack = main_window.state.undo_stack
        before = undo_stack.snapshot(scene)

        for node in selected_nodes:
            node.rotate(90)

        undo_stack.push_snapshot(
            scene, main_window.state, before, "Rotate component"
        )

    actions["rotate"].triggered.connect(_do_rotate)

    return actions
