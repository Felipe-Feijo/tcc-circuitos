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
        pen = QPen(Qt.GlobalColor.transparent)
        self.setPen(pen)
        self.setBrush(Qt.GlobalColor.transparent)

    def _init_hydraulic_labels(self):
        """Cria os labels de pressão e vazão para âncoras hidráulicas."""
        self._pressure_label = LabelItem(properties={
            "text": "P: --", "font_size": 8, "border": False,
            "color": Qt.GlobalColor.cyan,
        })
        self._pressure_label.setParentItem(self)
        self._pressure_label.setPos(8, -18)
        self._pressure_label.setVisible(False)

        self._flow_label = LabelItem(properties={
            "text": "Q: --", "font_size": 8, "border": False,
            "color": Qt.GlobalColor.yellow,
        })
        self._flow_label.setParentItem(self)
        self._flow_label.setPos(8, -6)
        self._flow_label.setVisible(False)

    def update_hydraulic_labels(self):
        """Atualiza o texto dos labels de pressão e vazão com os valores atuais."""
        if not hasattr(self, "_pressure_label"):
            return
        p = self.pressure
        q = self.flow
        p_text = f"P: {p:.2e}" if isinstance(p, float) else f"P: {p}"
        q_text = f"Q: {q:.2e}" if isinstance(q, float) else f"Q: {q}"
        self._pressure_label.setPlainText(p_text)
        self._flow_label.setPlainText(q_text)

    def set_hydraulic_labels_visible(self, visible: bool):
        """Mostra ou oculta os labels hidráulicos."""
        if hasattr(self, "_pressure_label"):
            self._pressure_label.setVisible(visible)
            self._flow_label.setVisible(visible)

    def shape(self) -> QPainterPath:
        """Retorna área de detecção expandida para facilitar o clique."""
        path = QPainterPath()
        path.addEllipse(QRectF(
            -self.hit_radius, -self.hit_radius,
            2 * self.hit_radius, 2 * self.hit_radius,
        ))
        return path

    def hoverEnterEvent(self, event):
        """Destaca a âncora ao entrar com o cursor no modo CONNECT."""
        node = self.node
        if node and node.editor and node.editor.mode == EditorMode.CONNECT:
            self.setBrush(Qt.GlobalColor.green)
            node.editor.hover_anchor = self
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Restaura aparência e limpa hover_anchor ao sair com o cursor."""
        node = self.node
        if node and node.editor and node.editor.mode == EditorMode.CONNECT:
            self.setBrush(Qt.GlobalColor.transparent)
            if node.editor.hover_anchor is self:
                node.editor.hover_anchor = None
        super().hoverLeaveEvent(event)
