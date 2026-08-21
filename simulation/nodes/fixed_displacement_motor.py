"""Simulation node for the fixed-displacement hydraulic motor.

Mechanical inverse of FixedDisplacementPump: instead of converting
rotation into flow/pressure, it converts received flow/pressure into
shaft rotation/torque.

    Q = D * omega  (flow proportional to angular speed)
    T = D * dp     (torque proportional to pressure drop)

Design direction: A (top, where the sprite triangle points) is the
reference input; B (base) is the reference output. dp = P_A - P_B.
Positive Q_A and dp = operation in the design direction (matches the
sprite arrow).

Direction reversal needs no special handling: the motor equation never
depends on the SIGN of Q_A, only the rest of the circuit (conservation)
decides -- if the circuit pushes flow the other way, Q_A (and hence
omega=Q_A/D) comes out negative naturally, with no branching and no
risk of a spurious root (same care applied to the throttle valve fix).

Two mutually exclusive operating modes (properties["control_mode"]),
each defining which of the two properties (T_load or omega_target) is
required:

    "torque": properties["T_load"] (N*m) -- CONSTANT torque load,
        imposed regardless of rotation direction (not friction -- real
        friction always opposes the direction of omega, which would
        require sign(Q) and reintroduce the same kind of branching
        avoided here). Equation: dp = T_load / D.
        omega = Q_A/D is derived (computed on the graphics side from
        the resolved flow, same scheme as piston speed).

    "speed": properties["omega_target"] (rad/s) -- imposed target
        speed, like a servo. Equation: Q_A = D * omega_target (flow
        locked, same idea as FixedDisplacementPump).
        T = dp * D is derived (computed on the graphics side from the
        resolved pressure).

`D` is always required. Only one of the two fields (T_load /
omega_target) is required, depending on control_mode.

`P_max` (Pa) and `n_max` (rad/s) are OPTIONAL -- structural limits of
the real motor (bearing, seal, cavitation), not energy-conversion
physics (unlike the centrifugal pump curve, the T=D*dp / Q=D*omega
relation stays linear across the whole range; the limits only clamp
where it stops being valid). Only the deterministic side of each mode
can be validated at CONSTRUCTION time: T_load implies dp directly
(checked against P_max in torque mode); omega_target implies Q=D*omega
directly (checked against n_max in speed mode). The opposite side in
each mode (omega in torque mode, dp in speed mode) only emerges after
solving with the rest of the circuit -- not validated here.
"""

from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin


class FixedDisplacementMotor(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "fixed_displacement_motor", domain=domain, properties=properties)

        if self.domain == "hydraulic":
            d = self.properties.get("D")
            if d is None:
                raise ValueError(
                    f"FixedDisplacementMotor '{self.id}': required property 'D' is not set."
                )
            self.D = float(d)

            p_max = self.properties.get("P_max")
            self.P_max = float(p_max) if p_max is not None else None
            n_max = self.properties.get("n_max")
            self.n_max = float(n_max) if n_max is not None else None

            self.control_mode = self.properties.get("control_mode", "torque")
            if self.control_mode not in ("torque", "speed"):
                raise ValueError(
                    f"FixedDisplacementMotor '{self.id}': 'control_mode' must be 'torque' or 'speed', "
                    f"got {self.control_mode!r}."
                )

            if self.control_mode == "torque":
                t_load = self.properties.get("T_load")
                if t_load is None:
                    raise ValueError(
                        f"FixedDisplacementMotor '{self.id}': required property 'T_load' "
                        "is not set (control_mode='torque')."
                    )
                self.T_load = float(t_load)

                if self.P_max is not None:
                    implied_delta_p = abs(self.T_load / self.D)
                    if implied_delta_p > self.P_max:
                        raise ValueError(
                            f"FixedDisplacementMotor '{self.id}': T_load={self.T_load:.3g} N*m implies "
                            f"dp={implied_delta_p:.3g} Pa, above limit P_max={self.P_max:.3g} Pa."
                        )
            else:
                omega_target = self.properties.get("omega_target")
                if omega_target is None:
                    raise ValueError(
                        f"FixedDisplacementMotor '{self.id}': required property 'omega_target' "
                        "is not set (control_mode='speed')."
                    )
                self.omega_target = float(omega_target)

                if self.n_max is not None and abs(self.omega_target) > self.n_max:
                    raise ValueError(
                        f"FixedDisplacementMotor '{self.id}': omega_target={self.omega_target:.3g} rad/s "
                        f"above limit n_max={self.n_max:.3g} rad/s."
                    )

            self.flow_var_a = f"Q_{self.id}_A"
            self.flow_var_b = f"Q_{self.id}_B"

    @property
    def is_flow_source(self) -> bool:
        return True

    @property
    def flow_hint(self) -> float:
        if self.control_mode == "speed":
            return abs(self.D * self.omega_target)
        return 0.0

    @property
    def p_hint(self) -> float:
        if self.control_mode == "torque":
            return abs(self.T_load / self.D)
        return 0.0

    @property
    def variables(self):
        vars_ = [self.flow_var_a, self.flow_var_b]
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    @property
    def initial_guess(self):
        if self.control_mode == "speed":
            q = self.D * self.omega_target
            return {self.flow_var_a: q, self.flow_var_b: -q}
        return {self.flow_var_a: 1.0, self.flow_var_b: -1.0}

    def hydraulic_ports(self):
        return {
            "A": self.flow_var_a,
            "B": self.flow_var_b,
        }

    def equations(self, x, idx):
        Q_a = x[idx[self.flow_var_a]]
        Q_b = x[idx[self.flow_var_b]]

        Q_scale = max(self.q_ref, 1e-12)
        P_scale = max(self.p_ref, 1e-3)

        eq_conservation = (Q_a + Q_b) / Q_scale

        if self.control_mode == "torque":
            P_a = x[idx[self.anchors["A"].pressure_var]]
            P_b = x[idx[self.anchors["B"].pressure_var]]
            delta_p = P_a - P_b
            eq_mode = (delta_p - self.T_load / self.D) / P_scale
        else:
            eq_mode = (Q_a - self.D * self.omega_target) / Q_scale

        return [eq_conservation, eq_mode]
