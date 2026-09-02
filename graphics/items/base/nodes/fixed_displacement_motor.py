"""Fixed-displacement hydraulic motor graphics node."""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QCoreApplication
from PyQt6.QtWidgets import QLabel
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
            name=QCoreApplication.translate("FixedDisplacementMotor", "Fixed Displacement Motor"),
        )

    def setup(self) -> None:
        self.properties = {"control_mode": "torque"}
        self.pixmap = QPixmap("resources/nodes/fixed_displacement_motor/fixed_displacement_motor.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        # A (top) -- reference input, where the sprite's triangle points.
        # B (bottom) -- reference output.
        self.add_anchor(AnchorItem("A", QPointF(self.width*28/84, 0), node=self, domain=self.domain, exit_directions={"external": ["top", "right", "left"]}))
        self.add_anchor(AnchorItem("B", QPointF(self.width*28/84, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom", "right", "left"]}))

        self._init_output_label()

    # ------------------------------------------------------------------
    # Output label (omega or T, depending on control_mode -- same
    # scheme as the piston velocity in cylinder_item.py)
    # ------------------------------------------------------------------

    def _init_output_label(self):
        self._label_output = LabelItem(properties={
            "text": "ω: 0 rad/s",
            "editable": False,
            "movable": True,
            "border": False,
            "font_delta": -1,
        })
        self._label_output.setParentItem(self)
        self._label_output.setPos(QPointF(self.width / 2, -18))

    def _reset_output_label_for_mode(self) -> None:
        """Shows the right label (omega or T) as soon as the mode is
        confirmed in the dialog (or loaded from a saved circuit) --
        without this, the text only switched once the simulation
        actually ran, staying stuck on the previous mode's label until then."""
        if not hasattr(self, "_label_output"):
            return
        mode = self.properties.get("control_mode", "torque")
        if mode == "torque":
            self._label_output.set_text("ω: 0 rad/s")
        else:
            self._label_output.set_text("T: 0 N·m")

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
        dialog = PropertiesDialog(title=self.tr("Fixed Displacement Motor — Properties"))
        if self.domain != "hydraulic":
            dialog._field_d = None
            dialog._combo_mode = None
            dialog._field_t = None
            dialog._field_omega = None
            dialog._field_p_max = None
            dialog._field_n_max = None
            return dialog

        dialog._field_d = dialog.add_number_field(
            self.tr("Displacement D (m³/rad)"), placeholder="ex: 1.5e-6",
            value=self.properties.get("D"),
            required=True,
        )
        dialog._combo_mode = dialog.add_combo_field(
            self.tr("Control mode"),
            [("torque", self.tr("Torque")), ("speed", self.tr("Speed"))],
            current=self.properties.get("control_mode", "torque"),
        )
        # required=False on both -- whether it's actually required
        # depends on control_mode (only one of the two applies at a
        # time), and the field hidden by conditional visibility still
        # counts toward the OK button's validation (which doesn't check
        # visible/hidden rows), locking OK if both were required=True.
        # Same pattern already used by the conditional timer fields in
        # directional_valve_item.py.
        dialog._field_t = dialog.add_number_field(
            self.tr("Load torque T_load (N·m)"), placeholder="ex: 50",
            value=self.properties.get("T_load"),
            required=False,
        )
        dialog._field_omega = dialog.add_number_field(
            self.tr("Target speed ω (rad/s)"), placeholder="ex: 100",
            value=self.properties.get("omega_target"),
            required=False,
        )

        # P_max/n_max are optional and independent of control_mode --
        # structural motor limits (bearing, seal), not conversion
        # physics. required=False -- absence is a valid choice (no
        # check), not a fill-in error.
        dialog._field_p_max = dialog.add_number_field(
            self.tr("Limit P_max (Pa) — optional"), placeholder="ex: 1e7",
            value=self.properties.get("P_max"),
            required=False,
        )
        dialog._field_n_max = dialog.add_number_field(
            self.tr("Limit n_max (rad/s) — optional"), placeholder="ex: 300",
            value=self.properties.get("n_max"),
            required=False,
        )

        dialog._preview_label = QLabel("—")
        dialog._form_layout.addRow(self.tr("Calculated requirement"), dialog._preview_label)

        def _update_mode_visibility(mode: str) -> None:
            form = dialog._form_layout
            for row in range(form.rowCount()):
                item = form.itemAt(row, form.ItemRole.FieldRole)
                if not item:
                    continue
                widget = item.widget()
                if widget is dialog._field_t:
                    form.setRowVisible(row, mode == "torque")
                elif widget is dialog._field_omega:
                    form.setRowVisible(row, mode == "speed")

        def _update_preview(*_args) -> None:
            try:
                d = float(dialog._field_d.text())
            except ValueError:
                dialog._preview_label.setText("—")
                return

            mode = dialog._combo_mode.currentData()
            try:
                if mode == "torque":
                    t_load = float(dialog._field_t.text())
                    delta_p = t_load / d
                    dialog._preview_label.setText(self.tr("Required Δp: {0:.3g} Pa").format(delta_p))
                else:
                    omega_target = float(dialog._field_omega.text())
                    q = d * omega_target
                    dialog._preview_label.setText(self.tr("Required flow rate: {0:.3g} m³/s").format(q))
            except (ValueError, ZeroDivisionError):
                dialog._preview_label.setText("—")

        dialog._combo_mode.currentIndexChanged.connect(
            lambda _i, combo=dialog._combo_mode: _update_mode_visibility(combo.currentData())
        )
        dialog._combo_mode.currentIndexChanged.connect(_update_preview)
        dialog._field_d.textChanged.connect(_update_preview)
        dialog._field_t.textChanged.connect(_update_preview)
        dialog._field_omega.textChanged.connect(_update_preview)

        _update_mode_visibility(dialog._combo_mode.currentData())
        _update_preview()

        return dialog

    def apply_properties_from_dialog(self, dialog) -> None:
        if dialog._field_d is None:
            return

        d_text = dialog._field_d.text().strip()
        self.properties["D"] = float(d_text) if d_text else None

        mode = dialog._combo_mode.currentData()
        self.properties["control_mode"] = mode

        if mode == "torque":
            t_text = dialog._field_t.text().strip()
            self.properties["T_load"] = float(t_text) if t_text else None
            self.properties["omega_target"] = None
        else:
            o_text = dialog._field_omega.text().strip()
            self.properties["omega_target"] = float(o_text) if o_text else None
            self.properties["T_load"] = None

        p_max_text = dialog._field_p_max.text().strip()
        self.properties["P_max"] = float(p_max_text) if p_max_text else None

        n_max_text = dialog._field_n_max.text().strip()
        self.properties["n_max"] = float(n_max_text) if n_max_text else None

        self._reset_output_label_for_mode()

    def apply_properties(self) -> None:
        self._reset_output_label_for_mode()
