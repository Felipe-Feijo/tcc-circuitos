"""Item de texto editável usado como rótulo sobre componentes do diagrama."""

from PyQt6.QtWidgets import QApplication, QGraphicsTextItem
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QFont, QPainter, QPen

# Delta aplicado sobre a fonte da aplicação (main_window.settings) quando
# "font_size" não é explicitamente informado -- mantém os labels do
# diagrama acompanhando o ajuste global de fonte (View > Font Size...) em
# vez de um tamanho fixo. Com a fonte padrão do app em 11pt, isso dá 14pt.
DEFAULT_FONT_DELTA = 3


class LabelItem(QGraphicsTextItem):
    """QGraphicsTextItem configurável para rótulos de nós e âncoras.

    Suporta edição inline (duplo clique), arrasto e renderização com borda
    opcional. Todas as propriedades visuais são controladas pelo dicionário
    `properties`, mesclado com DEFAULT_PROPERTIES no construtor.

    O tamanho de fonte é dinâmico por padrão: se "font_size" não for
    informado (fica None), o label acompanha a fonte global da aplicação
    (deslocada por "font_delta") e se atualiza via refresh_default_font_size()
    quando o usuário muda a fonte em View > Font Size... Um "font_size"
    explícito (ex: vindo de um arquivo salvo antigo) fixa o tamanho e o
    label deixa de acompanhar mudanças futuras.

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
        "font_size": None,
        "font_delta": DEFAULT_FONT_DELTA,
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

        self.editable = self.properties["editable"]
        self.max_length = self.properties["max_length"]
        self.on_commit = self.properties["on_commit"]

        self.movable = self.properties["movable"]
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, self.movable)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, self.editable or self.movable)
        # A orientação do texto é mantida reta pelo NodeItem, que
        # contra-rotaciona cada label (label.setRotation(-node.rotation()))
        # sempre que o componente gira -- ver NodeItem._counter_rotate_labels().
        # Deliberadamente NÃO usamos ItemIgnoresTransformations aqui: essa
        # flag ignora QUALQUER transformação herdada, não só rotação --
        # inclusive o zoom da view, fazendo o label parar de escalar com
        # o zoom. Contra-rotacionar cancela só a rotação, preservando o
        # resto da cadeia de transformação (zoom) normalmente.

        self._apply_font()

        self.setDefaultTextColor(self.properties["color"])

        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self.setAcceptHoverEvents(True)

    # =========================
    # Edição
    # =========================

    def mouseDoubleClickEvent(self, event):
        """Inicia edição inline se o label for editável."""
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
    # Fonte
    # =========================

    def _apply_font(self) -> None:
        """(Re)calcula e aplica o QFont a partir de properties["font_size"]
        (se explícito) ou da fonte da aplicação + properties["font_delta"]."""
        size = self.properties.get("font_size")
        if size is None:
            size = QApplication.instance().font().pointSize() + self.properties["font_delta"]

        font = QFont()
        font.setPointSize(size)
        font.setBold(self.properties["bold"])
        self.setFont(font)

    def refresh_default_font_size(self) -> None:
        """Reaplica o tamanho de fonte a partir da fonte atual da aplicação.

        No-op se este label tiver um "font_size" explícito (ex: carregado
        de um arquivo salvo antigo) -- só labels em modo dinâmico (o
        padrão) acompanham mudanças posteriores da fonte global.
        """
        if self.properties.get("font_size") is None:
            self._apply_font()

    # =========================
    # API externa
    # =========================

    def set_text(self, text: str) -> None:
        """Define o texto do label e atualiza o dict de propriedades.

        Args:
            text: Novo conteúdo textual do label.
        """
        self.properties["text"] = text
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
