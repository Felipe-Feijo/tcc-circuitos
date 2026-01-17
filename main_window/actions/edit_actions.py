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

    actions["open_palette"] = QAction("Add", main_window)
    actions["open_palette"].setCheckable(True)
    actions["open_palette"].toggled.connect(
        main_window.palette_dock.setVisible
    )

    return actions