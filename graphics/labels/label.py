"""Editable text item used as a label over diagram components."""

from PyQt6.QtWidgets import QApplication, QGraphicsTextItem
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QFont, QPainter, QPen

# Delta applied over the app's font (main_window.settings) when
# "font_size" isn't explicitly given -- keeps diagram labels tracking
# the global font setting (View > Font Size...) instead of a fixed
# size. With the app's default font at 11pt, this gives 14pt.
DEFAULT_FONT_DELTA = 3


class LabelItem(QGraphicsTextItem):
    """Configurable QGraphicsTextItem for node and anchor labels.

    Supports inline editing (double-click), dragging and rendering with
    an optional border. All visual properties are controlled by the
    `properties` dict, merged with DEFAULT_PROPERTIES in the constructor.

    Font size is dynamic by default: if "font_size" isn't given (stays
    None), the label tracks the app's global font (offset by
    "font_delta") and updates via refresh_default_font_size() when the
    user changes the font in View > Font Size... An explicit "font_size"
    (e.g. loaded from an old saved file) fixes the size and the label
    stops tracking future changes.

    Attributes:
        DEFAULT_PROPERTIES: Default values for every visual property.
        properties: This instance's configuration dict.
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
        # Merges defaults with the passed-in properties
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
        # Text orientation is kept upright by NodeItem, which
        # counter-rotates each label (label.setRotation(-node.rotation()))
        # whenever the component rotates -- see
        # NodeItem._counter_rotate_labels(). Deliberately NOT using
        # ItemIgnoresTransformations here: that flag ignores ANY
        # inherited transformation, not just rotation -- including the
        # view's zoom, which would stop the label from scaling with it.
        # Counter-rotating cancels only the rotation, leaving the rest of
        # the transformation chain (zoom) working normally.

        self._apply_font()

        self.setDefaultTextColor(self.properties["color"])

        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self.setAcceptHoverEvents(True)

    # =========================
    # Editing
    # =========================

    def mouseDoubleClickEvent(self, event):
        """Starts inline editing if the label is editable."""
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
            # removes automatically if it ended up empty
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
    # Font
    # =========================

    def _apply_font(self) -> None:
        """(Re)computes and applies the QFont from properties["font_size"]
        (if explicit) or from the app's font + properties["font_delta"]."""
        size = self.properties.get("font_size")
        if size is None:
            size = QApplication.instance().font().pointSize() + self.properties["font_delta"]

        font = QFont()
        font.setPointSize(size)
        font.setBold(self.properties["bold"])
        self.setFont(font)

    def apply_theme(self, is_light: bool) -> None:
        """Adjusts the text and border color to the current theme --
        black in light, white in dark. There's no UI today to customize
        a label's color individually, so it's safe to always follow the
        theme."""
        color = Qt.GlobalColor.black if is_light else Qt.GlobalColor.white
        self.properties["color"] = color
        self.properties["border_color"] = color
        self.setDefaultTextColor(color)
        self.update()

    def refresh_default_font_size(self) -> None:
        """Reapplies the font size from the app's current font.

        No-op if this label has an explicit "font_size" (e.g. loaded
        from an old saved file) -- only labels in dynamic mode (the
        default) track later changes to the global font.
        """
        if self.properties.get("font_size") is None:
            self._apply_font()

    # =========================
    # External API
    # =========================

    def set_text(self, text: str) -> None:
        """Sets the label's text and updates the properties dict.

        Args:
            text: The label's new text content.
        """
        self.properties["text"] = text
        if self.toPlainText() != text:
            self.setPlainText(text)

    # =========================
    # Drawing with a border
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
