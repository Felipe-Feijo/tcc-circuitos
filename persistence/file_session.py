"""Gerencia a sessão de arquivo aberta: caminho atual, diálogos e título da janela."""

from pathlib import Path
from PyQt6.QtWidgets import QFileDialog, QMessageBox


class SceneFileSession:
    """Controla o ciclo de vida do arquivo de cena aberto.

    Responsabilidades:
    - Abrir um arquivo via diálogo e carregar a cena.
    - Salvar no arquivo atual ou abrir diálogo de "salvar como".
    - Atualizar o título da janela com o nome do arquivo.

    Ciente da UI (usa QFileDialog e QMessageBox), mas agnóstica ao formato
    de persistência — delega a leitura/escrita ao módulo serializer.

    Args:
        scene: QGraphicsScene gerenciada pela sessão.
        parent_window: Janela principal usada como pai dos diálogos Qt.
        editor_state: EditorState passado ao deserializador; se None,
            tenta ler parent_window.state.
    """

    def __init__(self, scene, parent_window, editor_state=None):
        self.scene = scene
        self.parent = parent_window
        self.editor_state = editor_state or getattr(parent_window, "state", None)
        self.current_file: str | None = None

    # API pública

    def save(self) -> None:
        """Salva no arquivo atual, ou abre diálogo se nenhum arquivo estiver aberto."""
        if not self.current_file:
            return self.save_as()
        self._save_to_path(self.current_file)

    def save_as(self) -> None:
        """Abre diálogo de "salvar como" e grava a cena no caminho escolhido."""
        path, _ = QFileDialog.getSaveFileName(
            self.parent,
            "Salvar cena",
            "",
            "Scene Files (*.json)",
        )
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        self._save_to_path(path)

    def open(self) -> None:
        """Abre diálogo de arquivo e carrega a cena a partir do JSON escolhido."""
        path, _ = QFileDialog.getOpenFileName(
            self.parent,
            "Abrir cena",
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
            QMessageBox.critical(self.parent, "Erro ao abrir", str(e))

    # Métodos internos

    def _save_to_path(self, path: str) -> None:
        """Grava a cena no caminho indicado e atualiza o título da janela.

        Args:
            path: Caminho absoluto do arquivo de destino.
        """
        try:
            from persistence.serializer import save_to_file
            save_to_file(self.scene, path)
            self.current_file = path
            self._update_window_title()
        except Exception as e:
            QMessageBox.critical(self.parent, "Erro ao salvar", str(e))

    def _update_window_title(self) -> None:
        """Atualiza o título da janela principal com o nome do arquivo atual."""
        name = Path(self.current_file).name
        self.parent.setWindowTitle(f"Simulador – {name}")
