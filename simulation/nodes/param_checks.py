"""Range checks for node parameters, shared by __init__ and defect
validation (DefectMixin.validate_params).

Each raises ValueError with "<NodeClass> '<id>': property '<name>' must
be ..." so the GraphBuilder / defect log message names the culprit.
`not value > 0` (rather than `value <= 0`) also rejects NaN.
"""

from __future__ import annotations


def _fail(node, name, rule, value):
    raise ValueError(
        f"{type(node).__name__} '{node.id}': property '{name}' must be {rule}, got {value}."
    )


def require_positive(node, name: str, value: float) -> None:
    if not value > 0:
        _fail(node, name, "> 0", value)


def require_non_negative(node, name: str, value: float) -> None:
    if not value >= 0:
        _fail(node, name, ">= 0", value)
