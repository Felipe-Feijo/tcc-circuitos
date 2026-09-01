"""Manages the open file session: current path, dialogs and window title."""

from pathlib import Path
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QFileDialog, QMessageBox


class SceneFileSession:
    """Controls the lifecycle of the open scene file.

    Responsibilities:
    - Open a file via dialog and load the scene.
    - Save to the current file or open a "save as" dialog.
    - Update the window title with the file name.

    UI-aware (uses QFileDialog and QMessageBox), but agnostic to the
    persistence format -- delegates reading/writing to the serializer module.

    Args:
        scene: QGraphicsScene managed by the session.
        parent_window: Main window used as parent for the Qt dialogs.
        editor_state: EditorState passed to the deserializer; if None,
            tries to read parent_window.state.
    """

    def __init__(self, scene, parent_window, editor_state=None):
        self.scene = scene
        self.parent = parent_window
        self.editor_state = editor_state or getattr(parent_window, "state", None)
        self.current_file: str | None = None

    # Public API

    def save(self) -> None:
        """Saves to the current file, or opens a dialog if no file is open."""
        if not self.current_file:
            return self.save_as()
        self._save_to_path(self.current_file)

    def save_as(self) -> None:
        """Opens the "save as" dialog and writes the scene to the chosen path."""
        path, _ = QFileDialog.getSaveFileName(
            self.parent,
            QCoreApplication.translate("SceneFileSession", "Save scene"),
            "",
            "Scene Files (*.json)",
        )
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        self._save_to_path(path)

    def open(self) -> None:
        """Opens the file dialog and loads the scene from the chosen JSON."""
        path, _ = QFileDialog.getOpenFileName(
            self.parent,
            QCoreApplication.translate("SceneFileSession", "Open scene"),
            "",
            "Scene Files (*.json)",
        )
        if not path:
            return
        try:
            from persistence.serializer import load_from_file
            load_from_file(self.scene, path, self.editor_state)
            self.current_file = path
            self._update_window_title()
        except Exception as e:
            QMessageBox.critical(
                self.parent,
                QCoreApplication.translate("SceneFileSession", "Error opening file"),
                str(e),
            )

    # Internal methods

    def _save_to_path(self, path: str) -> None:
        """Writes the scene to the given path and updates the window title.

        Args:
            path: Absolute path of the destination file.
        """
        try:
            from persistence.serializer import save_to_file
            save_to_file(self.scene, path)
            self.current_file = path
            self._update_window_title()
        except Exception as e:
            QMessageBox.critical(
                self.parent,
                QCoreApplication.translate("SceneFileSession", "Error saving file"),
                str(e),
            )

    def _update_window_title(self) -> None:
        """Updates the main window title with the current file name."""
        name = Path(self.current_file).name
        self.parent.setWindowTitle(
            QCoreApplication.translate("SceneFileSession", "Circuit Editor – {0}").format(name)
        )
