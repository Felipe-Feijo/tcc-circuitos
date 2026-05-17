from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QGraphicsScene

from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem
from graphics.labels.label import LabelItem

class DeleteManager:
    """Manages deletion of nodes and connections from the scene."""
    
    def __init__(self, scene):
        self.scene = scene

    def delete_selection(self):
        # Waypoints têm prioridade: varrer todos os itens da cena (não só
        # os selecionados) pois a conexão fica deselecionada ao clicar num waypoint.
        for item in self.scene.items():
            if isinstance(item, ConnectionItem) and getattr(item, '_selected_wp', None) is not None:
                item._delete_waypoint(item._selected_wp)
                return True

        # Obtém todos os itens selecionados na cena
        items = list(self.scene.selectedItems())

        if not items:
            return False

        # Separa conexões, nodes e labels
        connections = {i for i in items if isinstance(i, ConnectionItem)}
        nodes       = [i for i in items if isinstance(i, NodeItem)]
        labels      = [i for i in items if isinstance(i, LabelItem)]

        # Adiciona conexões de nodes selecionados
        for node in nodes:
            node_conns = getattr(node, "connections", [])
            connections.update(node_conns)

        connections = list(connections)

        def do_delete():
            """Deferred deletion to avoid Qt event handling issues."""

            for label in labels:
                parent = label.parentItem()
                if parent and hasattr(parent, "labels"):
                    key = next((k for k, v in parent.labels.items() if v is label), None)
                    if key:
                        parent.labels.pop(key)
                if label.scene():
                    self.scene.removeItem(label)

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

            current_index = self.scene.itemIndexMethod()
            self.scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
            self.scene.setItemIndexMethod(current_index)

            self.scene.update()

        # Defer deletion to next event loop iteration
        QTimer.singleShot(0, do_delete)
        return True