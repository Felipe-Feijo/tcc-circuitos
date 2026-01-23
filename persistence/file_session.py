from pathlib import Path
from PyQt6.QtWidgets import QFileDialog, QMessageBox


class SceneFileSession:
    """
    Manages scene file lifecycle:
    - open
    - save
    - save as

    UI-aware, but persistence-agnostic.
    """

    def __init__(self, scene, parent_window):
        self.scene = scene
        self.parent = parent_window
        self.current_file: str | None = None

    # ----------------------
    # Public API
    # ----------------------

    def save(self):
        if not self.current_file:
            return self.save_as()

        self._save_to_path(self.current_file)

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self.parent,
            "Salvar cena",
            "",
            "Scene Files (*.json)"
        )

        if not path:
            return

        if not path.endswith(".json"):
            path += ".json"

        self._save_to_path(path)

    def open(self):
        path, _ = QFileDialog.getOpenFileName(
            self.parent,
            "Abrir cena",
            "",
            "Scene Files (*.json)"
        )

        if not path:
            return

        try:
            from persistence.serializer import load_from_file

            load_from_file(self.scene, path, self.parent)
            self.current_file = path
            self._update_window_title()

        except Exception as e:
            QMessageBox.critical(
                self.parent,
                "Erro ao abrir",
                str(e)
            )

    # ----------------------
    # Internal helpers
    # ----------------------

    def _save_to_path(self, path: str):
        try:
            from persistence.serializer import save_to_file

            save_to_file(self.scene, path)
            self.current_file = path
            self._update_window_title()

        except Exception as e:
            QMessageBox.critical(
                self.parent,
                "Erro ao salvar",
                str(e)
            )

    def _update_window_title(self):
        name = Path(self.current_file).name
        self.parent.setWindowTitle(f"Simulador – {name}")
