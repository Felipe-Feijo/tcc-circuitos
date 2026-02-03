import json
from pathlib import Path

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.connections.connection_item import ConnectionItem

def serialize_scene(scene, *, nodes=None) -> dict:
    if nodes is None:
        nodes = [
            item for item in scene.items()
            if isinstance(item, NodeItem)
        ]

    node_set = set(nodes)

    nodes_data = [node.to_dict() for node in nodes]

    connections_data = []

    for item in scene.items():
        if not isinstance(item, ConnectionItem):
            continue

        # 🔒 ignora conexões incompletas
        if not item.source_anchor or not item.target_anchor:
            continue

        if (
            item.source_anchor.node in node_set
            and item.target_anchor.node in node_set
        ):
            connections_data.append(item.to_dict())

    return {
        "version": 1,
        "nodes": nodes_data,
        "connections": connections_data
    }

def deserialize_scene(data: dict, scene, editor, *, clear_scene=True):
    if clear_scene:
        scene.clear()

    node_index = {}
    created_items = []

    # 1. nodes
    for node_data in data["nodes"]:
        node = NodeItem.from_dict(
            node_data,
            sensor_registry=scene.sensor_registry  # 🔥 AQUI
        )
        node.editor = editor
        scene.addItem(node)

        node_index[node.id] = node
        created_items.append(node)

    # 2. connections
    for conn_data in data["connections"]:
        conn = ConnectionItem.from_dict(conn_data, node_index)
        scene.addItem(conn)
        created_items.append(conn)

    return created_items

def save_to_file(scene, filepath: str):
    data = serialize_scene(scene)
    path = Path(filepath)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_from_file(scene, filepath: str, editor):
    from graphics.sensor_registry.sensor_registry import SensorRegistry

    scene.sensor_registry = SensorRegistry()  # 🔹 reset controlado

    path = Path(filepath)

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    deserialize_scene(data, scene, editor)