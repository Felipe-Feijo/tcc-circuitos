"""Parameter errors and range checks for node parameters, shared by
__init__ and defect validation (DefectMixin.validate_params).

ParamError's str() reads "<NodeClass> '<id>': ..." so the GraphBuilder /
defect log message names the culprit; `code` and `params` let the UI build
a translated message instead.
`not value > 0` (rather than `value <= 0`) also rejects NaN.
"""

from __future__ import annotations


class ParamError(ValueError):
    """Invalid or missing node parameter (or wiring) detected before the solve."""

    _MESSAGES = {
        "missing_property": "required property '{key}' is not set.",
        "must_be_positive": "property '{key}' must be > 0, got {value}.",
        "must_be_non_negative": "property '{key}' must be >= 0, got {value}.",
        "conductance_negative":
            "property '{key}' must be >= 0 (0 = fully blocked), got {value}.",
        "rod_not_smaller_than_bore":
            "property 'rod_diameter' must be < bore ({bore}), got {rod}.",
        "invalid_control_mode":
            "'control_mode' must be 'torque' or 'speed', got {value!r}.",
        "torque_exceeds_pressure_limit":
            "T_load={T_load:.3g} N*m implies dp={dp:.3g} Pa, above limit P_max={P_max:.3g} Pa.",
        "speed_exceeds_limit":
            "omega_target={omega:.3g} rad/s above limit n_max={n_max:.3g} rad/s.",
        "port_not_connected": "port '{port}' is not connected to anything.",
    }

    def __init__(self, node, code: str, **params):
        self.node_id = node.id
        self.node_type = type(node).__name__
        self.code = code
        self.params = params
        super().__init__(
            f"{self.node_type} '{self.node_id}': " + self._MESSAGES[code].format(**params)
        )


def require_property(node, key: str):
    """Returns node.properties[key], raising ParamError if it's unset."""
    value = node.properties.get(key)
    if value is None:
        raise ParamError(node, "missing_property", key=key)
    return value


def require_positive(node, name: str, value: float) -> None:
    if not value > 0:
        raise ParamError(node, "must_be_positive", key=name, value=value)


def require_non_negative(node, name: str, value: float) -> None:
    if not value >= 0:
        raise ParamError(node, "must_be_non_negative", key=name, value=value)
