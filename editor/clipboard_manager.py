import copy
import uuid
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.connections.connection_item import ConnectionItem
from persistence.serializer import serialize_scene, deserialize_scene

def _clear_sensor_names(nodes_data: list) -> None:
    """Clear sensor/actuator names from copied node data.

    Prevents duplicate sensor names when pasting — the registry will
    assign new unique names during register_sensors().
    """
    for node in nodes_data:
        props = node.get("properties", {})
        # cylinder pattern: {"sensors": {"retracted": {"name": ...}, ...}}
        for sensor in props.get("sensors", {}).values():
            if isinstance(sensor, dict):
                sensor["name"] = ""
        # coil pattern: {"sensor": {"coil": {"name": ...}}}
        for sensor in props.get("sensor", {}).values():
            if isinstance(sensor, dict):
                sensor["name"] = ""

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

    def has_data(self) -> bool:
        return self._data is not None

    def paste(self, scene, editor_state, offset=(20, 20)):
        """Paste copied nodes into scene.

        Args:
            scene: GraphicsScene
            editor_state: EditorState (NOT MainWindow)
            offset: pixel offset applied to pasted nodes
        """
        if not self._data:
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

        # 3. limpa nomes de sensores para evitar duplicatas no registry
        _clear_sensor_names(data["nodes"])

        # 4. desserializa
        created_items = deserialize_scene(data, scene, editor_state, clear_scene=False)

        # 4. seleção
        scene.clearSelection()

        for item in created_items:
            item.setSelected(True)
