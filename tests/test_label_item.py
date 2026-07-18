import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsItem

app = QApplication.instance() or QApplication([])

from graphics.labels.label import LabelItem


def test_label_ignores_parent_transformations():
    label = LabelItem(properties={"text": "hello"})
    assert bool(label.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
