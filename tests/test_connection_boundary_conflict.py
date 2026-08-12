import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.scene import GraphicsScene
from persistence.serializer import deserialize_scene
from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways
from graphics.items.base.nodes.directional_valve.valve_5_2_ways import Valve_5_2_Ways


def _state(target_pos: tuple, waypoints: list) -> dict:
    """Monta um estado JSON v1 mínimo: Valve_5_2_Ways.B (source, fixo) ->
    Valve_4_2_Ways.B (target, posição variável) -- mesma dupla de
    componentes e mesma âncora ('B', ambas saem por 'top') dos JSONs reais
    que o usuário reportou (estado1..estado5.json)."""
    return {
        "version": 1,
        "nodes": [
            {"id": "target", "type": "Valve_4_2_Ways", "domain": "pneumatic",
             "position": {"x": target_pos[0], "y": target_pos[1]}, "rotation": 0.0,
             "properties": {"actuators": {"left": None, "right": None}, "default_side": "right"},
             "labels": {}, "anchor_labels": {}},
            {"id": "source", "type": "Valve_5_2_Ways", "domain": "pneumatic",
             "position": {"x": -1068.0, "y": -94.0}, "rotation": 0.0,
             "properties": {"actuators": {"left": None, "right": None}, "default_side": "right"},
             "labels": {}, "anchor_labels": {}},
        ],
        "connections": [
            {"source": {"node": "source", "anchor": "B"},
             "target": {"node": "target", "anchor": "B"},
             "waypoints": waypoints},
        ],
    }


def _load(state: dict):
    scene = GraphicsScene()
    items = deserialize_scene(state, scene, editor=None)
    conn = next(i for i in items if isinstance(i, ConnectionItem))
    target = next(i for i in items if getattr(i, "id", None) == "target")
    source = next(i for i in items if getattr(i, "id", None) == "source")
    # Mantém `scene` viva enquanto `conn` existir -- sem isso o PyQt destrói o
    # QGraphicsScene C++ (e em cascata os itens filhos) assim que a variável
    # local `scene` desta função sai de escopo, mesmo com `conn`/`target`
    # ainda referenciados pelo chamador.
    conn._test_scene_ref = scene
    return conn, target, source


def test_deliberate_offset_gets_a_bridge_instead_of_collapsing():
    """Reprodução exata de estado2 -> estado3 do usuário: um desvio manual
    de 3 waypoints (o segmento vertical [1]-[2] é um canto deliberado, não
    um ponto solto redundante) não pode ser engolido quando o componente
    alvo move só 1px."""
    conn, target, source = _load(_state(
        (-342.5, -124.0),
        [{"x": -663.0, "y": -231.0}, {"x": 46.0, "y": -231.0}, {"x": 46.0, "y": -142.0}],
    ))
    target.setPos(-342.5, -123.0)
    conn.adjust_waypoints_for_node_move(moved_source=False, moved_target=True)

    wps = conn.waypoints
    assert len(wps) == 4, f"esperava uma ponte inserida (4 pontos), achou {[(p.x(), p.y()) for p in wps]}"
    assert (wps[0].x(), wps[0].y()) == (-663.0, -231.0)
    assert (wps[1].x(), wps[1].y()) == (46.0, -231.0)
    assert (wps[2].x(), wps[2].y()) == (46.0, -142.0)
    # ponte: eixo travado (x) bate com o anchor novo, outro eixo (y) com wps[2]
    assert abs(wps[3].y() - (-142.0)) < 0.5
    assert wps[3].x() != 46.0

    pts = conn.get_path_points()
    for a, b in zip(pts, pts[1:]):
        assert abs(a.x() - b.x()) < 0.5 or abs(a.y() - b.y()) < 0.5, f"segmento diagonal: {a} -> {b}"


def test_bridge_already_present_only_moves_itself():
    """Reprodução de estado4 -> estado5: quando já existe um waypoint bem
    na borda (a 'ponte' manual que o usuário construiu), só ele se move."""
    conn, target, source = _load(_state(
        (-342.5, -123.0),
        [{"x": -663.0, "y": -231.0}, {"x": 46.0, "y": -231.0},
         {"x": 46.0, "y": -142.0}, {"x": -86.5, "y": -142.0}],
    ))
    target.setPos(-451.5, -98.0)
    conn.adjust_waypoints_for_node_move(moved_source=False, moved_target=True)

    wps = conn.waypoints
    assert len(wps) == 4, f"não deveria inserir nova ponte, achou {[(p.x(), p.y()) for p in wps]}"
    assert (wps[0].x(), wps[0].y()) == (-663.0, -231.0)
    assert (wps[1].x(), wps[1].y()) == (46.0, -231.0)
    assert (wps[2].x(), wps[2].y()) == (46.0, -142.0)
    assert abs(wps[3].y() - (-142.0)) < 0.5   # y intocado
    assert wps[3].x() != -86.5                # x acompanhou o anchor
