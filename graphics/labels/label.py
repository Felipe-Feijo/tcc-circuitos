from PyQt6.QtWidgets import QGraphicsTextItem
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QFont, QPainter, QPen

class LabelItem(QGraphicsTextItem):
    def __init__(self, text: str, *, editable=False, max_length=None, on_commit=None):
        super().__init__(text)

        self.on_commit = on_commit
        self.editable = editable
        self._editing = False
        self.max_length = max_length

        # 🔠 Fonte maior
        font = QFont()
        font.setPointSize(15)
        font.setBold(True)
        self.setFont(font)

        self.setDefaultTextColor(Qt.GlobalColor.white)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        if editable:
            self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        else:
            self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, False)
        
        

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

        # Enter confirma edição
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finish_editing()
            return

        # Limite de caracteres
        if self.max_length is not None:
            text = self.toPlainText()

            # teclas que NÃO contam como caractere
            allowed_keys = (
                Qt.Key.Key_Backspace,
                Qt.Key.Key_Delete,
                Qt.Key.Key_Left,
                Qt.Key.Key_Right,
                Qt.Key.Key_Home,
                Qt.Key.Key_End,
            )

            # se já atingiu o limite e não é tecla permitida → bloqueia
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
        self.update()

        text = self.toPlainText()
        if self.max_length is not None:
            text = text[:self.max_length]
            self.setPlainText(text)

        if callable(self.on_commit):
            self.on_commit(text)

    # =========================
    # Atualizar texto externo
    # =========================
    def set_text(self, text: str):
        if self.toPlainText() != text:
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