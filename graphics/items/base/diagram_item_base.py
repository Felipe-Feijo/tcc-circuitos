"""Classe base para todos os itens gráficos do diagrama."""

from PyQt6.QtWidgets import QGraphicsItem, QMenu, QGraphicsObject
from PyQt6.QtGui import QPen
from PyQt6.QtCore import Qt

from editor.mode import EditorMode


class DiagramItemBase(QGraphicsObject):
    """Base comum para NodeItem e ConnectionItem.

    Fornece:
    - Seleção Qt habilitada por padrão.
    - Atualização do retângulo da cena ao soltar o mouse.
    - Menu de contexto no modo SELECT, extensível por subclasses via
      extend_context_menu().
    - Renderização de destaque de seleção via paint_selection_feedback().

    Attributes:
        editor: EditorState injetado após adicionar o item à cena.
        draw_selection: Se False, suprime o destaque azul de seleção.
    """

    def __init__(self):
        super().__init__()
        self.editor = None
        self.draw_selection = True
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    def mouseReleaseEvent(self, event):
        """Solicita atualização do retângulo da cena ao soltar o mouse."""
        super().mouseReleaseEvent(event)
        if self.editor:
            self.editor.update_scene_rect()

    def contextMenuEvent(self, event):
        """Exibe menu de contexto no modo SELECT; ignora nos demais modos."""
        if not self.editor:
            return
        if self.editor.mode != EditorMode.SELECT:
            event.ignore()
            return

        scene = self.scene()
        if not self.isSelected():
            scene.clearSelection()
            self.setSelected(True)

        menu = QMenu()
        self.editor.active_context_menu = menu
        menu.addAction(self.editor.actions["delete"])
        self.extend_context_menu(menu)
        menu.exec(event.screenPos())
        self.editor.active_context_menu = None
        event.accept()

    def extend_context_menu(self, menu: QMenu) -> None:
        """Permite que subclasses adicionem entradas ao menu de contexto.

        Chamado por contextMenuEvent antes de exibir o menu. No-op por padrão.
        """

    def paint_selection_feedback(self, painter) -> None:
        """Desenha destaque tracejado azul ao redor do shape quando selecionado."""
        if self.draw_selection and self.isSelected():
            pen = QPen(Qt.GlobalColor.blue, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.shape())

    def update_from_domain(self, domain_node) -> None:
        """Atualiza estado visual a partir do nó de domínio. No-op por padrão."""
