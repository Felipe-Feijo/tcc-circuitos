from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QGraphicsScene

from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem

class DeleteManager:
    """Manages deletion of nodes and connections from the scene."""
    
    def __init__(self, scene):
        self.scene = scene

    def delete_selection(self):
        print("DeleteManager: delete_selection called")
        """
        Deletes all selected items from the scene.
        
        Deletion happens in two phases:
        1. prepare_delete() - Cleanup and disconnect from model
        2. removeItem() - Remove from scene
        
        Returns:
            bool: True if items were deleted, False if nothing was selected
        """
        items = list(self.scene.selectedItems())
        print("Selected:", items)
        if not items:
            return False

        # Collect connections (selected + those attached to selected nodes)
        connections = {i for i in items if isinstance(i, ConnectionItem)}
        nodes = [i for i in items if isinstance(i, NodeItem)]

        for node in nodes:
            connections.update(node.connections)

        connections = list(connections)

        def do_delete():
            """Deferred deletion to avoid Qt event handling issues."""
            
            # Phase 1: Prepare all items for deletion
            for conn in connections:
                conn.prepare_delete()

            for node in nodes:
                node.prepare_delete()

            # Phase 2: Remove items from scene
            for item in connections + nodes:
                if item.scene():
                    self.scene.removeItem(item)

            # Clear references
            connections.clear()
            nodes.clear()
            items.clear()

            # Force scene refresh
            self.scene.invalidate(
                self.scene.sceneRect(),
                QGraphicsScene.SceneLayer.AllLayers
            )
            self.scene.update()

        # Defer deletion to next event loop iteration
        QTimer.singleShot(0, do_delete)
        return True