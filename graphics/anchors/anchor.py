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

    def reposition_hydraulic_label(self) -> None:
        """Recalcula e aplica o offset do label hidráulico.

        Chamado por NodeItem.rotate() depois de cada rotação, pra manter
        o label crescendo pro lado de fora certo (ver _default_label_offset).
        """
        if hasattr(self, "_label_hydraulic"):
            self._label_hydraulic.setPos(self._default_label_offset())

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
        """Calcula um offset que empurra o label para fora do componente.

        Classifica a borda (topo/base/esquerda/direita) em coordenadas de
        CENA -- não locais -- porque o label é filho da âncora (que gira
        junto com o node) mas tem ItemIgnoresTransformations (ver
        LabelItem): sua ORIENTAÇÃO fica sempre reta, mas sua POSIÇÃO
        continua sendo mapeada pela transformação herdada. Se a borda
        fosse classificada em coordenadas locais (pré-rotação), o offset
        cresceria sempre na mesma direção "de fábrica" mesmo depois do
        componente girar -- fazendo o label crescer pro lado errado
        (sobrepondo o sprite) assim que o node é rotacionado.

        Reutilizável a qualquer momento (não só na criação da âncora) --
        NodeItem.rotate() chama de novo depois de cada rotação, pra manter
        o label no lado de fora certo.
        """
        margin = 4
        rect = self._label_hydraulic.boundingRect()
        w, h = rect.width(), rect.height()

        node = self.node
        anchor_scene_pos = self.scenePos()
        node_scene_rect = node.sceneBoundingRect()

        on_top    = anchor_scene_pos.y() <= node_scene_rect.top() + 1
        on_bottom = anchor_scene_pos.y() >= node_scene_rect.bottom() - 1
        on_left   = anchor_scene_pos.x() <= node_scene_rect.left() + 1
        on_right  = anchor_scene_pos.x() >= node_scene_rect.right() - 1

        if on_top:
            scene_offset = QPointF(-w / 2, -h - margin)
        elif on_bottom:
            scene_offset = QPointF(-w / 2, margin)
        elif on_left:
            scene_offset = QPointF(-w - margin, -h / 2)
        elif on_right:
            scene_offset = QPointF(margin, -h / 2)
        else:
            # Âncora interna (não está em nenhuma borda): mantém o padrão antigo.
            scene_offset = QPointF(margin, -h - margin)

        # scene_offset está em coordenadas de cena (já reta); converte pra
        # coordenada LOCAL da âncora, que é o que setPos() espera -- o Qt
        # vai remapear pra cena aplicando a rotação de novo, cancelando
        # essa conversão e deixando o label exatamente onde calculamos.
        return self.mapFromScene(anchor_scene_pos + scene_offset)

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
