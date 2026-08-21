"""Serialization and deserialization of the graphics scene in JSON v1 format.

File format:
    {
        "version": 1,
        "nodes": [ <NodeItem.to_dict()>, ... ],
        "connections": [ <ConnectionItem.to_dict()>, ... ]
    }

Public functions:
    serialize_scene   -- scene -> dict
    deserialize_scene -- dict -> items in the scene
    save_to_file      -- scene -> .json file
    load_from_file    -- .json file -> scene
"""

import json
from pathlib import Path

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.connections.connection_item import ConnectionItem


def serialize_scene(scene, *, nodes=None) -> dict:
    """Converts the graphics scene into a serializable dict.

    Args:
        scene: QGraphicsScene holding the diagram's items.
        nodes: Optional list of NodeItems to serialize. If None,
            serializes every NodeItem present in the scene.

    Returns:
        Dict in JSON v1 format with "version", "nodes" and
        "connections" keys.
    """
    if nodes is None:
        nodes = [item for item in scene.items() if isinstance(item, NodeItem)]

    node_set = set(nodes)
    nodes_data = [node.to_dict() for node in nodes]

    connections_data = []
    for item in scene.items():
        if not isinstance(item, ConnectionItem):
            continue
        # Skips incomplete connections (missing a source or target anchor)
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
        "connections": connections_data,
    }


def deserialize_scene(data: dict, scene, editor, *, clear_scene=True) -> list:
    """Rebuilds the scene from a JSON v1 dict.

    Args:
        data: Dict in the format returned by serialize_scene.
        scene: Target QGraphicsScene.
        editor: EditorState passed to the created items.
        clear_scene: If True (default), clears the scene before rebuilding.

    Returns:
        List of every item created (NodeItems and ConnectionItems).
    """
    if clear_scene:
        scene.clear()

    node_index = {}
    created_items = []

    # Step 1: creates the nodes
    for node_data in data["nodes"]:
        node = NodeItem.from_dict(
            node_data,
            sensor_registry=scene.sensor_registry,
        )
        node.editor = editor
        scene.addItem(node)
        node_index[node.id] = node
        created_items.append(node)

    # Step 2: creates the connections (depend on the nodes already existing)
    for conn_data in data["connections"]:
        conn = ConnectionItem.from_dict(conn_data, node_index)
        conn.editor = editor
        scene.addItem(conn)
        created_items.append(conn)

    return created_items


def save_to_file(scene, filepath: str) -> None:
    """Serializes the scene and writes it to a JSON file.

    Args:
        scene: QGraphicsScene holding the diagram's items.
        filepath: Absolute or relative path of the destination file.
    """
    data = serialize_scene(scene)
    path = Path(filepath)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_from_file(scene, filepath: str, editor) -> None:
    """Loads a JSON file and rebuilds the scene.

    Resets the SensorRegistry before loading to guarantee sensors from
    a previous session don't contaminate the new scene.

    Args:
        scene: Target QGraphicsScene.
        filepath: Path of the .json file to load.
        editor: EditorState passed to the recreated items.
    """
    from graphics.sensor_registry.sensor_registry import SensorRegistry

    # Resets the sensor registry before loading the new scene
    scene.sensor_registry = SensorRegistry()

    path = Path(filepath)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    with scene.sensor_registry.loading():
        deserialize_scene(data, scene, editor)
