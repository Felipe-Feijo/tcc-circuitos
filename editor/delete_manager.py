"""Manages the safe removal of nodes, connections and labels from the graphics scene."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QGraphicsScene

from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem
from graphics.labels.label import LabelItem


class DeleteManager:
    """Removes scene items safely, deferring deletion outside the Qt event cycle.

    Deleting immediately while processing an event can access invalid
    pointers. Using QTimer.singleShot(0, ...) guarantees removal only
    happens after the current event has been fully processed.
    """

    def __init__(self, scene):
        self.scene = scene

    def delete_selection(self, editor_state=None) -> bool:
        """Removes the currently selected items from the scene.

        Connection waypoints take priority: if any connection has a
        selected waypoint, only that waypoint is removed. Otherwise,
        removes every selected node, connection and label, including
        the selected nodes' transitive connections.

        Args:
            editor_state: Optional EditorState. When given, the
                operation is recorded on the undo_stack for Ctrl+Z support.

        Returns:
            True if any item was removed, False if there was no selection.
        """
        # Waypoints take priority: the connection gets deselected on
        # clicking a waypoint, so we scan every scene item, not just the selected ones.
        for item in self.scene.items():
            if isinstance(item, ConnectionItem) and getattr(item, '_selected_wp', None) is not None:
                item._delete_waypoint(item._selected_wp)
                return True

        items = list(self.scene.selectedItems())

        if not items:
            return False

        # Captures a snapshot BEFORE deletion, for undo
        before = None
        if editor_state is not None:
            from editor.undo import UndoStack
            before = UndoStack.snapshot(self.scene)

        connections = {i for i in items if isinstance(i, ConnectionItem)}
        nodes       = [i for i in items if isinstance(i, NodeItem)]
        labels      = [i for i in items if isinstance(i, LabelItem)]

        # Includes the selected nodes' connections (they'll be removed too)
        for node in nodes:
            connections.update(getattr(node, "connections", []))

        connections = list(connections)

        def do_delete():
            """Performs the actual removal, deferred outside the Qt event."""
            for label in labels:
                parent = label.parentItem()
                if parent and hasattr(parent, "labels"):
                    key = next((k for k, v in parent.labels.items() if v is label), None)
                    if key:
                        parent.labels.pop(key)
                if label.scene():
                    self.scene.removeItem(label)

            # Phase 1: notifies each item before removal (clears internal references)
            for conn in connections:
                conn.prepare_delete()

            for node in nodes:
                node.prepare_delete()

            # Phase 2: removes from the scene
            for item in connections + nodes:
                if item.scene():
                    self.scene.removeItem(item)

            connections.clear()
            nodes.clear()
            items.clear()

            # Forces a full visual update of the scene
            self.scene.invalidate(
                self.scene.sceneRect(),
                QGraphicsScene.SceneLayer.AllLayers
            )
            current_index = self.scene.itemIndexMethod()
            self.scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
            self.scene.setItemIndexMethod(current_index)
            self.scene.update()

            # Pushes the undo command AFTER the deletion is applied
            if editor_state is not None and before is not None:
                editor_state.undo_stack.push_snapshot(
                    self.scene,
                    editor_state,
                    before,
                    "Deletar itens",
                )

        QTimer.singleShot(0, do_delete)
        return True
