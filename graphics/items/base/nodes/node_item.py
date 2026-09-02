import uuid
import copy
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene, QMenu
from PyQt6.QtCore import (
    Qt, QRectF, QPointF, QTimer, QCoreApplication, pyqtSignal, pyqtProperty,
)
from PyQt6.QtGui import QPainter, QPixmap
from graphics.anchors.anchor import AnchorItem
from graphics.items.base.diagram_item_base import DiagramItemBase
from graphics.labels.label import LabelItem
from graphics.sensor_registry.sensor_registry import SensorRegistry
from graphics.utils.properties_dialog import PropertiesDialog
from graphics.utils.defect_dialog import DefectDialog
from graphics.utils.pixmap_utils import recolor_pixmap_black
from graphics.items.base.nodes.node_descriptor import PaletteMeta

# Generic "default_side" -> body_state mapping for 3-position nodes
# (THREE_POSITION=True). Lives here, in the base class, because
# reset_visual_state() needs it and can't depend on a specific subclass
# module (e.g. directional_valve_item.py, which imports this constant from here).
THREE_POSITION_SIDE_MAP = {"right": 0, "center": 1, "left": 2}


class NodeItem(DiagramItemBase):
    """Base class for all diagram nodes.

    ── Subclass declarations ───────────────────────────────────────────────
    Every concrete subclass must declare at the class level:

        node_type: str       Serialisation key (e.g. "valve_3_2_ways").
        simulation_cls: type Corresponding domain/simulation class.

    ── Initialisation lifecycle ────────────────────────────────────────────
    Do NOT override __init__ in subclasses.  Override setup() instead.

    Order guaranteed by the base __init__:
        1. Infrastructure attributes are set (id, anchors, labels, …).
        2. self.setup() is called  →  subclass builds visuals & anchors.
        3. If not in preview mode, self.register_sensors() is called
           so the subclass can register with the sensor registry.

    Typical setup() implementation:
        def setup(self):
            self.initialize_body_visuals()   # sets self.width/height
            self.initialize_anchors()        # uses self.width/height
            self.initialize_actuators()      # or initialize_sensors() / initialize_label()

    ── Simulation contract ─────────────────────────────────────────────────
    SimulationSession / SimulationController interact with nodes through
    exactly three entry points:

        simulation_mode = True
            Set by SimulationSession before the simulation starts.
            Use on_simulation_activated() to react (optional hook).

        update_from_domain(domain_node)
            Called by SimulationController each simulation step.
            Base implementation updates hydraulic anchor labels.
            Subclasses call super() and then update their own visuals.

        reset_visual_state()
            Called by SimulationSession when simulation stops.
            Base implementation resets simulation_mode, visual_offset,
            body_state, and calls update_body_visuals() if it exists.
            Subclasses that own a pixmap_default must override and
            reset self.pixmap.

    ── User → simulation channel ───────────────────────────────────────────
    To send a command from a user interaction (e.g. button click) to the
    simulation controller, emit:

        self.command.emit(self.id, {"action": "...", ...})

    The signal is connected to the controller by SimulationSession.

    ── Properties & serialisation ──────────────────────────────────────────
    Persistent configuration lives in self.properties (dict).
    apply_properties() must reconstruct the full visual state from
    self.properties — it is called after deserialisation and after the
    user closes the properties dialog.
    """

    # ── Class-level registry (populated automatically by __init_subclass__) ──
    class_registry: dict[str, type] = {}

    # ── Signals ─────────────────────────────────────────────────────────────
    command = pyqtSignal(str, dict)  # (node_id, payload)

    # ── Subclass must declare ────────────────────────────────────────────────
    node_type: str = None
    simulation_cls: type = None

    @classmethod
    def palette_meta(cls) -> "PaletteMeta | None":
        """Returns palette metadata for this node type.

        Return a ``PaletteMeta`` instance so the node automatically
        appears in the palette. Base (abstract) classes don't need to
        override this -- the ``None`` default excludes them from
        auto-discovery.

        Example::

            @classmethod
            def palette_meta(cls):
                return PaletteMeta(
                    domains=("pneumatic", "hydraulic"),
                    sprite=cls.BODY_VISUALS[0]["sprite"],
                    name="Valve 3/2 Ways",
                )
        """
        return None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        NodeItem.class_registry[cls.__name__] = cls

    # ── Infrastructure init (do not override) ────────────────────────────────
    def __init__(self, *args, domain: str | None = None,
                 sensor_registry: SensorRegistry | None = None,
                 _loading: bool = False, **kwargs):
        DiagramItemBase.__init__(self)

        # Identity & topology
        self.id: str = str(uuid.uuid4())
        self.domain: str | None = domain
        self.sensor_registry: SensorRegistry | None = sensor_registry
        self.anchors: dict[str, AnchorItem] = {}
        self.connections: list = []

        # Labels
        self.labels: dict[str, LabelItem] = {}
        self.special_labels: dict[str, LabelItem] = {}

        # Visual state
        self.simulation_mode: bool = False
        self.use_light_theme: bool = False
        self.pixmap: QPixmap | None = None
        self.draw_selection: bool = True
        self._visual_offset: QPointF = QPointF(0, 0)

        # Reference to the most recent domain node (updated each
        # simulation step by update_from_domain) and the active-defect
        # indicator, used by build_defect_dialog()/apply_defect_from_dialog()
        # and by paint_selection_feedback() in DiagramItemBase.
        self._domain_node = None
        self._defect_indicator: bool = False

        # Flags
        self.is_preview: bool = False
        # True only when reconstructed via from_dict (file load, undo/redo
        # restore, clipboard paste) -- PairedTerminalItem uses this to skip
        # spawning its paired far end on those paths.
        self._loading: bool = _loading
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

        # Let the subclass build its visuals and anchors
        self.setup()

        # Register sensors/actuators only for real (non-preview) instances
        if not self.is_preview:
            self.register_sensors()

    # ══════════════════════════════════════════════════════════════════════════
    # Lifecycle hooks  (override in subclasses)
    # ══════════════════════════════════════════════════════════════════════════

    def setup(self) -> None:
        """Build visuals and anchors.

        Call order must be:
            initialize_body_visuals()  →  sets self.width / self.height
            initialize_anchors()       →  positions depend on width/height
            initialize_actuators() / initialize_sensors() / initialize_label()

        This method replaces __init__ in subclasses.
        """

    def register_sensors(self) -> None:
        """Register this node's sensors/actuators with the sensor registry.

        Called once after setup(), only for non-preview instances.
        Override in subclasses that own sensors (CoilItem, CylinderItem, …).
        Default: no-op.
        """

    # ══════════════════════════════════════════════════════════════════════════
    # Simulation contract
    # ══════════════════════════════════════════════════════════════════════════

    def update_from_domain(self, domain_node) -> None:
        """Update visuals from the domain node state (called each sim step).

        Base handles hydraulic anchor pressure/flow labels, caches the
        domain node reference (used by build_defect_dialog() to read live
        values), and refreshes the defect indicator.
        Subclasses call super() then update their own visual state.
        """
        self._domain_node = domain_node
        self._defect_indicator = bool(getattr(domain_node, "defect_active", False))

        for name, anchor in self.anchors.items():
            domain_anchor = domain_node.anchors.get(name)
            if domain_anchor and domain_anchor.domain == "hydraulic":
                anchor.pressure = domain_anchor.pressure
                anchor.flow = domain_anchor.flow
                anchor.update_hydraulic_labels()

    def reset_visual_state(self) -> None:
        """Return to editor state after simulation stops.

        Base resets simulation_mode, visual_offset, and body_state,
        then calls update_body_visuals() if the subclass defines it.

        Override when the subclass holds extra visual state that must
        be reset (e.g. a non-default pixmap).  Always call super().
        """
        self.simulation_mode = False
        self._domain_node = None
        self._defect_indicator = False

        for anchor in self.anchors.values():
            if anchor.domain == "hydraulic":
                anchor.pressure = 0.0
                anchor.flow = 0.0
                anchor.update_hydraulic_labels()

        if hasattr(self, "initialize_actuators"):
            self.initialize_actuators()

        if hasattr(self, "update_body_visuals"):
            props = getattr(self, "properties", {})
            if "default_side" in props:
                if getattr(self, "THREE_POSITION", False):
                    self.body_state = THREE_POSITION_SIDE_MAP.get(props["default_side"], 1)
                else:
                    self.body_state = 1 if props["default_side"] == "left" else 0
            elif "default_state" in props:
                self.body_state = 1 if props["default_state"] == "extended" else 0
            else:
                self.body_state = 0
            self.update_body_visuals()

        if hasattr(self, "update_actuators_visuals"):
            self.update_actuators_visuals()
        elif hasattr(self, "update_anchor_positions"):
            self.update_anchor_positions()

        self.update()

    def on_simulation_activated(self) -> None:
        """Called when simulation mode is enabled (optional hook).

        SimulationSession sets self.simulation_mode = True directly;
        this hook gives subclasses a chance to react (e.g. hide edit
        buttons).  Default: no-op.
        """

    # ══════════════════════════════════════════════════════════════════════════
    # Properties & serialisation
    # ══════════════════════════════════════════════════════════════════════════

    def apply_properties(self) -> None:
        """Reconstruct full visual state from self.properties.

        Called after deserialisation (from_dict) and after the user
        confirms the properties dialog.  Subclasses must override and
        rebuild whatever setup() built originally.
        """

    def build_properties_dialog(self) -> PropertiesDialog | None:
        """Return a PropertiesDialog for this node, or None if no properties."""
        return None

    def apply_properties_from_dialog(self, dialog: PropertiesDialog) -> None:
        """Read values from dialog and apply them (called on dialog accept)."""

    def build_defect_dialog(self) -> DefectDialog | None:
        """Return a DefectDialog for this node during simulation, or None.

        Unlike build_properties_dialog(), this is read during simulation
        (simulation_mode=True) and must reflect LIVE domain state -- use
        self._domain_node (cached by update_from_domain) to prefill fields,
        never self.properties. Default: no defect dialog (opt-in per subclass).
        """
        return None

    def apply_defect_from_dialog(self, dialog: DefectDialog) -> None:
        """Read values from an accepted DefectDialog and emit a command.

        Must emit self.command with {"action": "set_defect", ...} or
        {"action": "clear_defect"} -- never mutate self.properties (defect
        state is transient, tied to the current simulation session only).
        """

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.__class__.__name__,
            "domain": self.domain,
            "position": {"x": self.pos().x(), "y": self.pos().y()},
            "rotation": self.rotation(),
            "properties": copy.deepcopy(getattr(self, "properties", {})),
            "labels": self.labels_to_dict(),
            "anchor_labels": self.anchor_labels_to_dict(),
        }

    def anchor_labels_to_dict(self) -> dict:
        """Serializes the hydraulic labels' position (relative to the anchor).

        These labels are children of the AnchorItem (not of
        self.labels), since they follow their anchor individually --
        that's why they need their own serialization key.
        """
        data = {}
        for name, anchor in self.anchors.items():
            label = getattr(anchor, "_label_hydraulic", None)
            if label is not None:
                data[name] = {"x": label.pos().x(), "y": label.pos().y()}
        return data

    def labels_to_dict(self) -> dict:
        data = {}
        for key, label in self.labels.items():
            props = {}
            for k, v in label.properties.items():
                if callable(v):
                    props[k] = v.__name__
                elif isinstance(v, Qt.GlobalColor):
                    props[k] = v.name.lower()
                else:
                    props[k] = v
            data[key] = {
                "pos": {"x": label.pos().x(), "y": label.pos().y()},
                "properties": props,
            }
        return data

    @classmethod
    def from_dict(cls, data: dict, *, keep_id: bool = True,
                  sensor_registry: SensorRegistry | None = None) -> "NodeItem":
        node_cls = cls.class_registry[data["type"]]
        node = node_cls(domain=data["domain"], sensor_registry=sensor_registry, _loading=True)

        if keep_id:
            node.id = data["id"]

        pos = data["position"]
        node.setPos(float(pos["x"]), float(pos["y"]))

        rotation = data.get("rotation", 0.0)
        if rotation:
            node.setTransformOriginPoint(node.width / 2, node.height / 2)
            node.setRotation(rotation)
            steps = int(round(rotation / 90)) % 4
            if steps:
                node._apply_exit_direction_rotation(steps)
            for anchor in node.anchors.values():
                anchor.reposition_hydraulic_label()
            node._counter_rotate_labels()

        for key, label_data in data.get("labels", {}).items():
            props = dict(label_data["properties"])
            for color_key in ("color", "border_color"):
                if color_key in props and isinstance(props[color_key], str):
                    props[color_key] = {
                        c.name.lower(): c for c in Qt.GlobalColor
                    }.get(props[color_key], Qt.GlobalColor.white)

            label = LabelItem(properties=props)
            label.setPos(QPointF(label_data["pos"]["x"], label_data["pos"]["y"]))
            node.add_label(key, label, special=False)

        node.properties = data.get("properties", {})
        node.apply_properties()

        # Applied after apply_properties(): some subclasses recreate
        # their anchors there (e.g. a port-count change), which would
        # replace the existing AnchorItems and discard the position
        # restored above.
        for name, pos in data.get("anchor_labels", {}).items():
            anchor = node.anchors.get(name)
            label = getattr(anchor, "_label_hydraulic", None) if anchor else None
            if label is not None:
                label.setPos(QPointF(float(pos["x"]), float(pos["y"])))

        return node

    # Clockwise 90° rotation map for exit direction labels.
    _DIR_CW90 = {"top": "right", "right": "bottom", "bottom": "left", "left": "top"}

    def rotate(self, degrees: float = 90.0) -> None:
        """Rotate the node by *degrees* clockwise around its visual centre.

        The transform origin is pinned to the centre of the bounding rect so
        the node appears to spin in place.  Anchors, labels, and all other
        child items are rotated automatically by Qt.

        exit_directions on every anchor are also rotated so the A* router
        always receives directions consistent with the new orientation.
        Only multiples of 90° are supported for direction mapping.

        Args:
            degrees: Clockwise rotation step in degrees (default 90).
        """
        self.setTransformOriginPoint(self.width / 2, self.height / 2)
        self.setRotation((self.rotation() + degrees) % 360)

        steps = int(round(degrees / 90)) % 4
        if steps:
            self._apply_exit_direction_rotation(steps)

        for anchor in self.anchors.values():
            anchor.reposition_hydraulic_label()

        self._counter_rotate_labels()

        self.update_connections()

    def _counter_rotate_labels(self) -> None:
        """Cancels the node's rotation on each child label, keeping the
        text always upright.

        Unlike ItemIgnoresTransformations (deliberately not used by
        LabelItem -- see the comment there), this only neutralizes the
        inherited ROTATION; position and scale (the view's zoom) still
        follow Qt's normal transformation chain.
        """
        angle = -self.rotation()
        for label in self.labels.values():
            label.setRotation(angle)
        for label in self.special_labels.values():
            label.setRotation(angle)
        for anchor in self.anchors.values():
            hydraulic_label = getattr(anchor, "_label_hydraulic", None)
            if hydraulic_label is not None:
                hydraulic_label.setRotation(angle)

    def _apply_exit_direction_rotation(self, steps: int) -> None:
        """Rotate exit_directions on all anchors by *steps* clockwise 90° turns."""
        for anchor in self.anchors.values():
            if not anchor.exit_directions:
                continue
            rotated = {}
            for key, dirs in anchor.exit_directions.items():
                current = list(dirs)
                for _ in range(steps):
                    current = [self._DIR_CW90.get(d, d) for d in current]
                rotated[key] = current
            anchor.exit_directions = rotated

    # ══════════════════════════════════════════════════════════════════════════
    # Anchor & label management
    # ══════════════════════════════════════════════════════════════════════════

    def add_anchor(self, anchor: AnchorItem) -> None:
        existing = self.anchors.get(anchor.name)
        if existing:
            existing.setPos(anchor.pos())
            anchor.setParentItem(None)
            return
        anchor.setParentItem(self)
        self.anchors[anchor.name] = anchor

    def remove_anchor(self, name: str) -> None:
        """Removes the `name` anchor and any connection attached to it.

        Confirmed by a real repro (2026-08): removing the anchor and its
        connection synchronously -- even with prepare_delete()+removeItem()
        done immediately -- is a timing-sensitive race that can leave
        the QGraphicsScene's spatial index (BSP) inconsistent, crashing
        the process with a "Windows fatal exception: access violation"
        on a subsequent real mouseMoveEvent (the crash disappears when
        any debug instrumentation that delays the event loop is added,
        the classic signature of this kind of race). Not reproducible
        with synthetic QTest -- only with a real mouse.

        Mitigation: follow the EXACT pattern already used by
        editor/delete_manager.py (DeleteManager.do_delete()) for the
        same problem -- defer EVERYTHING (bookkeeping + physical
        removal) as a single atomic unit via QTimer.singleShot(0, ...),
        and force a rebuild of the scene's spatial index afterward. The
        anchor disappears from self.anchors immediately (other methods
        like hydraulic_ports() can still count on that once this call
        returns), but the connection is only disconnected
        (prepare_delete) and removed from the scene on the next
        event-loop cycle -- exactly like a DeleteManager deletion.
        """
        anchor = self.anchors.pop(name, None)
        if not anchor:
            return

        matched_connections = [
            conn for conn in self.connections[:]
            if conn.source_anchor == anchor or conn.target_anchor == anchor
        ]

        def _do_remove():
            for conn in matched_connections:
                conn.prepare_delete()
            for conn in matched_connections:
                if conn.scene():
                    conn.scene().removeItem(conn)
            scene = anchor.scene()
            if scene:
                scene.removeItem(anchor)
                # Forces a rebuild of the spatial index (BSP) -- same
                # dance used in DeleteManager.do_delete() after removing
                # items from the scene.
                current_index = scene.itemIndexMethod()
                scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
                scene.setItemIndexMethod(current_index)
                scene.update()

        QTimer.singleShot(0, _do_remove)

    def add_label(self, key: str, label: LabelItem, special: bool = False) -> None:
        """Add a label to this node.

        Args:
            key:     Logical identifier (e.g. 'sensor_retracted').
            label:   LabelItem instance.
            special: If True, stored in self.special_labels (not serialised).
        """
        label_dict = self.special_labels if special else self.labels
        existing = label_dict.get(key)
        if existing:
            existing.setPlainText(label.toPlainText())
            existing.setPos(label.pos())
            return
        label.setParentItem(self)
        label_dict[key] = label
        label.setRotation(-self.rotation())

    def remove_label(self, key: str, special: bool = False) -> None:
        label_dict = self.special_labels if special else self.labels
        label = label_dict.pop(key, None)
        if label and label.scene():
            label.scene().removeItem(label)

    def prepare_delete(self) -> None:
        """Clean up before removal from scene."""
        self.connections.clear()
        self.unregister_sensors()

    def unregister_sensors(self) -> None:
        """Unregister all sensors from the registry.

        Base implementation handles the common pattern where subclasses
        store sensors in self.sensors as {key: {"name": str}}.
        Override if the structure differs.
        """
        if hasattr(self, "sensors") and self.sensor_registry:
            for sensor in self.sensors.values():
                name = sensor.get("name") if isinstance(sensor, dict) else None
                if name:
                    self.sensor_registry.unregister(name)

    # ══════════════════════════════════════════════════════════════════════════
    # Qt event hooks
    # ══════════════════════════════════════════════════════════════════════════

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.update_connections()

        elif change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            if self.editor and hasattr(self.editor, "theme_changed"):
                try:
                    self.editor.theme_changed.disconnect(self.on_theme_changed)
                except (TypeError, RuntimeError):
                    pass
                self.editor.theme_changed.connect(self.on_theme_changed)
                # Syncs with the current theme: the item may have been
                # created after the last toggle, never having received
                # the signal.
                self.on_theme_changed(getattr(self.editor, "is_light_theme", False))

        return super().itemChange(change, value)

    def on_theme_changed(self, is_light: bool) -> None:
        self.use_light_theme = is_light
        if hasattr(self, "_pixmap_cache"):
            self._pixmap_cache.clear()
        for label in (*self.labels.values(), *self.special_labels.values()):
            label.apply_theme(is_light)
        for anchor in self.anchors.values():
            hydraulic_label = getattr(anchor, "_label_hydraulic", None)
            if hydraulic_label is not None:
                hydraulic_label.apply_theme(is_light)
        self.update()

    def update_connections(self) -> None:
        for conn in self.connections[:]:
            if conn.source_anchor.scene() is None or conn.target_anchor.scene() is None:
                continue
            conn.adjust_waypoints_for_node_move(moved_source=conn.source is self, moved_target=conn.target is self)
            conn.prepareGeometryChange()
            conn.update()

    def mouseDoubleClickEvent(self, event) -> None:
        if self.simulation_mode:
            event.ignore()
            return
        dialog = self.build_properties_dialog()
        if dialog is None:
            event.ignore()
            return

        # Captures a snapshot before opening the dialog -- only pushed if the user confirms
        scene = self.scene()
        undo_stack = getattr(getattr(self, "editor", None), "undo_stack", None)
        before = undo_stack.snapshot(scene) if (undo_stack and scene) else None

        if dialog.exec():
            self.apply_properties_from_dialog(dialog)
            if before is not None:
                # Deferred (same QTimer.singleShot(0, ...) queue used by
                # remove_anchor()): if apply_properties_from_dialog() just
                # scheduled an anchor/connection removal, that callback
                # was queued BEFORE this one -- it runs first, guaranteeing
                # the "after" snapshot sees the scene already fully
                # settled, with no half-finished connection.
                editor = self.editor
                QTimer.singleShot(
                    0,
                    lambda: undo_stack.push_snapshot(scene, editor, before, "Editar propriedades"),
                )

        event.accept()

    # ══════════════════════════════════════════════════════════════════════════
    # Rendering
    # ══════════════════════════════════════════════════════════════════════════

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.save()
        painter.translate(self._visual_offset)

        if self.pixmap and not self.pixmap.isNull():
            scaled = self.pixmap.scaled(
                self.width, self.height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            pos = QPointF(
                (self.width - scaled.width()) / 2,
                (self.height - scaled.height()) / 2,
            )
            self.draw_pixmap(painter, pos, scaled)

        self.paint_selection_feedback(painter)
        painter.restore()

    def draw_pixmap(self, painter: QPainter, pos: QPointF, pixmap: QPixmap) -> None:
        if not pixmap or pixmap.isNull():
            return

        if not self.use_light_theme:
            painter.drawPixmap(pos, pixmap)
            return

        painter.drawPixmap(pos, recolor_pixmap_black(pixmap))

    # ── visual_offset property (used by Qt animations) ───────────────────────
    def getVisualOffset(self) -> QPointF:
        return self._visual_offset

    def setVisualOffset(self, value: QPointF) -> None:
        self._visual_offset = value
        self.update()

    visual_offset = pyqtProperty(QPointF, fget=getVisualOffset, fset=setVisualOffset)

    def apply_preview_constraints(self) -> None:
        """Configure node for palette preview (ghost-dragging mode)."""
        self.is_preview = True
        self.setOpacity(0.5)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

    # ══════════════════════════════════════════════════════════════════════════
    # Context menu
    # ══════════════════════════════════════════════════════════════════════════

    def extend_context_menu(self, menu: QMenu) -> None:
        if self.simulation_mode:
            # Simulation running: project editing (rotate, labels,
            # properties) becomes unavailable -- only the defect entry,
            # explicitly simulation-aware, is offered.
            defect_dialog = self.build_defect_dialog()
            if defect_dialog is not None:
                defect_action = menu.addAction(
                    QCoreApplication.translate("NodeItem", "Simulate defect...")
                )
                defect_action.triggered.connect(lambda: self._open_defect_dialog(defect_dialog))
            super().extend_context_menu(menu)
            return

        props_action = menu.addAction(
            QCoreApplication.translate("NodeItem", "Properties...")
        )
        props_action.triggered.connect(self._open_properties_dialog)
        menu.addSeparator()

        rotate_action = menu.addAction(
            QCoreApplication.translate("NodeItem", "Rotate 90°")
        )
        rotate_action.setShortcut("R")

        def _rotate():
            undo_stack = getattr(getattr(self, "editor", None), "undo_stack", None)
            scene = self.scene()
            before = undo_stack.snapshot(scene) if (undo_stack and scene) else None
            self.rotate(90)
            if before is not None:
                undo_stack.push_snapshot(
                    scene, self.editor, before,
                    QCoreApplication.translate("NodeItem", "Rotate component"),
                )

        rotate_action.triggered.connect(_rotate)
        menu.addSeparator()

        add_label_action = menu.addAction(
            QCoreApplication.translate("NodeItem", "Add label")
        )

        def _add_label():
            label = LabelItem(properties={"editable": True, "movable": True, "border": False})
            shape_rect = self.shape().boundingRect()
            label.setPos(shape_rect.width() / 2, shape_rect.bottom() + 20)
            key = self._next_label_key()
            self.add_label(key, label, special=False)
            label._editing = True
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            label.setFocus()

        add_label_action.triggered.connect(_add_label)
        super().extend_context_menu(menu)

    def _open_properties_dialog(self) -> None:
        dialog = self.build_properties_dialog()
        if dialog is None:
            dialog = PropertiesDialog(title="Properties")
            dialog.add_no_properties_message()

        scene = self.scene()
        undo_stack = getattr(getattr(self, "editor", None), "undo_stack", None)
        before = undo_stack.snapshot(scene) if (undo_stack and scene) else None

        if dialog.exec():
            self.apply_properties_from_dialog(dialog)
            if before is not None:
                undo_stack.push_snapshot(scene, self.editor, before, "Editar propriedades")

    def _open_defect_dialog(self, dialog: DefectDialog) -> None:
        if dialog.exec():
            self.apply_defect_from_dialog(dialog)

    def _next_label_key(self) -> str:
        i = 0
        while f"label_{i}" in self.labels:
            i += 1
        return f"label_{i}"