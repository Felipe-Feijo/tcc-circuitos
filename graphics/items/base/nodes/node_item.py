
import uuid
from PyQt6.QtWidgets import QGraphicsItem, QMenu
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, pyqtProperty
from PyQt6.QtGui import QPainter, QPixmap, QColor
from graphics.anchors.anchor import AnchorItem
from graphics.items.base.diagram_item_base import DiagramItemBase
from graphics.labels.label import LabelItem
from graphics.sensor_registry.sensor_registry import SensorRegistry
from graphics.utils.properties_dialog import PropertiesDialog


class NodeItem(DiagramItemBase):
    class_registry = {}
    command = pyqtSignal(str, dict) #node_id, command

    # Subclasses devem declarar:
    #   node_type     : str  — chave de serialização (ex: "valve_3_2_ways")
    #   simulation_cls: type — classe de domínio correspondente
    node_type: str = None
    simulation_cls: type = None

    def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            NodeItem.class_registry[cls.__name__] = cls

    def __init__(self, *args, domain=None, sensor_registry: SensorRegistry | None = None,  **kwargs):
        DiagramItemBase.__init__(self)

        self.id = str(uuid.uuid4())
        self.domain = domain
        self.sensor_registry = sensor_registry
        
        self.anchors = {}
        self.labels = {}
        self.special_labels = {}  # para labels que precisam de tratamento específico (ex: sensor_retracted)
        self.connections = []
        self.setAcceptHoverEvents(True)


        self.simulation_mode = False

        self.use_light_theme = False

        self.pixmap: QPixmap | None = None
        self.draw_selection = True
        self._visual_offset = QPointF(0, 0)

        self.is_preview = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)


    def add_anchor(self, anchor: AnchorItem):
        existing = self.anchors.get(anchor.name)

        if existing:
            # reaproveita a anchor existente
            existing.setPos(anchor.pos())
            return

        anchor.setParentItem(self)
        self.anchors[anchor.name] = anchor

    def remove_anchor(self, name: str):
        anchor = self.anchors.pop(name, None)
        if not anchor:
            return

        # desconecta conexões globais
        for conn in self.connections[:]:
            if conn.source_anchor == anchor or conn.target_anchor == anchor:
                conn.prepare_delete()
                if conn.scene():
                    conn.scene().removeItem(conn)

        # se o node tiver internal_connections, remove também
        if hasattr(self, "internal_connections"):
           
            for conn in self.internal_connections[:]:
                if conn.source_anchor == anchor or conn.target_anchor == anchor:
                    # apenas remove da lista interna, sem tocar na cena
                    self.internal_connections.remove(conn)
                    print(self.internal_connections, "before removing anchor", name)

        # remove da cena
        if anchor.scene():
            anchor.scene().removeItem(anchor)

    def add_label(self, key: str, label, special=False):
        """
        key: identificador lógico do label (ex: 'sensor_retracted')
        label: QGraphicsTextItem ou subclass
        """
        label_dict = self.special_labels if special else self.labels
        existing = label_dict.get(key)

        if existing:
            # reaproveita label existente
            existing.setPlainText(label.toPlainText())
            existing.setPos(label.pos())
            return

        label.setParentItem(self)
        label_dict[key] = label

    def remove_label(self, key: str, special=False):
        label_dict = self.special_labels if special else self.labels
        label = label_dict.pop(key, None)
        if not label:
            return

        if label.scene():
            label.scene().removeItem(label)


    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.update_connections()

        elif change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            if self.editor:
                try:
                    self.editor.theme_changed.disconnect(self.on_theme_changed)
                except (TypeError, RuntimeError):
                    pass
                self.editor.theme_changed.connect(self.on_theme_changed)

        return super().itemChange(change, value)
    
    def on_theme_changed(self, is_light):
        self.use_light_theme = is_light

        if hasattr(self, "_pixmap_cache"):
            self._pixmap_cache.clear()

        self.update()
        
    def update_connections(self):
        for conn in self.connections[:]:  # iterando sobre uma cópia
            # ignora conexões órfãs
            if conn.source_anchor.scene() is None or conn.target_anchor.scene() is None:
                continue

            conn.prepareGeometryChange()
            conn.update()

    def prepare_delete(self):
        # 🔹 desconecta tudo (se ainda precisar)
        self.connections.clear()

        # 🔹 remove todos os sensores da registry
        if hasattr(self, "sensors") and self.sensor_registry:
            for pos, sensor in self.sensors.items():
                name = sensor.get("name")
                if name:
                    self.sensor_registry.unregister(name)


    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter: QPainter, option, widget=None):
        painter.save()  # salva estado atual do painter

        # aplica deslocamento visual (somente para feedback, não afeta anchors)
        painter.translate(self._visual_offset)

        # ícone (se existir)
        if self.pixmap and not self.pixmap.isNull():
            scaled = self.pixmap.scaled(
                self.width,
                self.height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            pos = QPointF(
                (self.width - scaled.width()) / 2,
                (self.height - scaled.height()) / 2
            )
            self.draw_pixmap(painter, pos, scaled)

        # feedback de seleção (bordas, highlight, etc.)
        self.paint_selection_feedback(painter)

        painter.restore()  # restaura estado original, remove o translate


    def draw_pixmap(self, painter, pos, pixmap):
        if not pixmap or pixmap.isNull():
            return

        if not self.use_light_theme:
            painter.drawPixmap(pos, pixmap)
            return

        colored = QPixmap(pixmap.size())
        colored.fill(Qt.GlobalColor.transparent)

        p = QPainter(colored)
        p.drawPixmap(0, 0, pixmap)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        p.fillRect(colored.rect(), QColor(0, 0, 0))
        p.end()

        painter.drawPixmap(pos, colored)

    def getVisualOffset(self):
        return self._visual_offset

    def setVisualOffset(self, value):
        self._visual_offset = value
        self.update()  # força redraw

    visual_offset = pyqtProperty(QPointF, fget=getVisualOffset, fset=setVisualOffset)  

    def apply_preview_constraints(self):
        self.is_preview = True
        self.setOpacity(0.5)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.__class__.__name__,
            "domain": self.domain,
            "position": {
                "x": self.pos().x(),
                "y": self.pos().y()
            },
            "properties": getattr(self, "properties", {}),
            "labels": self.labels_to_dict()
        }
    
    def labels_to_dict(self):

        data = {}
        for key, label in self.labels.items():
            props = {}
            for k, v in label.properties.items():
                if callable(v):
                    props[k] = v.__name__
                else:
                    if isinstance(v, Qt.GlobalColor):
                        props[k] = v.name.lower()
                    else:
                        props[k] = v
            data[key] = {
                "pos": {
                    "x": label.pos().x(),
                    "y": label.pos().y()
                },
                "properties": props
            }
        return data
    
    @classmethod
    def from_dict(cls, data: dict, *, keep_id=True, sensor_registry=None):
        node_cls = cls.class_registry[data["type"]]
        node = node_cls(domain = data['domain'], sensor_registry=sensor_registry)

        if keep_id:
            node.id = data["id"]

        pos = data["position"]
        node.setPos(float(pos["x"]), float(pos["y"]))

        for key, label_data in data.get("labels", {}).items():
            props = dict(label_data["properties"])

            # reverte cores serializadas de volta para Qt.GlobalColor
            for color_key in ("color", "border_color"):
                if color_key in props and isinstance(props[color_key], str):
                    props[color_key] = {c.name.lower(): c for c in Qt.GlobalColor}.get(props[color_key], Qt.GlobalColor.white)

            label = LabelItem(properties=props)
            label.setPos(QPointF(label_data["pos"]["x"], label_data["pos"]["y"]))
            
            # Adiciona como label normal, special=False
            node.add_label(key, label, special=False)

        node.properties = data.get("properties", {})

        if hasattr(node, "apply_properties"):
            node.apply_properties()

        return node
    
    def update_from_domain(self, domain_node):
        super().update_from_domain(domain_node)
        
        for name, anchor in self.anchors.items():
            domain_anchor = domain_node.anchors.get(name)
            if domain_anchor and domain_anchor.domain == "hydraulic":
                anchor.pressure = domain_anchor.pressure
                anchor.flow = domain_anchor.flow
                anchor.update_hydraulic_labels()

    def reset_visual_state(self):
        """
        Retorna o item gráfico ao estado default (fora de simulação).
        """
        self.simulation_mode = False

        # 🔹 reset visual
        self.visual_offset = QPointF(0, 0)

        if hasattr(self, "initialize_actuators"):
            self.initialize_actuators()

        # 🔹 reset estado do corpo (se existir)
        if hasattr(self, "update_body_visuals"):
            self.body_state = 0
            self.update_body_visuals()

        # 🔹 atualiza anchors dependentes do estado
        if hasattr(self, "update_anchor_positions"):
            self.update_anchor_positions()

        self.update()

    def _next_label_key(self):
        i = 0
        while f"label_{i}" in self.labels:
            i += 1
        return f"label_{i}"

    def extend_context_menu(self, menu: QMenu):
        props_action = menu.addAction("Propriedades...")
        props_action.triggered.connect(self._open_properties_dialog)
        menu.addSeparator()
        add_label_action = menu.addAction("Adicionar label")

        def _add_label():
            label = LabelItem(properties={
                "editable": True,
                "movable": True,
                "border": False,
            })

            shape_rect = self.shape().boundingRect()
            label.setPos(shape_rect.width() / 2, shape_rect.bottom() + 20)

            key = self._next_label_key()
            self.add_label(key, label, special=False)

            label._editing = True
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            label.setFocus()

        add_label_action.triggered.connect(_add_label)
        super().extend_context_menu(menu)

    def _open_properties_dialog(self):
        dialog = self.build_properties_dialog()
        if dialog is None:
            dialog = PropertiesDialog(title="Properties")
            dialog.add_no_properties_message()
        if dialog.exec():  # retorna True só se o usuário clicou OK
            self.apply_properties_from_dialog(dialog)

    def build_properties_dialog(self) -> PropertiesDialog | None:
        return None
    
    def apply_properties_from_dialog(self, dialog: PropertiesDialog):
        pass

    def mouseDoubleClickEvent(self, event):
        if self.simulation_mode:
            event.ignore()
            return
        dialog = self.build_properties_dialog()
        if dialog is None:
            event.ignore()
            return
        if dialog.exec():
            self.apply_properties_from_dialog(dialog)
        event.accept()