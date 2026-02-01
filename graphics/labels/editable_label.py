from PyQt6.QtWidgets import QGraphicsTextItem
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QFont, QPainter, QPen

class EditableLabelItem(QGraphicsTextItem):
    def __init__(self, text: str, *, on_commit=None):
        super().__init__(text)

        self.on_commit = on_commit

        # 🔠 Fonte maior
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        self.setFont(font)

        self.setDefaultTextColor(Qt.GlobalColor.white)

        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)

        self._editing = False

    def mouseDoubleClickEvent(self, event):
        self._editing = True
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus()
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        self.finish_editing()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finish_editing()
            return  # evita quebrar linha
        super().keyPressEvent(event)

    def finish_editing(self):
        if not self._editing:
            return
        self._editing = False

        # sai do modo de edição
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        # 🔹 remove seleção visual do item
        self.setSelected(False)

        # força redraw
        self.update()

        # chama callback
        if callable(self.on_commit):
            self.on_commit(self.toPlainText())

    # =========================
    # Atualizar texto externo
    # =========================
    def set_text(self, text: str):
        """Atualiza o texto da label sem entrar em edição."""
        self.setPlainText(text)

    # =========================
    # Desenho com outline
    # =========================
    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)

        painter.save()

        pen = QPen(Qt.GlobalColor.white)
        pen.setWidthF(1.2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        rect: QRectF = self.boundingRect().adjusted(-2, -1, 2, 1)
        painter.drawRect(rect)

        painter.restore()