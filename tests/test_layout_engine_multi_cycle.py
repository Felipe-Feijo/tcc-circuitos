"""Teste de posicionamento end-to-end para o suporte a multi-ciclo — ver
docs/superpowers/specs/2026-07-10-cascade-multi-cycle-or-valve-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.sequence_parser import parse
from circuit_generator.methods import cascade
from circuit_generator.layout_engine import apply as apply_layout


def _positions_by_id(data):
    return {n["id"]: n["position"] for n in data["nodes"]}


def test_single_cycle_layout_still_works_end_to_end():
    # regressão: sequência de 1 ciclo continua funcionando sem OR nenhuma
    data = cascade.generate(parse("A+B+A-B-"))
    data = apply_layout(data)
    assert [n for n in data["nodes"] if n["type"] == "OrValve"] == []
    at_origin = [nid for nid, pos in _positions_by_id(data).items()
                 if pos["x"] == 0 and pos["y"] == 0]
    assert at_origin == []


def test_no_node_left_at_origin_for_multi_cycle_sequence():
    # "B+A+B-A-A+A-" produz uma OrValve com fonte mista (bus-direto + sig
    # encadeada), exercitando o fallback de posição das sigs "órfãs"
    data = cascade.generate(parse("B+A+B-A-A+A-"))
    data = apply_layout(data)
    at_origin = [nid for nid, pos in _positions_by_id(data).items()
                 if pos["x"] == 0 and pos["y"] == 0]
    assert at_origin == []


def test_or_valve_nodes_get_a_position():
    data = cascade.generate(parse("B+A+B-A-A+A-"))
    data = apply_layout(data)
    or_nodes = [n for n in data["nodes"] if n["type"] == "OrValve"]
    assert len(or_nodes) == 2
    for n in or_nodes:
        assert (n["position"]["x"], n["position"]["y"]) != (0, 0)


def test_orphan_signal_valves_get_a_position():
    # gen-sig-B-ext-0 e gen-sig-B-ret-2 alimentam uma OrValve, não a 4/2
    # diretamente — precisam do fallback de posição, não do KeyError antigo
    data = cascade.generate(parse("B+A+B-A-A+A-"))
    data = apply_layout(data)
    positions = _positions_by_id(data)
    for sig_id in ("gen-sig-B-ext-0", "gen-sig-B-ret-2"):
        assert sig_id in positions
        pos = positions[sig_id]
        assert (pos["x"], pos["y"]) != (0, 0)
    # os dois orphan sigs alimentam lados de pilot diferentes (PL vs PR) do
    # mesmo cilindro — não podem cair na mesma posição
    pos_ext = positions["gen-sig-B-ext-0"]
    pos_ret = positions["gen-sig-B-ret-2"]
    assert (pos_ext["x"], pos_ext["y"]) != (pos_ret["x"], pos_ret["y"])


def test_two_orphan_signal_valves_feeding_same_or_valve_get_distinct_positions():
    # gen-sig-A-ext-0 e gen-sig-A-ret-5 alimentam anchors diferentes (X e Y)
    # da MESMA OrValve (or_valve:B:PL:0) -- precisam de posições distintas
    # mesmo compartilhando letra+pilot_side
    data = cascade.generate(parse("A+B+A-B-A+A-B+B-"))
    data = apply_layout(data)
    positions = _positions_by_id(data)
    pos_ext = positions["gen-sig-A-ext-0"]
    pos_ret = positions["gen-sig-A-ret-5"]
    assert (pos_ext["x"], pos_ext["y"]) != (pos_ret["x"], pos_ret["y"])


def test_three_cycle_chain_layout_does_not_crash():
    # cadeia de 2 OrValve por pilot — garante que o caso N>2 também
    # atravessa o layout sem erro
    data = cascade.generate(parse("A+A-A+A-A+A-"))
    data = apply_layout(data)
    or_nodes = [n for n in data["nodes"] if n["type"] == "OrValve"]
    assert len(or_nodes) == 4
    at_origin = [nid for nid, pos in _positions_by_id(data).items()
                 if pos["x"] == 0 and pos["y"] == 0]
    assert at_origin == []


class TestPilotAnchorRobustToCommutation:
    def test_signal_valve_feeding_left_memory_uses_the_commutation_margin(self):
        # cascade.py seta default_side="left" pra toda memória de grupo
        # com índice i > 0. DIFERENTE do passo a passo: em cascade, PR de
        # uma memória NUNCA é alimentado direto por uma PressureLine --
        # sempre por uma cadeia de sig (Valve_3_2_Ways), ver
        # cascade.py:327 (`connect(final_id, final_anchor, mem_ids[...], "PR")`,
        # onde final_id é sempre um Valve_3_2_Ways). O que muda com a
        # correção é a posição X atribuída a esse sig
        # (layout_engine.py:455, `sig_x`), que usa V52_PR_x pra se colocar
        # relativo à própria memória -- precisa usar o valor com a margem
        # de comutação (anchor_local_for_routing), não o valor base, senão
        # o sig fica mais perto da memória do que deveria quando ela
        # comuta.
        import json
        from circuit_generator.sequence_parser import parse
        from circuit_generator.methods import cascade
        from circuit_generator import layout_engine
        from circuit_generator.sprite_metrics import anchor_local_for_routing, METRICS as _M

        data = cascade.generate(parse("A+B+A-B-C+C-"))  # 2+ grupos
        result = layout_engine.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}

        left_memories = [n for n in result["nodes"]
                         if n["type"] == "Valve_5_2_Ways"
                         and n["properties"].get("default_side") == "left"]
        assert left_memories, "cenário precisa ter pelo menos 1 memória com default_side=left"

        cfg = json.loads(layout_engine._CONFIG_PATH.read_text(encoding="utf-8"))
        cols = cfg["columns"]
        n_mc_total = sum(1 for n in result["nodes"] if n["type"] == "Valve_5_2_Ways")
        sig_pr_off = (cols.get("sig_mc_pilot_offset_PR", 500)
                      + cols.get("sig_pilot_offset_PR_per_mc", 0) * (n_mc_total - 1))
        base_pr_x = _M.anchor_local["Valve_5_2_Ways"]["PR"][0]
        sig_a_x   = _M.anchor_local["Valve_3_2_Ways"]["A"][0]  # "A" não muda com a correção

        checked = 0
        for mc in left_memories:
            conns = [c for c in result["connections"]
                     if c["target"]["node"] == mc["id"] and c["target"]["anchor"] == "PR"]
            for conn in conns:
                sig = node_by_id[conn["source"]["node"]]
                if sig["type"] != "Valve_3_2_Ways":
                    continue
                mc_x = mc["position"]["x"]
                sig_x_actual     = sig["position"]["x"]
                sig_x_without_fix = mc_x + base_pr_x - sig_a_x + sig_pr_off
                assert sig_x_actual > sig_x_without_fix, (
                    f"{sig['id']}: x={sig_x_actual} não ficou à direita do valor "
                    f"SEM a margem de comutação (x={sig_x_without_fix}) -- "
                    f"layout_engine ainda usa o V52_PR_x base, não anchor_local_for_routing"
                )
                checked += 1
        assert checked > 0


class TestPressureLineAnchorYAccountsForSpriteHeight:
    def test_routing_uses_the_real_rendered_anchor_y_not_just_node_position_y(self):
        # Regressão: mesma causa raiz do passo a passo --
        # graphics/items/base/nodes/expandable/pressure_line.py posiciona
        # os anchors da PressureLine em y0=self.pix_h (pl_pix_h abaixo da
        # posição do nó), mas layout_engine._scene_xy usava npos[1] direto,
        # sem somar esse offset. Reproduzido com
        # parse("A+B+A-B-C+C-"): gen-pl-grp1.X45 -> gen-sig-A-ext-0.P.
        from circuit_generator.sprite_metrics import METRICS as _M

        data = cascade.generate(parse("A+B+A-B-C+C-"))
        result = apply_layout(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        node_type_map = {n["id"]: n["type"] for n in result["nodes"]}

        checked = 0
        for c in result["connections"]:
            s, t = c["source"], c["target"]
            if node_type_map.get(s["node"]) != "PressureLine":
                continue
            wps = c.get("waypoints")
            if not wps:
                continue
            pl = node_by_id[s["node"]]
            real_pl_y = pl["position"]["y"] + _M.pl_pix_h
            target_y = node_by_id[t["node"]]["position"]["y"]
            for wp in wps:
                if target_y > real_pl_y:
                    assert wp["y"] >= real_pl_y - 1, (
                        f"{s} -> {t}: alvo está ABAIXO da PL, mas waypoint "
                        f"y={wp['y']} cruza de volta pra cima do anchor REAL "
                        f"da PL (y={real_pl_y})"
                    )
                elif target_y < real_pl_y:
                    assert wp["y"] <= real_pl_y + 1, (
                        f"{s} -> {t}: alvo está ACIMA da PL, mas waypoint "
                        f"y={wp['y']} cruza de volta pra baixo do anchor REAL "
                        f"da PL (y={real_pl_y})"
                    )
            checked += 1
        assert checked > 0


def test_pressure_line_buses_use_the_new_paired_terminal_format():
    data = cascade.generate(parse("A+B+A-B-"))
    data = apply_layout(data)
    pl_nodes = [n for n in data["nodes"] if n["type"] == "PressureLine"]
    assert pl_nodes, "expected at least one PressureLine bus"
    for pl in pl_nodes:
        assert "anchors" not in pl["properties"]
    node_ids = {n["id"] for n in data["nodes"]}
    for conn in data["connections"]:
        assert conn["source"]["node"] in node_ids
        assert conn["target"]["node"] in node_ids
        assert not conn["source"]["anchor"].startswith("X") or conn["source"]["anchor"] == "X1"
        assert not conn["target"]["anchor"].startswith("X") or conn["target"]["anchor"] == "X1"
