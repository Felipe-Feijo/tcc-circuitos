import copy
import uuid
from PyQt6.QtWidgets import QMessageBox
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.connections.connection_item import ConnectionItem
from persistence.serializer import serialize_scene, deserialize_scene

class ClipboardManager:
    def __init__(self):
        self._data = None

    def copy(self, scene):
        selected_nodes = [
            item for item in scene.selectedItems()
            if isinstance(item, NodeItem)
        ]

        if not selected_nodes:
            self._data = None
            return

        self._data = serialize_scene(scene, nodes=selected_nodes)
        print("Copied to clipboard:", self._data)

    def has_data(self) -> bool:
        return self._data is not None

    def paste(self, scene, editor, offset=(20, 20)):
        if not self._data:
            return
        
        if editor.mode == "simulate":
            QMessageBox.information(
                editor,
                "Simulação em execução",
                "Pare a simulação para editar o diagrama."
            )
            return

        data = copy.deepcopy(self._data)
        id_map = {}

        # 1. novos IDs + offset
        for node in data["nodes"]:
            old_id = node["id"]
            new_id = str(uuid.uuid4())

            id_map[old_id] = new_id
            node["id"] = new_id

            node["position"]["x"] += offset[0]
            node["position"]["y"] += offset[1]

        # 2. atualizar conexões
        for conn in data["connections"]:
            conn["source"]["node"] = id_map[conn["source"]["node"]]
            conn["target"]["node"] = id_map[conn["target"]["node"]]

        # 3. desserializa
        created_items = deserialize_scene(data, scene, editor, clear_scene=False)

        # 4. seleção
        scene.clearSelection()

        for item in created_items:
            item.setSelected(True)

        editor.cancel_current_mode()