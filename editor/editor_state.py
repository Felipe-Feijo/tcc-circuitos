"""Estado mutável de interação do editor de diagramas."""

from PyQt6.QtCore import QObject, pyqtSignal


class EditorState(QObject):
    """Centraliza o estado de interação do editor.

    Pertencente à MainWindow e passado para GraphicsView, DiagramItemBase
    e AnchorItem, eliminando referências diretas à janela principal.

    Attributes:
        mode: Modo atual do editor (enum EditorMode).
        pending_node: NodeDescriptor selecionado na paleta (somente no modo ADD).
        hover_anchor: AnchorItem sob o cursor (somente no modo CONNECT).
        active_context_menu: QMenu aberto no momento, fechado ao deletar.
        actions: Dicionário de QActions preenchido pela MainWindow após construção.

    Signals:
        add_node_requested(x, y): Usuário clicou para posicionar um nó.
        scene_rect_update_requested: O retângulo da cena deve ser recalculado.
        theme_changed(is_light): O tema da aplicação foi alterado.
    """

    add_node_requested = pyqtSignal(float, float)
    scene_rect_update_requested = pyqtSignal()
    theme_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()

        self.mode = None
        self.pending_node = None
        self.hover_anchor = None
        self.active_context_menu = None

        # Estado de arrasto de conexão — lido por GraphicsView e AnchorItem
        self._connecting: bool = False
        self._conn_source_anchor = None

        self.actions: dict = {}

    def add_node_at(self, x: float, y: float) -> None:
        """Emite o sinal para posicionar um nó nas coordenadas da cena.

        Args:
            x: Coordenada horizontal na cena.
            y: Coordenada vertical na cena.
        """
        self.add_node_requested.emit(x, y)

    def update_scene_rect(self) -> None:
        """Solicita recálculo do retângulo da cena."""
        self.scene_rect_update_requested.emit()
