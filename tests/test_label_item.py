import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsItem

app = QApplication.instance() or QApplication([])

from graphics.labels.label import LabelItem


def test_label_does_not_ignore_parent_transformations():
    """Deliberadamente NÃO usa ItemIgnoresTransformations -- essa flag
    ignoraria toda transformação herdada (inclusive o zoom da view), não
    só rotação. NodeItem._counter_rotate_labels() cancela apenas a
    rotação, mantendo o zoom funcionando normalmente -- ver
    test_anchor_hydraulic_label_rotation.py para o comportamento."""
    label = LabelItem(properties={"text": "hello"})
    assert not bool(label.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)


def test_default_font_size_derives_from_app_font_plus_delta():
    original = app.font()
    try:
        font = app.font()
        font.setPointSize(11)
        app.setFont(font)

        label = LabelItem(properties={"text": "normal"})
        assert label.font().pointSize() == 14  # 11 + DEFAULT_FONT_DELTA (3)

        small = LabelItem(properties={"text": "small", "font_delta": -1})
        assert small.font().pointSize() == 10  # 11 - 1
    finally:
        app.setFont(original)


def test_explicit_font_size_overrides_and_stays_fixed():
    label = LabelItem(properties={"text": "fixed", "font_size": 20})
    assert label.font().pointSize() == 20

    original = app.font()
    try:
        font = app.font()
        font.setPointSize(30)
        app.setFont(font)
        label.refresh_default_font_size()
        assert label.font().pointSize() == 20  # unchanged: explicit override
    finally:
        app.setFont(original)


def test_refresh_default_font_size_tracks_live_app_font():
    original = app.font()
    try:
        font = app.font()
        font.setPointSize(11)
        app.setFont(font)

        label = LabelItem(properties={"text": "dynamic"})
        assert label.font().pointSize() == 14

        font.setPointSize(20)
        app.setFont(font)
        label.refresh_default_font_size()

        assert label.font().pointSize() == 23  # 20 + 3
    finally:
        app.setFont(original)
