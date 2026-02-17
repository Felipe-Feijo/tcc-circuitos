from PyQt6.QtWidgets import QGraphicsTextItem
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QFont, QPainter, QPen

class LabelItem(QGraphicsTextItem):
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
        # mescla defaults com propriedades passadas
        label_properties = dict(self.DEFAULT_PROPERTIES)
        if properties:
            label_properties.update(properties)

        super().__init__(label_properties["text"])

        self.properties = label_properties
        self._editing = False

        self.editable = self.properties["editable"]
        self.max_length = self.properties["max_length"]
        self.on_commit = self.properties["on_commit"]

        self.movable = self.properties["movable"]
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, self.movable)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, self.editable or self.movable)

        # Fonte
        font = QFont()
        font.setPointSize(self.properties["font_size"])
        font.setBold(self.properties["bold"])
        self.setFont(font)

        # Cor do texto
        self.setDefaultTextColor(self.properties["color"])

        # Interação
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)


    # =========================
    # Edição
    # =========================
    def mouseDoubleClickEvent(self, event):
        if not self.editable:
            event.ignore()
            return
        self._editing = True
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus()
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        if self.editable:
            self.finish_editing()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if not self.editable:
            return

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finish_editing()
            return

        if self.max_length is not None:
            text = self.toPlainText()
            allowed_keys = (
                Qt.Key.Key_Backspace,
                Qt.Key.Key_Delete,
                Qt.Key.Key_Left,
                Qt.Key.Key_Right,
                Qt.Key.Key_Home,
                Qt.Key.Key_End,
            )
            if len(text) >= self.max_length and event.key() not in allowed_keys:
                event.ignore()
                return

        super().keyPressEvent(event)

    def finish_editing(self):
        if not self._editing:
            return

        self._editing = False
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setSelected(False)

        text = self.toPlainText().strip()
        if self.max_length:
            text = text[:self.max_length]
            self.setPlainText(text)

        if not text:
            # remove automaticamente se ficou vazia
            if self.parentItem() and hasattr(self.parentItem(), "labels"):
                node = self.parentItem()
                key = next((k for k, v in node.labels.items() if v is self), None)
                if key:
                    node.remove_label(key)
            return

        if callable(self.on_commit):
            self.on_commit(text)

        self.update()

    # =========================
    # API externa
    # =========================
    def set_text(self, text: str):
        if self.toPlainText() != text:
            self.setPlainText(text)

    # =========================
    # Desenho com borda
    # =========================
    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)

        if not self.properties.get("border", True):
            return

        painter.save()
        pen = QPen(self.properties.get("border_color", Qt.GlobalColor.white))
        pen.setWidthF(self.properties.get("border_width", 1.2))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        rect: QRectF = self.boundingRect().adjusted(-2, -1, 2, 1)
        painter.drawRect(rect)
        painter.restore()