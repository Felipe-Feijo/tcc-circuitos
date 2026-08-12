import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF

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

    # `ConnectionItem.from_dict` roda seu próprio passe de "reparo de
    # waypoints legados" (uma chamada a `adjust_waypoints_for_node_move()`)
    # logo após construir a conexão, com `_last_p2_in` ainda None nesse
    # ponto -- sem histórico, `_adjust_boundary` não tem como distinguir
    # "ponto solto redundante" de "canto deliberado" e insere uma ponte por
    # padrão. Sem o reset abaixo, esse efeito colateral do load já produziria
    # os 4 waypoints esperados sozinho, e o teste passaria mesmo que o
    # código acionado pelo *move* (o que esta task corrige) estivesse
    # quebrado. Reseta pra geometria pristina do fixture e prepara
    # `_last_p2_in` como estaria numa sessão ao vivo recém-assentada nessa
    # posição pré-move, pra que as asserções abaixo dependam só da chamada
    # explícita de `setPos` + `adjust_waypoints_for_node_move()` mais adiante.
    conn.waypoints = [QPointF(-663.0, -231.0), QPointF(46.0, -231.0), QPointF(46.0, -142.0)]
    _, _, _, p2_in_before_move, _, _ = conn._compute_exit_entry()
    conn._last_p2_in = p2_in_before_move
    assert len(conn.waypoints) == 3, "pré-condição: geometria pristina, sem ponte ainda"

    target.setPos(-342.5, -123.0)
    conn.adjust_waypoints_for_node_move(moved_source=False, moved_target=True)

    wps = conn.waypoints
    assert len(wps) == 4, (
        "esperava uma ponte inserida pela chamada de move+adjust (4 pontos), "
        f"achou {[(p.x(), p.y()) for p in wps]}"
    )
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


def test_redundant_collinear_filler_points_slide_together_with_the_anchor():
    """Cobre o ramo `was_aligned=True` de `_adjust_boundary`: dois waypoints
    "soltos" (ex.: inseridos por duplo-clique numa reta), ambos já alinhados
    com o anchor no eixo travado antes do move, devem andar JUNTOS com o
    anchor -- sem virar ponte e sem travar no primeiro.

    Setup análogo aos testes acima: prepara a geometria e o cache
    `_last_p2_in` manualmente (em vez de depender do reparo automático do
    `from_dict`, que roda sem histórico -- ver comentário no primeiro teste
    acima) pra isolar exatamente o comportamento de
    `adjust_waypoints_for_node_move` quando os dois waypoints PRÉ-move já
    estavam colineares entre si E alinhados com o anchor (o oposto do
    "canto deliberado" do primeiro teste)."""
    conn, target, source = _load(_state(
        (-210.0, -124.0),
        [{"x": 46.0, "y": -231.0}, {"x": 46.0, "y": -142.0}],
    ))

    conn.waypoints = [QPointF(46.0, -231.0), QPointF(46.0, -142.0)]
    _, _, _, p2_in_before_move, _, _ = conn._compute_exit_entry()
    assert abs(p2_in_before_move.x() - 46.0) < 0.5, "pré-condição: os 2 wps já alinhados com o anchor"
    conn._last_p2_in = p2_in_before_move

    target.setPos(-342.5, -124.0)
    conn.adjust_waypoints_for_node_move(moved_source=False, moved_target=True)

    wps = conn.waypoints
    assert len(wps) == 2, f"não deveria inserir ponte (são fillers redundantes), achou {[(p.x(), p.y()) for p in wps]}"
    _, _, _, p2_in_after_move, _, _ = conn._compute_exit_entry()
    # os dois pontos acompanharam o novo x do anchor, cada um mantendo seu y original
    assert abs(wps[0].x() - p2_in_after_move.x()) < 0.5
    assert abs(wps[0].y() - (-231.0)) < 0.5
    assert abs(wps[1].x() - p2_in_after_move.x()) < 0.5
    assert abs(wps[1].y() - (-142.0)) < 0.5


def test_double_click_loose_point_slides_with_boundary_no_bridge():
    """O caso que o fix de 29/06 resolveu: um ponto solto inserido no meio
    de um segmento reto perto da borda deve acompanhar o movimento do
    anchor sem gerar uma ponte extra (é genuinamente redundante, não um
    canto deliberado)."""
    conn, target, source = _load(_state((-342.5, -124.0), []))
    # `ConnectionItem.from_dict` marca `_waypoints_initialized = True` assim
    # que a lista de waypoints salva (vazia aqui) é aplicada, sem nunca
    # chamar `_route_between_points` -- `get_path_points()` então vê
    # "já inicializado" e não roteia nada, deixando `self.waypoints == []`
    # pra sempre (o desenho vira só p1_out->p2_in, uma reta possivelmente
    # diagonal). Isso é diferente de uma conexão nova numa sessão ao vivo,
    # que nunca passa por `from_dict` e por isso roteia normalmente na
    # primeira `get_path_points()`. `_reroute_waypoints()` força esse
    # roteamento real (e popula `_last_p1_out`/`_last_p2_in`), reproduzindo
    # o estado de uma sessão ao vivo já assentada nesta posição.
    conn._reroute_waypoints()

    p1_out = conn._resolved_points()[0][0]
    first_wp = conn.waypoints[0]
    mid = QPointF((p1_out.x() + first_wp.x()) / 2, (p1_out.y() + first_wp.y()) / 2)
    ins_idx = conn._insert_waypoint_at_segment(mid)
    assert ins_idx is not None, "duplo-clique não achou o segmento perto da borda -- ajuste o fixture"
    n_before = len(conn.waypoints)

    source.setPos(source.x() + 3, source.y() + 3)
    conn.adjust_waypoints_for_node_move(moved_source=True, moved_target=False)

    assert len(conn.waypoints) == n_before, (
        f"não deveria inserir ponte pra um ponto solto redundante, achou "
        f"{[(p.x(), p.y()) for p in conn.waypoints]}"
    )
    pts = conn.get_path_points()
    for a, b in zip(pts, pts[1:]):
        assert abs(a.x() - b.x()) < 0.5 or abs(a.y() - b.y()) < 0.5, f"segmento diagonal: {a} -> {b}"


def test_from_dict_round_trips_auto_route_without_spurious_bridge():
    """Reprodução do Important #1 do review final da branch: `from_dict()`
    roda seu passe de reparo legado (`adjust_waypoints_for_node_move()`) com
    o cache `_last_p1_out`/`_last_p2_in`/`_last_exit_dir`/`_last_entry_dir`
    ainda nos defaults de `__init__` -- sem histórico, a checagem "rota
    pristina" nunca dispara e `_adjust_boundary` trata QUALQUER waypoint
    perto da borda que compartilhe o eixo travado com seu vizinho interno
    como "canto deliberado", inserindo uma ponte degenerada (sentada em cima
    do próprio anchor) numa rota que era puramente automática. Essa ponte é
    persistida de volta no próximo save, marcando a conexão como
    "não-pristina" pra sempre. Constrói uma rota automática real numa sessão
    "ao vivo" (via `_reroute_waypoints()`, não via `from_dict`), serializa
    com `to_dict()` e recarrega com `from_dict()` -- a lista de waypoints
    deve bater exatamente, sem ponte extra."""
    conn, target, source = _load(_state((-342.5, -124.0), []))
    conn._reroute_waypoints()
    before = [(p.x(), p.y()) for p in conn.waypoints]
    assert len(before) == 3, (
        f"pré-condição: rota automática vhvh de 3 pontos, achou {before} -- "
        "ajuste o fixture se o roteador mudou de comportamento"
    )

    data = conn.to_dict()
    node_index = {"source": source, "target": target}
    conn2 = ConnectionItem.from_dict(data, node_index)
    conn2._test_scene_ref = conn._test_scene_ref

    after = [(p.x(), p.y()) for p in conn2.waypoints]
    assert after == before, (
        f"round-trip do_dict/from_dict deveria preservar a rota automática "
        f"intacta, esperava {before}, achou {after}"
    )


def test_auto_route_move_does_not_insert_spurious_bridge():
    """Rota automática (2 ou 3 pontos) não deve nunca ganhar uma ponte
    espúria ao mover um dos componentes -- é o caso mais comum e não pode
    regredir."""
    conn, target, source = _load(_state((-342.5, -124.0), []))
    # Mesma ressalva do teste acima: força o roteamento automático real em
    # vez de depender de `get_path_points()`, que é um no-op aqui porque
    # `from_dict` já marcou `_waypoints_initialized = True` sem rotear.
    conn._reroute_waypoints()
    n_before = len(conn.waypoints)

    target.setPos(-300.0, -110.0)
    conn.adjust_waypoints_for_node_move(moved_source=False, moved_target=True)

    assert len(conn.waypoints) == n_before, (
        f"rota automática não deveria ganhar waypoint extra, achou "
        f"{[(p.x(), p.y()) for p in conn.waypoints]}"
    )
    pts = conn.get_path_points()
    for a, b in zip(pts, pts[1:]):
        assert abs(a.x() - b.x()) < 0.5 or abs(a.y() - b.y()) < 0.5, f"segmento diagonal: {a} -> {b}"
