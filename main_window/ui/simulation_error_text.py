"""Translated, user-facing text for errors returned by SimulationSession.start()."""

from PyQt6.QtCore import QCoreApplication

from graphics.items.base.nodes.node_item import NodeItem
from simulation.graph_builder import GraphBuildError
from simulation.nodes.param_checks import ParamError


def _templates() -> dict[str, str]:
    # Literal QCoreApplication.translate("SimulationErrors", ...) per code:
    # pylupdate6 doesn't see through an alias or a context constant.
    return {
        "missing_property": QCoreApplication.translate(
            "SimulationErrors", "{node}: required property '{key}' is not set."),
        "must_be_positive": QCoreApplication.translate(
            "SimulationErrors", "{node}: property '{key}' must be greater than 0 (got {value})."),
        "must_be_non_negative": QCoreApplication.translate(
            "SimulationErrors", "{node}: property '{key}' must be at least 0 (got {value})."),
        "conductance_negative": QCoreApplication.translate(
            "SimulationErrors", "{node}: property '{key}' must be at least 0, where 0 means fully blocked (got {value})."),
        "rod_not_smaller_than_bore": QCoreApplication.translate(
            "SimulationErrors", "{node}: rod diameter ({rod}) must be smaller than the bore diameter ({bore})."),
        "invalid_control_mode": QCoreApplication.translate(
            "SimulationErrors", "{node}: control mode must be 'torque' or 'speed' (got '{value}')."),
        "torque_exceeds_pressure_limit": QCoreApplication.translate(
            "SimulationErrors", "{node}: load torque {T_load} N·m requires {dp} Pa, above the limit P_max = {P_max} Pa."),
        "speed_exceeds_limit": QCoreApplication.translate(
            "SimulationErrors", "{node}: target speed {omega} rad/s is above the limit n_max = {n_max} rad/s."),
        "port_not_connected": QCoreApplication.translate(
            "SimulationErrors", "{node}: port '{port}' is not connected to anything."),
    }


def _fmt(value) -> str:
    return f"{value:.3g}" if isinstance(value, float) else str(value)


def _node_label(error: ParamError, scene) -> str:
    """Translated component type plus its user-given name, if any."""
    for item in scene.items():
        if isinstance(item, NodeItem) and item.id == error.node_id:
            meta = type(item).palette_meta()
            label = meta.name if meta else error.node_type
            return f"{label} '{item.name}'" if item.name else label
    return error.node_type


def _param_error_text(error: ParamError, scene, templates: dict[str, str]) -> str:
    template = templates.get(error.code)
    if template is None:
        return str(error)
    params = {k: _fmt(v) for k, v in error.params.items()}
    return template.format(node=_node_label(error, scene), **params)


def format_simulation_error(error: ValueError, scene) -> str:
    """One translated line per error; unknown errors fall back to str()."""
    errors = error.errors if isinstance(error, GraphBuildError) else [error]
    templates = _templates()
    return "\n".join(
        _param_error_text(e, scene, templates) if isinstance(e, ParamError) else str(e)
        for e in errors
    )
