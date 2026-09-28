"""Generic defect injection for simulation nodes.

A node opts in by inheriting DefectMixin ahead of Node and declaring
DEFECT_FIELDS, a {command_key: attribute_name} map:

    class DirectionalValve(DefectMixin, Node):
        DEFECT_FIELDS = {"k": "k", "stuck": "stuck_defect"}

The node initializes each attribute to its healthy value and its own
logic reads the attribute as usual -- the mixin knows nothing about
physics. It only handles the command protocol:

    {"action": "set_defect", <key>: value, ..., "note"?: str}
    {"action": "clear_defect", "note"?: str}

On set, each attribute's healthy value is snapshotted the first time
it's touched; clear restores every snapshotted attribute.
defect_active compares current values against that snapshot, so a
new defect never needs its own restore/detect code.

Defects are transient: never persisted to properties nor included in
get_state() (stepping backward doesn't undo them).
"""

from __future__ import annotations


def _coerce(original, value):
    if isinstance(original, bool):
        return bool(value)
    if original is None:
        return value
    return type(original)(value)


class DefectMixin:
    DEFECT_FIELDS: dict[str, str] = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._defect_originals: dict[str, object] = {}
        # Free-text note of the last set/clear command; FrameRecorder
        # uses it to label the report chart's defect markers.
        self.defect_note: str = ""

    def handle_command(self, command: dict):
        if not self.handle_defect_command(command):
            super().handle_command(command)

    def handle_defect_command(self, command: dict) -> bool:
        """Handles set_defect/clear_defect; returns True if consumed.

        Subclasses that override handle_command must call this first
        (they precede the mixin in the MRO).
        """
        action = command.get("action")
        if action == "set_defect":
            self._set_defect(command)
            return True
        if action == "clear_defect":
            self._clear_defect(command)
            return True
        return False

    def _set_defect(self, command: dict) -> None:
        for key, value in command.items():
            attr = self.DEFECT_FIELDS.get(key)
            if attr is None or not hasattr(self, attr):
                continue
            original = self._defect_originals.setdefault(attr, getattr(self, attr))
            setattr(self, attr, _coerce(original, value))
        self.defect_note = command.get("note", "")
        self._on_defect_changed()

    def _clear_defect(self, command: dict) -> None:
        for attr, original in self._defect_originals.items():
            setattr(self, attr, original)
        self._defect_originals.clear()
        self.defect_note = command.get("note", "")
        self._on_defect_changed()

    def _on_defect_changed(self) -> None:
        """Hook for nodes that recompute derived values after set/clear."""

    @property
    def defect_active(self) -> bool:
        return any(
            getattr(self, attr) != original
            for attr, original in self._defect_originals.items()
        )

    def defect_value(self, key: str):
        """Current value of the attribute mapped by `key` (None if unmapped/absent)."""
        attr = self.DEFECT_FIELDS.get(key)
        if attr is None:
            return None
        return getattr(self, attr, None)
