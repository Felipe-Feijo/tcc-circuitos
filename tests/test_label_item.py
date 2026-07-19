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
