from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QGraphicsScene

from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem

class DeleteManager:
    """Manages deletion of nodes and connections from the scene."""
    
    def __init__(self, scene):
        self.scene = scene

    def delete_selection(self):
        print("=== DeleteManager: delete_selection called ===")
        
        # Obtém todos os itens selecionados na cena
        items = list(self.scene.selectedItems())
        print(f"Selected items ({len(items)}): {items}")
        
        if not items:
            print("No items selected, exiting.")
            return False

        # Separa conexões e nodes
        connections = {i for i in items if isinstance(i, ConnectionItem)}
        nodes = [i for i in items if isinstance(i, NodeItem)]

        # Adiciona conexões de nodes selecionados
        for node in nodes:
            node_conns = getattr(node, "connections", [])
            print(f"Node {getattr(node, 'id', node)} connections to consider: {node_conns}")
            connections.update(node_conns)

        connections = list(connections)
        print(f"Total connections to delete ({len(connections)}): {connections}")
        print(f"Total nodes to delete ({len(nodes)}): {nodes}")

        def do_delete():
            """Deferred deletion to avoid Qt event handling issues."""
            print("\n--- do_delete START ---")

            # Phase 1: Prepare all items for deletion
            print("\nPhase 1: prepare_delete connections")
            for conn in connections:
                print(f"Preparing connection for deletion: {conn} (source: {getattr(conn, 'source_anchor', None)}, target: {getattr(conn, 'target_anchor', None)})")
                conn.prepare_delete()

            print("\nPhase 1: prepare_delete nodes")
            for node in nodes:
                print(f"Preparing node for deletion: {getattr(node, 'id', node)}")
                node.prepare_delete()

            # Phase 2: Remove items from scene
            print("\nPhase 2: removing items from scene")
            for item in connections + nodes:
                if item.scene():
                    print(f"Removing {item} from scene")
                    self.scene.removeItem(item)
                else:
                    print(f"{item} is not in scene")

            # Clear references
            print("\nClearing lists")
            connections.clear()
            nodes.clear()
            items.clear()

            # Force scene refresh
            print("\nInvalidating and updating scene")
            self.scene.invalidate(
                self.scene.sceneRect(),
                QGraphicsScene.SceneLayer.AllLayers
            )

            current_index = self.scene.itemIndexMethod()
            self.scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
            self.scene.setItemIndexMethod(current_index)
            
            self.scene.update()
            print("--- do_delete END ---\n")

        # Defer deletion to next event loop iteration
        print("Scheduling deferred deletion (QTimer.singleShot)")
        QTimer.singleShot(0, do_delete)
        return True