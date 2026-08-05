"""Classe base para todos os itens gráficos do diagrama."""

from PyQt6.QtWidgets import QGraphicsItem, QMenu, QGraphicsObject
from PyQt6.QtGui import QPen, QColor
from PyQt6.QtCore import Qt

from editor.mode import EditorMode


class DiagramItemBase(QGraphicsObject):
    """Base comum para NodeItem e ConnectionItem.

    Fornece:
    - Seleção Qt habilitada por padrão.
    - Atualização do retângulo da cena ao soltar o mouse.
    - Menu de contexto nos modos SELECT e SIMULATE, extensível por
      subclasses via extend_context_menu(). Em SIMULATE, "Deletar" fica de
      fora (edição de projeto continua desabilitada) -- só entradas que as
      próprias subclasses decidiram expor durante simulação (checando
      self.simulation_mode) aparecem; ver NodeItem.extend_context_menu().
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
        """Exibe menu de contexto nos modos SELECT e SIMULATE; ignora nos demais.

        Em SIMULATE, "Deletar" não é oferecido (deletar um nó/conexão no
        meio de uma simulação corromperia o grafo de domínio em execução);
        o restante do conteúdo do menu é decidido por extend_context_menu(),
        que cada subclasse já restringe a entradas cientes de simulação
        quando self.simulation_mode é True.
        """
        if not self.editor:
            return
        if not self._context_menu_allowed():
            event.ignore()
            return

        scene = self.scene()
        if not self.isSelected():
            scene.clearSelection()
            self.setSelected(True)

        menu = QMenu()
        self.editor.active_context_menu = menu
        if self.editor.mode == EditorMode.SELECT:
            menu.addAction(self.editor.actions["delete"])
        self.extend_context_menu(menu)
        menu.exec(event.screenPos())
        self.editor.active_context_menu = None
        event.accept()

    def _context_menu_allowed(self) -> bool:
        """True se o menu de contexto deve abrir no modo atual do editor.

        SELECT: edição normal de projeto. SIMULATE: simulação rodando --
        o menu ainda abre, mas com conteúdo restrito (sem "Deletar"; o
        resto depende de cada subclasse checar self.simulation_mode em
        extend_context_menu()). ADD/CONNECT: bloqueado, como antes.
        """
        return self.editor.mode in (EditorMode.SELECT, EditorMode.SIMULATE)

    def extend_context_menu(self, menu: QMenu) -> None:
        """Permite que subclasses adicionem entradas ao menu de contexto.

        Chamado por contextMenuEvent antes de exibir o menu. No-op por padrão.
        """

    def paint_selection_feedback(self, painter) -> None:
        """Desenha destaque de seleção (azul) e/ou de defeito ativo (vermelho)."""
        if self.draw_selection and self.isSelected():
            pen = QPen(Qt.GlobalColor.blue, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.shape())

        if getattr(self, "_defect_indicator", False):
            pen = QPen(QColor("#e74c3c"), 3, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.shape())

    def update_from_domain(self, domain_node) -> None:
        """Atualiza estado visual a partir do nó de domínio. No-op por padrão."""
