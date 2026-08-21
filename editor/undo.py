"""Undo/redo module -- Command pattern using Qt's QUndoStack.

Every editor operation (add node, remove, move, connect, paste) is
wrapped in a SceneSnapshotCommand that stores JSON scene snapshots
before and after the operation.

Typical usage:
    before = undo_stack.snapshot(scene)   # BEFORE the operation
    # ... performs the operation ...
    undo_stack.push_snapshot(scene, editor_state, before, "Description")

Reference: https://doc.qt.io/qt-6/qundostack.html
"""

import copy

from PyQt6.QtGui import QUndoCommand, QUndoStack

from persistence.serializer import serialize_scene, deserialize_scene


def _restore_snapshot(snapshot: dict, scene, editor_state) -> None:
    """Restores the scene from a snapshot, resetting the SensorRegistry."""
    from graphics.sensor_registry.sensor_registry import SensorRegistry

    scene.sensor_registry = SensorRegistry()
    with scene.sensor_registry.loading():
        deserialize_scene(
            copy.deepcopy(snapshot),
            scene,
            editor_state,
            clear_scene=True,
        )


class SceneSnapshotCommand(QUndoCommand):
    """Generic command based on a full scene snapshot.

    The first redo() is suppressed because QUndoStack.push() calls it
    immediately -- but at that point the operation has already been
    applied to the scene, so reapplying the 'after' snapshot would
    destroy the in-memory state. From the second redo() onward (a real
    user redo), the snapshot is restored normally.
    """

    def __init__(self, scene, editor_state, before: dict, after: dict, text: str):
        super().__init__(text)
        self._scene = scene
        self._editor = editor_state
        self._before = before
        self._after = after
        self._first_redo = True  # suppresses push()'s automatic call

    def undo(self) -> None:
        _restore_snapshot(self._before, self._scene, self._editor)

    def redo(self) -> None:
        if self._first_redo:
            # push() calls redo() automatically -- the scene already has
            # the correct state, we don't need (or want) to restore the snapshot.
            self._first_redo = False
            return
        _restore_snapshot(self._after, self._scene, self._editor)


class UndoStack(QUndoStack):
    """QUndoStack extended with scene-snapshot helpers."""

    @staticmethod
    def snapshot(scene) -> dict:
        """Serializes the scene into a dict. Must be called *before* the operation."""
        return serialize_scene(scene)

    def push_snapshot(self, scene, editor_state, before: dict, text: str) -> None:
        """Captures the current state as 'after' and pushes the command.

        Must be called *after* the operation has been applied to the scene.
        """
        after = serialize_scene(scene)
        cmd = SceneSnapshotCommand(scene, editor_state, before, after, text)
        self.push(cmd)
