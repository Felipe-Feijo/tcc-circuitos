"""Nó gráfico de motor hidráulico de deslocamento fixo."""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF
from simulation.nodes.fixed_displacement_motor import FixedDisplacementMotor as FixedDisplacementMotorNode

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.utils.properties_dialog import PropertiesDialog
from graphics.labels.label import LabelItem
from ....anchors.anchor import AnchorItem


class FixedDisplacementMotor(NodeItem):
    node_type = "fixed_displacement_motor"
    simulation_cls = FixedDisplacementMotorNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("hydraulic",),
            sprite="resources/nodes/fixed_displacement_motor/fixed_displacement_motor.png",
            name="Fixed Displacement Motor",
        )

    def setup(self) -> None:
        self.properties = {"control_mode": "torque"}
        self.pixmap = QPixmap("resources/nodes/fixed_displacement_motor/fixed_displacement_motor.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        # A (topo) -- entrada de referência, pra onde o triângulo do
        # sprite aponta. B (base) -- saída de referência.
        self.add_anchor(AnchorItem("A", QPointF(self.width*28/84, 0), node=self, domain=self.domain, exit_directions={"external": ["top", "right", "left"]}))
        self.add_anchor(AnchorItem("B", QPointF(self.width*28/84, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom", "right", "left"]}))

        self._init_output_label()

    # ------------------------------------------------------------------
    # Label de saída (ω ou T, conforme control_mode -- mesmo esquema da
    # velocidade do pistão em cylinder_item.py)
    # ------------------------------------------------------------------

    def _init_output_label(self):
        self._label_output = LabelItem(properties={
            "text": "ω: 0 rad/s",
            "editable": False,
            "movable": True,
            "border": False,
            "font_size": 8,
        })
        self._label_output.setParentItem(self)
        self._label_output.setPos(QPointF(self.width / 2, -18))

    def _update_output_label(self, domain_node) -> None:
        try:
            mode = getattr(domain_node, "control_mode", "torque")
            d = getattr(domain_node, "D", None)
            if not d:
                return

            if mode == "torque":
                q_a = domain_node.anchors["A"].flow
                if isinstance(q_a, str):
                    return
                omega = q_a / d
                if abs(omega) < 1e-8:
                    omega = 0.0
                self._label_output.set_text(f"ω: {omega:.3g} rad/s")
            else:
                p_a = domain_node.anchors["A"].pressure
                p_b = domain_node.anchors["B"].pressure
                if isinstance(p_a, str) or isinstance(p_b, str):
                    return
                torque = (p_a - p_b) * d
                if abs(torque) < 1e-8:
                    torque = 0.0
                self._label_output.set_text(f"T: {torque:.3g} N·m")
        except (KeyError, TypeError, ZeroDivisionError):
            pass

    # ------------------------------------------------------------------
    # Simulation visual sync
    # ------------------------------------------------------------------

    def update_from_domain(self, domain_node) -> None:
        super().update_from_domain(domain_node)
        if self.domain == "hydraulic":
            self._update_output_label(domain_node)

    # ------------------------------------------------------------------
    # Properties dialog
    # ------------------------------------------------------------------

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title="Fixed Displacement Motor — Properties")
        if self.domain != "hydraulic":
            dialog._field_d = None
            dialog._combo_mode = None
            dialog._field_t = None
            dialog._field_omega = None
            return dialog

        dialog._field_d = dialog.add_number_field(
            "Deslocamento D (m³/rad)", placeholder="ex: 1.5e-6",
            value=self.properties.get("D"),
            required=True,
        )
        dialog._combo_mode = dialog.add_combo_field(
            "Modo de controle", ["torque", "speed"],
            current=self.properties.get("control_mode", "torque"),
        )
        dialog._field_t = dialog.add_number_field(
            "Torque de carga T_load (N·m)", placeholder="ex: 50",
            value=self.properties.get("T_load"),
            required=True,
        )
        dialog._field_omega = dialog.add_number_field(
            "Velocidade alvo ω (rad/s)", placeholder="ex: 100",
            value=self.properties.get("omega_target"),
            required=True,
        )

        def _update_mode_visibility(mode_text: str) -> None:
            form = dialog._form_layout
            for row in range(form.rowCount()):
                item = form.itemAt(row, form.ItemRole.FieldRole)
                if not item:
                    continue
                widget = item.widget()
                if widget is dialog._field_t:
                    form.setRowVisible(row, mode_text == "torque")
                elif widget is dialog._field_omega:
                    form.setRowVisible(row, mode_text == "speed")

        dialog._combo_mode.currentTextChanged.connect(_update_mode_visibility)
        _update_mode_visibility(dialog._combo_mode.currentText())

        return dialog

    def apply_properties_from_dialog(self, dialog) -> None:
        if dialog._field_d is None:
            return

        d_text = dialog._field_d.text().strip()
        self.properties["D"] = float(d_text) if d_text else None

        mode = dialog._combo_mode.currentText()
        self.properties["control_mode"] = mode

        if mode == "torque":
            t_text = dialog._field_t.text().strip()
            self.properties["T_load"] = float(t_text) if t_text else None
            self.properties["omega_target"] = None
        else:
            o_text = dialog._field_omega.text().strip()
            self.properties["omega_target"] = float(o_text) if o_text else None
            self.properties["T_load"] = None
