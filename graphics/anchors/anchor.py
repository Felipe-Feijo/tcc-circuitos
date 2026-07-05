"""Item gráfico de âncora — ponto de conexão visível nos nós do diagrama."""

from PyQt6.QtWidgets import QGraphicsEllipseItem
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QPainterPath

from graphics.labels.label import LabelItem
from editor.mode import EditorMode


class AnchorItem(QGraphicsEllipseItem):
    """Representa visualmente um ponto de conexão de um NodeItem.

    Detecta hover do cursor no modo CONNECT e exibe/oculta conforme o contexto.
    Para âncoras hidráulicas, mantém labels de pressão e vazão atualizados
    pelo ViewSync após cada passo de simulação.

    Args:
        name: Identificador da âncora (ex: "P", "A", "X1").
        pos: Posição relativa ao nó pai.
        radius: Raio visual da elipse.
        node: NodeItem proprietário.
        domain: Domínio da âncora ("pneumatic", "electric" ou "hydraulic").
        exit_directions: Direções de saída permitidas para o roteador A*.
        margin: Margem adicional para detecção de colisão no roteador.
    """

    def __init__(self, name: str, pos: QPointF, radius: float = 6,
                 node=None, domain=None, exit_directions=None, margin=None):
        super().__init__(-radius, -radius, 2 * radius, 2 * radius, node)

        self.name = name
        self.id = (node.id, name)
        self.node = node
        self.domain = domain
        self.hit_radius = radius * 4

        # Direções de saída para o roteador A* (ex: {"external": ["left", "right"]})
        self.exit_directions = exit_directions
        self.margin = margin

        self.setPos(pos)
        self._active = False

        if domain == "hydraulic":
            self.pressure: float = 0.0
            self.flow: float = 0.0
            self._init_hydraulic_labels()

        # Aparência inicial: invisível até hover ou simulação
        self.setBrush(Qt.GlobalColor.transparent)
        self.setPen(QPen(Qt.PenStyle.NoPen))

        self.setZValue(100)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def shape(self) -> QPainterPath:
        """Retorna área de detecção expandida para facilitar o clique."""
        path = QPainterPath()
        r = self.hit_radius
        path.addEllipse(-r, -r, 2 * r, 2 * r)
        return path

    def boundingRect(self):
        r = self.hit_radius
        return QRectF(-r, -r, 2 * r, 2 * r)

    def hoverEnterEvent(self, event):
        """Destaca a âncora ao entrar com o cursor no modo CONNECT."""
        if not self.node.editor:
            return

        is_source_anchor = (
            self.node.editor._connecting
            and self.node.editor._conn_source_anchor is self
        )

        if self.node.editor.mode == EditorMode.CONNECT and not is_source_anchor:
            source = self.node.editor._conn_source_anchor

            # Impede conexão entre âncoras de domínios diferentes
            if source and source.domain != self.domain:
                return

            self.setBrush(Qt.GlobalColor.red)
            self.node.editor.hover_anchor = self
            self.update()

    def hoverLeaveEvent(self, event):
        """Restaura aparência e limpa hover_anchor ao sair com o cursor."""
        if not self.node.editor:
            return

        if self.node.editor.hover_anchor is self:
            self.node.editor.hover_anchor = None

        is_source_anchor = (
            self.node.editor._connecting
            and self.node.editor._conn_source_anchor is self
        )

        if not is_source_anchor:
            self.setBrush(Qt.GlobalColor.transparent)
            self.update()

    def set_exit_directions(self, directions) -> None:
        """Define as direções de saída permitidas para o roteador A*.

        Args:
            directions: Valor aceito por exit_directions (ex: dict ou lista).
        """
        self.exit_directions = directions

    def set_hydraulic_labels_visible(self, visible: bool):
        """Mostra ou oculta os labels hidráulicos."""
        if hasattr(self, "_label_hydraulic"):
            self._label_hydraulic.setVisible(visible)

    def _init_hydraulic_labels(self):
        """Cria os labels de pressão e vazão para âncoras hidráulicas."""
        self._label_hydraulic = LabelItem(properties={
            "text": "0.0 Pa | 0.0 m³/s",
            "editable": False,
            "movable": True,
            "border": False,
            "font_size": 8,
        })
        self._label_hydraulic.setParentItem(self)
        self._label_hydraulic.setPos(self._default_label_offset())

    def _default_label_offset(self) -> QPointF:
        """Calcula um offset inicial que empurra o label para fora do componente.

        Usa a posição da âncora relativa ao bounding box do node (self.node.width/
        height) para descobrir em qual borda ela está (topo/base/esquerda/direita)
        e desloca o label para o lado de fora dessa borda, evitando que ele nasça
        sobreposto ao sprite do componente.
        """
        margin = 4
        rect = self._label_hydraulic.boundingRect()
        w, h = rect.width(), rect.height()

        node = self.node
        node_w = getattr(node, "width", 0)
        node_h = getattr(node, "height", 0)
        x, y = self.pos().x(), self.pos().y()

        on_top = y <= 0
        on_bottom = bool(node_h) and y >= node_h
        on_left = x <= 0
        on_right = bool(node_w) and x >= node_w

        if on_top:
            return QPointF(-w / 2, -h - margin)
        if on_bottom:
            return QPointF(-w / 2, margin)
        if on_left:
            return QPointF(-w - margin, -h / 2)
        if on_right:
            return QPointF(margin, -h / 2)

        # Âncora interna (não está em nenhuma borda): mantém o padrão antigo.
        return QPointF(margin, -h - margin)

    def update_hydraulic_labels(self):
        """Atualiza o texto dos labels de pressão e vazão com os valores atuais."""
        if not hasattr(self, "_label_hydraulic"):
            return

        if isinstance(self.pressure, str) or isinstance(self.flow, str):
            self._label_hydraulic.set_text("ERR | ERR")
            return

        p = self.format_hydraulic_value(self.pressure, "Pa")
        q = self.format_hydraulic_value(abs(self.flow), "m³/s")
        self._label_hydraulic.set_text(f"{p} | {q}")

    def format_hydraulic_value(self, value: float, unit: str) -> str:
        if abs(value) < 1e-10:
            return f"0 {unit}"
        if unit == "Pa" and abs(value) < 1.0:
            return f"0 {unit}"
        return f"{value:.3g} {unit}"
