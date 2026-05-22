"""Item de texto editável usado como rótulo sobre componentes do diagrama."""

from PyQt6.QtWidgets import QGraphicsTextItem
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QFont, QPainter, QPen


class LabelItem(QGraphicsTextItem):
    """QGraphicsTextItem configurável para rótulos de nós e âncoras.

    Suporta edição inline (duplo clique), arrasto e renderização com borda
    opcional. Todas as propriedades visuais são controladas pelo dicionário
    `properties`, mesclado com DEFAULT_PROPERTIES no construtor.

    Attributes:
        DEFAULT_PROPERTIES: Valores padrão para todas as propriedades visuais.
        properties: Dicionário de configuração desta instância.
    """

    DEFAULT_PROPERTIES = {
        "text": "",
        "editable": False,
        "movable": False,
        "max_length": None,
        "on_commit": None,
        "font_size": 12,
        "bold": False,
        "color": Qt.GlobalColor.white,
        "border": True,
        "border_width": 1.2,
        "border_color": Qt.GlobalColor.white,
    }

    def __init__(self, properties: dict | None = None):
        # Mescla defaults com propriedades passadas
        label_properties = dict(self.DEFAULT_PROPERTIES)
        if properties:
            label_properties.update(properties)

        super().__init__(label_properties["text"])

        self.properties = label_properties
        self._editing = False

        font = QFont()
        font.setPointSize(label_properties["font_size"])
        font.setBold(label_properties["bold"])
        self.setFont(font)
        self.setDefaultTextColor(label_properties["color"])

        if label_properties["movable"]:
            self.setFlag(self.GraphicsItemFlag.ItemIsMovable, True)

        self.setAcceptHoverEvents(True)

    def paint(self, painter: QPainter, option, widget=None):
        """Desenha o texto e, opcionalmente, uma borda ao redor."""
        if self.properties.get("border"):
            pen = QPen(
                self.properties["border_color"],
                self.properties["border_width"],
            )
            painter.setPen(pen)
            painter.drawRect(self.boundingRect().adjusted(1, 1, -1, -1))
        super().paint(painter, option, widget)

    def mouseDoubleClickEvent(self, event):
        """Inicia edição inline se o label for editável."""
        if self.properties.get("editable"):
            self._editing = True
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            self.setFocus()
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        """Confirma edição e chama on_commit ao perder foco."""
        if self._editing:
            self._editing = False
            self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            max_len = self.properties.get("max_length")
            if max_len and len(self.toPlainText()) > max_len:
                self.setPlainText(self.toPlainText()[:max_len])
            on_commit = self.properties.get("on_commit")
            if callable(on_commit):
                on_commit(self.toPlainText())
        super().focusOutEvent(event)
