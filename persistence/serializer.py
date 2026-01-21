import json
from pathlib import Path

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.connections.connection_item import ConnectionItem

def serialize_scene(scene) -> dict:
    nodes = []
    connections = []

    for item in scene.items():
        if isinstance(item, NodeItem):
            nodes.append(item.to_dict())

        elif isinstance(item, ConnectionItem):
            connections.append(item.to_dict())

    return {
        "version": 1,
        "nodes": nodes,
        "connections": connections
    }

def deserialize_scene(data: dict, scene, editor):
    scene.clear()

    node_index = {}

    # 1. nodes
    for node_data in data["nodes"]:
        node = NodeItem.from_dict(node_data)
        node.editor = editor 
        scene.addItem(node)
        node_index[node.id] = node

    # 2. connections
    for conn_data in data["connections"]:
        conn = ConnectionItem.from_dict(conn_data, node_index)
        scene.addItem(conn)

def save_to_file(scene, filepath: str):
    data = serialize_scene(scene)
    path = Path(filepath)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_from_file(scene, filepath: str, editor):
    path = Path(filepath)

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    deserialize_scene(data, scene, editor)