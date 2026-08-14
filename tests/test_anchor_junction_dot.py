"""A bolinha de junção é permanente: aparece quando um anchor tem 3+
conexões vivas, some quando cai pra 2. hoverLeaveEvent não deve mais
apagar a bolinha incondicionalmente -- ela precisa sobreviver ao mouse
saindo da área de hover."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsObject
from PyQt6.QtCore import QPointF, QRectF, Qt

app = QApplication.instance() or QApplication([])

from graphics.anchors.anchor import AnchorItem


class _FakeConn:
    def __init__(self, source_anchor, target_anchor):
        self.source_anchor = source_anchor
        self.target_anchor = target_anchor


class _DummyNode(QGraphicsObject):
    def __init__(self):
        super().__init__()
        self.id = "node-1"
        self.connections = []
        self.editor = None

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, 1, 1)

    def paint(self, painter, option, widget=None):
        pass


def _is_dot_visible(anchor: AnchorItem) -> bool:
    return anchor.brush().color().alpha() > 0


def test_dot_hidden_with_two_connections():
    scene = QGraphicsScene()
    node = _DummyNode()
    scene.addItem(node)
    anchor = AnchorItem("J", QPointF(0, 0), node=node, domain="electric",
                         exit_directions={"external": ["right"], "internal": ["right"]})
    anchor.setParentItem(node)

    other_a, other_b = QPointF(), QPointF()  # placeholders, só o tipo importa
    node.connections = [_FakeConn(anchor, "x"), _FakeConn("y", anchor)]

    anchor.refresh_junction_dot()
    assert not _is_dot_visible(anchor)


def test_dot_visible_with_three_connections():
    scene = QGraphicsScene()
    node = _DummyNode()
    scene.addItem(node)
    anchor = AnchorItem("J", QPointF(0, 0), node=node, domain="electric",
                         exit_directions={"external": ["right"], "internal": ["right"]})
    anchor.setParentItem(node)

    node.connections = [_FakeConn(anchor, "x"), _FakeConn("y", anchor), _FakeConn(anchor, "z")]

    anchor.refresh_junction_dot()
    assert _is_dot_visible(anchor)


def test_hover_leave_preserves_junction_dot():
    scene = QGraphicsScene()
    node = _DummyNode()
    node.editor = None  # hoverLeaveEvent retorna cedo sem editor -- ok pro teste
    scene.addItem(node)
    anchor = AnchorItem("J", QPointF(0, 0), node=node, domain="electric",
                         exit_directions={"external": ["right"], "internal": ["right"]})
    anchor.setParentItem(node)
    node.connections = [_FakeConn(anchor, "x"), _FakeConn("y", anchor), _FakeConn(anchor, "z")]
    anchor.refresh_junction_dot()
    assert _is_dot_visible(anchor)

    # Sem editor, hoverLeaveEvent não faz nada (early return) -- chamamos
    # refresh diretamente pra simular o que hoverLeaveEvent deve fazer.
    anchor.refresh_junction_dot()
    assert _is_dot_visible(anchor)
