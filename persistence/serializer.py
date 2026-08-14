"""Serialização e desserialização da cena gráfica em formato JSON v1.

Formato do arquivo:
    {
        "version": 1,
        "nodes": [ <NodeItem.to_dict()>, ... ],
        "connections": [ <ConnectionItem.to_dict()>, ... ]
    }

Funções públicas:
    serialize_scene   — cena → dict
    deserialize_scene — dict → itens na cena
    save_to_file      — cena → arquivo .json
    load_from_file    — arquivo .json → cena
"""

import json
from pathlib import Path

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.connections.connection_item import ConnectionItem


def serialize_scene(scene, *, nodes=None) -> dict:
    """Converte a cena gráfica em um dicionário serializável.

    Args:
        scene: QGraphicsScene com os itens do diagrama.
        nodes: Lista opcional de NodeItems a serializar. Se None, serializa
            todos os NodeItems presentes na cena.

    Returns:
        Dicionário no formato JSON v1 com chaves "version", "nodes"
        e "connections".
    """
    if nodes is None:
        nodes = [item for item in scene.items() if isinstance(item, NodeItem)]

    node_set = set(nodes)
    nodes_data = [node.to_dict() for node in nodes]

    connections_data = []
    for item in scene.items():
        if not isinstance(item, ConnectionItem):
            continue
        # Ignora conexões incompletas (sem âncora de origem ou destino)
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
    """Reconstrói a cena a partir de um dicionário JSON v1.

    Args:
        data: Dicionário no formato retornado por serialize_scene.
        scene: QGraphicsScene de destino.
        editor: EditorState passado aos itens criados.
        clear_scene: Se True (padrão), limpa a cena antes de reconstruir.

    Returns:
        Lista de todos os itens criados (NodeItems e ConnectionItems).
    """
    if clear_scene:
        scene.clear()

    node_index = {}
    created_items = []

    # Passo 1: cria os nós
    for node_data in data["nodes"]:
        node = NodeItem.from_dict(
            node_data,
            sensor_registry=scene.sensor_registry,
        )
        node.editor = editor
        scene.addItem(node)
        node_index[node.id] = node
        created_items.append(node)

    # Passo 2: cria as conexões (dependem dos nós já existirem)
    for conn_data in data["connections"]:
        conn = ConnectionItem.from_dict(conn_data, node_index)
        conn.editor = editor
        scene.addItem(conn)
        created_items.append(conn)

    return created_items


def save_to_file(scene, filepath: str) -> None:
    """Serializa a cena e grava em um arquivo JSON.

    Args:
        scene: QGraphicsScene com os itens do diagrama.
        filepath: Caminho absoluto ou relativo do arquivo de destino.
    """
    data = serialize_scene(scene)
    path = Path(filepath)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_from_file(scene, filepath: str, editor) -> None:
    """Carrega um arquivo JSON e reconstrói a cena.

    Reinicia o SensorRegistry antes de carregar para garantir que
    sensores de uma sessão anterior não contaminem a nova cena.

    Args:
        scene: QGraphicsScene de destino.
        filepath: Caminho do arquivo .json a carregar.
        editor: EditorState passado aos itens recriados.
    """
    from graphics.sensor_registry.sensor_registry import SensorRegistry

    # Reinicia o registro de sensores antes de carregar nova cena
    scene.sensor_registry = SensorRegistry()

    path = Path(filepath)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    with scene.sensor_registry.loading():
        deserialize_scene(data, scene, editor)
