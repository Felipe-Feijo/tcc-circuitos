"""Testes para circuit_generator/step_by_step_electric_layout.py — ver
docs/superpowers/specs/2026-07-31-step-by-step-electric-start-button-and-anchor-fix-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

import pytest

from circuit_generator.sequence_parser import parse
from circuit_generator.methods import step_by_step_electric as sbe
from circuit_generator import step_by_step_electric_layout as layout
from circuit_generator.sprite_metrics import METRICS as _M, anchor_local_for_routing


def _node(data, node_id):
    return next(n for n in data["nodes"] if n["id"] == node_id)


def _scene_xy(node_by_id, node_type_map, node_id, anchor_name):
    """Real (x, y) of an anchor. Since the RailPlanner migration (rail.py),
    a VoltageSource/Ground "X1" resolves against the node's OWN stored
    position (which already bakes in the vsource_pix_w/ground_pix_w*0.5
    offset -- see rail.py's x_min) via sprite_metrics.py's "VoltageSource"/
    "Ground" anchor_local entries -- no more special-casing needed here."""
    pos = node_by_id[node_id]["position"]
    ntype = node_type_map.get(node_id, "")
    local = anchor_local_for_routing(ntype, anchor_name)
    return (pos["x"] + local[0], pos["y"] + local[1]) if local else (pos["x"], pos["y"])


def _assert_connection_orthogonal(data, conn, eps=0.5):
    node_by_id = {n["id"]: n for n in data["nodes"]}
    node_type_map = {n["id"]: n["type"] for n in data["nodes"]}
    pts = [_scene_xy(node_by_id, node_type_map, conn["source"]["node"], conn["source"]["anchor"])]
    for wp in conn.get("waypoints", []):
        pts.append((wp["x"], wp["y"]))
    pts.append(_scene_xy(node_by_id, node_type_map, conn["target"]["node"], conn["target"]["anchor"]))
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        assert abs(x1 - x2) <= eps or abs(y1 - y2) <= eps, (
            f"diagonal segment {pts[i]} -> {pts[i + 1]} in connection {conn}"
        )


class TestCylinderSpacing:
    def test_cylinders_1000px_apart(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        cyl_a_x = _node(data, "gen-cyl-A")["position"]["x"]
        cyl_b_x = _node(data, "gen-cyl-B")["position"]["x"]
        assert cyl_b_x - cyl_a_x == 1000


class TestNoCollisionOrDuplicatePositions:
    def test_no_two_nodes_share_a_position(self):
        for seq in ("A+B+A-B-", "A+B+A-A+B-A-", "C+(A+B+)C-A-B-"):
            data = layout.apply(sbe.generate(parse(seq)))
            positions = [(n["position"]["x"], n["position"]["y"]) for n in data["nodes"]]
            assert len(positions) == len(set(positions)), seq

    def test_voltage_source_does_not_collide_with_ramo_a_stack(self):
        # Bug real do v0: vsource_row_y coincidia exatamente com a primeira
        # linha empilhada de sensores (ramo_row_y - 1*ramo_stack_gap).
        data = layout.apply(sbe.generate(parse("C+(A+B+)C-A-B-")))  # tem bloco paralelo -> stack
        vsource_y = _node(data, "gen-vsource")["position"]["y"]
        sensor_y = _node(data, "gen-contact-2-ramo_a_sensor0")["position"]["y"]
        assert vsource_y != sensor_y

    def test_voltage_source_does_not_overlap_a_3_deep_sensor_stack(self):
        # Achado de revisão: uma checagem de mera desigualdade de valor
        # (vsource_y != sensor_y) passa mesmo quando as CAIXAS DELIMITADORAS
        # dos dois sprites se sobrepõem -- e é exatamente isso que
        # acontecia com o stack de profundidade 3 sob as constantes
        # anteriores (vsource ocupava y em [700,800], stack de profundidade
        # 3 ocupava y em [750,825] -- 50px de sobreposição real). Este
        # teste verifica sobreposição de caixa delimitadora de verdade,
        # contra um átomo com 3 eventos simultâneos (bloco paralelo com 3
        # ramos).
        data = layout.apply(sbe.generate(parse("(A+B+C+)A-B-C-")))
        vsource = _node(data, "gen-vsource")
        vs_top = vsource["position"]["y"]
        vs_bottom = vs_top + _M.vsource_pix_h
        for role in ("ramo_a_sensor0", "ramo_a_sensor1", "ramo_a_sensor2"):
            sensor = _node(data, f"gen-contact-1-{role}")
            s_top = sensor["position"]["y"]
            s_bottom = s_top + _M.relay_switch_height
            overlap = s_top < vs_bottom and vs_top < s_bottom
            assert not overlap, (
                f"{role}: vsource=[{vs_top},{vs_bottom}] sensor=[{s_top},{s_bottom}]"
            )


class TestCoherentAtomBlock:
    """Reset (NC) e bobina K ficam na MESMA coluna do ramo B, logo abaixo
    -- bloco coeso por átomo, não mais uma zona distante."""

    def test_reset_and_coil_same_x_as_ramo_b(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        for k in range(4):
            ramo_b_x = _node(data, f"gen-contact-{k}-ramo_b_self")["position"]["x"]
            reset_x = _node(data, f"gen-contact-{k}-reset_nc")["position"]["x"]
            coil_x = _node(data, f"gen-coil-{k}")["position"]["x"]
            assert reset_x == ramo_b_x
            assert coil_x == ramo_b_x

    def test_reset_below_ramo_row_coil_below_reset(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        ramo_y = _node(data, "gen-contact-0-ramo_b_self")["position"]["y"]
        reset_y = _node(data, "gen-contact-0-reset_nc")["position"]["y"]
        coil_y = _node(data, "gen-coil-0")["position"]["y"]
        assert ramo_y < reset_y < coil_y

    def test_atom_blocks_ordered_left_to_right(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        xs = [_node(data, f"gen-contact-{k}-ramo_b_self")["position"]["x"] for k in range(4)]
        assert xs == sorted(xs)


class TestStartButtonPosition:
    """Botão de início: mesma coluna do ramo A do átomo 0, numa linha
    própria entre ramo_row e reset_row."""

    def test_start_button_same_column_as_atom_zero_ramo_a(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        ramo_a_x = _node(data, "gen-contact-0-ramo_a_prev")["position"]["x"]
        btn_x = _node(data, "gen-btn-start")["position"]["x"]
        assert btn_x == ramo_a_x

    def test_start_button_between_ramo_row_and_reset_row(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        ramo_y = _node(data, "gen-contact-0-ramo_a_prev")["position"]["y"]
        reset_y = _node(data, "gen-contact-0-reset_nc")["position"]["y"]
        btn_y = _node(data, "gen-btn-start")["position"]["y"]
        assert ramo_y < btn_y < reset_y


class TestButtonJoinsTheRamoAStackGrid:
    """O botão de início (gen-btn-start) é só mais um nível empilhado na
    MESMA coluna/grade do ramo A -- não uma linha própria em fração
    arbitrária entre ramo_row e reset_row."""

    def test_start_button_one_stack_level_below_ramo_row(self):
        # átomo anterior ao 0 (que fecha o anel) é um bloco paralelo de 2
        # eventos -> átomo 0 tem stack de sensores de profundidade 2,
        # permitindo comparar o passo do botão com o passo real entre
        # níveis do stack.
        data = layout.apply(sbe.generate(parse("A+B+(A-B-)")))
        ramo_y = _node(data, "gen-contact-0-ramo_a_prev")["position"]["y"]
        # sensor1 (evento mais recente do átomo anterior) fica mais perto de
        # ramo_row; sensor0 (evento mais antigo) fica mais longe -- a cadeia
        # é montada em ordem reversa (ver `reversed(sensor_roles)` no layout).
        sensor_near_y = _node(data, "gen-contact-0-ramo_a_sensor1")["position"]["y"]
        sensor_far_y = _node(data, "gen-contact-0-ramo_a_sensor0")["position"]["y"]
        btn_y = _node(data, "gen-btn-start")["position"]["y"]

        level_gap = ramo_y - sensor_near_y
        assert sensor_near_y - sensor_far_y == level_gap, "níveis do stack acima não usam passo uniforme"
        assert btn_y - ramo_y == level_gap, "botão não está no mesmo passo do grid do stack"

    def test_reset_row_comes_after_the_button_level(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        btn_y = _node(data, "gen-btn-start")["position"]["y"]
        reset_y = _node(data, "gen-contact-0-reset_nc")["position"]["y"]
        assert reset_y > btn_y


class TestSourceGroundHeightScalesWithActualMaxDepth:
    """A distância vsource->ramo_row deve refletir a profundidade real do
    circuito, não uma constante fixa dimensionada pro pior caso (profundidade
    até 5-6, ver histórico em step_by_step_electric_layout.py)."""

    def test_shallow_sequence_uses_far_less_height_than_the_old_fixed_worst_case(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        vsource = _node(data, "gen-vsource")
        ramo_y = _node(data, "gen-contact-0-ramo_b_self")["position"]["y"]
        gap = ramo_y - (vsource["position"]["y"] + _M.vsource_pix_h)
        assert gap < 500  # bem menor que os ~900px reservados antes pro pior caso

    def test_deeper_sequence_gets_more_height_than_a_shallow_one(self):
        def gap(seq, atom_idx):
            data = layout.apply(sbe.generate(parse(seq)))
            vsource = _node(data, "gen-vsource")
            ramo_y = _node(data, f"gen-contact-{atom_idx}-ramo_b_self")["position"]["y"]
            return ramo_y - (vsource["position"]["y"] + _M.vsource_pix_h)

        shallow_gap = gap("A+B+A-B-", 0)
        deep_gap = gap("(A+B+C+)A-B-C-", 1)  # átomo 1: stack de profundidade 3
        assert deep_gap > shallow_gap


class TestPowerZoneRightOfAllAtomBlocks:
    def test_power_zone_entirely_right_of_last_atom_block(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        atom_xs = []
        for k in range(4):
            atom_xs.append(_node(data, f"gen-contact-{k}-ramo_a_prev")["position"]["x"])
            atom_xs.append(_node(data, f"gen-contact-{k}-ramo_b_self")["position"]["x"])
            atom_xs.append(_node(data, f"gen-contact-{k}-reset_nc")["position"]["x"])
            atom_xs.append(_node(data, f"gen-coil-{k}")["position"]["x"])
        power_xs = [
            _node(data, cid)["position"]["x"] for cid in (
                "gen-contact-power-A-ext-0", "gen-contact-power-B-ext-1",
                "gen-contact-power-A-ret-2", "gen-contact-power-B-ret-3",
            )
        ]
        assert max(atom_xs) < min(power_xs)

    def test_power_groups_ordered_by_first_triggering_atom(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        xs = {
            cid: _node(data, cid)["position"]["x"] for cid in (
                "gen-contact-power-A-ext-0", "gen-contact-power-B-ext-1",
                "gen-contact-power-A-ret-2", "gen-contact-power-B-ret-3",
            )
        }
        ordered = sorted(xs, key=lambda cid: xs[cid])
        assert ordered == [
            "gen-contact-power-A-ext-0", "gen-contact-power-B-ext-1",
            "gen-contact-power-A-ret-2", "gen-contact-power-B-ret-3",
        ]


class TestMultiCyclePowerStacking:
    def test_two_power_contacts_distinct_positions_same_column(self):
        data = layout.apply(sbe.generate(parse("A+B+A-A+B-A-")))
        c0 = _node(data, "gen-contact-power-A-ext-0")["position"]
        c3 = _node(data, "gen-contact-power-A-ext-3")["position"]
        assert c0 != c3
        assert c0["x"] == c3["x"]
        assert c0["y"] != c3["y"]


class TestVoltageSourceAboveGroundBelow:
    def test_voltage_source_above_ramo_row(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        vsource_y = _node(data, "gen-vsource")["position"]["y"]
        ramo_y = _node(data, "gen-contact-0-ramo_b_self")["position"]["y"]
        assert vsource_y < ramo_y

    def test_ground_below_coil_row(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        ground_y = _node(data, "gen-ground")["position"]["y"]
        coil_y = _node(data, "gen-coil-0")["position"]["y"]
        assert ground_y > coil_y


class TestCylinderRegionAboveElectricRegion:
    def test_cylinders_above_voltage_source(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        cyl_y = _node(data, "gen-cyl-A")["position"]["y"]
        vsource_y = _node(data, "gen-vsource")["position"]["y"]
        assert cyl_y < vsource_y


class TestLayoutMapRegistration:
    def test_generate_and_load_resolves_electric_layout(self):
        from circuit_generator.circuit_generator import LAYOUT_MAP
        assert LAYOUT_MAP[("step_by_step", "electric")] is layout.apply


class TestVoltageSourceGroundBarDimensioned:
    """RailPlanner (rail.py) sizes each bus once from the grid's real reach
    (x_min/x_max), no incremental "anchors" array to grow/shrink anymore --
    materialize() pops properties["anchors"] entirely and represents the
    bus's far end as a REAL "JunctionNodeItem" node (bus_id + "-b-...")."""

    def test_bars_reach_the_full_x_range_of_nodes(self):
        raw = sbe.generate(parse("A+B+A-B-"))
        data = layout.apply(raw)
        node_xs = [n["position"]["x"] for n in data["nodes"]]
        max_x = max(node_xs)
        for bus_id in ("gen-vsource", "gen-ground"):
            assert _node(data, bus_id)["properties"].get("anchors") is None
            far_end = next(n for n in data["nodes"] if n["id"].startswith(f"{bus_id}-b-"))
            assert far_end["type"] == "JunctionNodeItem"
            assert far_end["position"]["x"] >= max_x - _M.pl_spacing


def _bus_tap_owner(nid: str, bus_ids: set) -> str | None:
    """Identifies which bus (if any) owns node `nid` post-materialize --
    the bus's own node, its far-end "-b-..." JunctionNodeItem, or an
    interior "-j-..." JunctionNodeItem tap. See rail.py's materialize()."""
    if nid in bus_ids:
        return nid
    for bid in bus_ids:
        if nid.startswith(f"{bid}-b-") or nid.startswith(f"{bid}-j-"):
            return bid
    return None


class TestBusAnchorProximityReassignment:
    """Só existe UMA VoltageSource/Ground -- a reatribuição é um mapeamento
    monotônico: conexões ordenadas por X real do outro lado casam 1:1 com
    taps ordenados por X real -- garante zero cruzamento por construção.
    Post-migration: a "anchor" de cada conexão da barra agora é um nó REAL
    (a própria barra ou um JunctionNodeItem, interior ou "-b-" no fim
    distante) -- lê-se a posição x real desse nó via node_by_id em vez de
    indexar properties["anchors"]. Connections between two nodes that both
    belong to the SAME bus are the bus's own internal chain segments, not
    component connections, and are excluded."""

    def test_voltage_source_tap_assignment_is_monotonic_in_target_x(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        node_by_id = {n["id"]: n for n in data["nodes"]}
        bus_ids = {"gen-vsource"}

        rows = []
        for c in data["connections"]:
            s_owner = _bus_tap_owner(c["source"]["node"], bus_ids)
            if s_owner is None or _bus_tap_owner(c["target"]["node"], bus_ids) == s_owner:
                continue
            tap_x = node_by_id[c["source"]["node"]]["position"]["x"]
            target_x = node_by_id[c["target"]["node"]]["position"]["x"]
            rows.append((tap_x, target_x))
        rows.sort()
        target_xs = [r[1] for r in rows]
        assert len(rows) > 0
        assert target_xs == sorted(target_xs)

    def test_ground_tap_assignment_is_monotonic_in_source_x(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        node_by_id = {n["id"]: n for n in data["nodes"]}
        bus_ids = {"gen-ground"}

        rows = []
        for c in data["connections"]:
            t_owner = _bus_tap_owner(c["target"]["node"], bus_ids)
            if t_owner is None or _bus_tap_owner(c["source"]["node"], bus_ids) == t_owner:
                continue
            tap_x = node_by_id[c["target"]["node"]]["position"]["x"]
            source_x = node_by_id[c["source"]["node"]]["position"]["x"]
            rows.append((tap_x, source_x))
        rows.sort()
        source_xs = [r[1] for r in rows]
        assert len(rows) > 0
        assert source_xs == sorted(source_xs)


class TestBusAnchorReassignmentActuallyDoesSomething:
    """Achado de revisão: os dois testes acima só verificam que o resultado
    final é monotônico -- mas para TODA sequência real testável neste
    arquivo, a ordem de criação das conexões pelo gerador já é monotônica
    em X final (átomos e grupos de potência são sempre enumerados na mesma
    ordem esquerda->direita em que o layout os posiciona), então a
    reatribuição nunca muda nada observável por aqueles testes -- ela pode
    passar de forma idêntica com ou sem a reatribuição rodar. Este teste
    fabrica um cenário sintético (troca os `target` de duas conexões da
    VoltageSource antes de rodar layout.apply, criando deliberadamente uma
    ordem padrão NÃO monotônica) e confirma que layout.apply corrige isso
    -- prova de que o código de reatribuição realmente faz algo em vez de
    apenas preservar uma propriedade que já valia."""

    def test_reassignment_fixes_a_deliberately_scrambled_default_order(self):
        seq = "A+B+A-B-"
        raw = sbe.generate(parse(seq))
        vsource_conns = [c for c in raw["connections"] if c["source"]["node"] == "gen-vsource"]
        assert len(vsource_conns) >= 2, "sequência de teste não gerou conexões suficientes"
        first, last = vsource_conns[0], vsource_conns[-1]
        first["target"], last["target"] = last["target"], first["target"]
        # Snapshot of target node ids in raw creation order (== the order
        # next_bus_anchor's sequential X1, X2, ... would have paired them,
        # pre-rail.assign_sorted) -- this is the "naive" order the old
        # array-index anchors would have produced without reassignment.
        naive_target_ids = [c["target"]["node"] for c in vsource_conns]

        data = layout.apply(raw)
        node_by_id = {n["id"]: n for n in data["nodes"]}

        naive_target_xs = [node_by_id[tid]["position"]["x"] for tid in naive_target_ids]
        assert naive_target_xs != sorted(naive_target_xs), (
            "cenário sintético não ficou scrambled -- ajustar a troca de targets"
        )

        bus_ids = {"gen-vsource"}
        rows = []
        for c in data["connections"]:
            s_owner = _bus_tap_owner(c["source"]["node"], bus_ids)
            if s_owner is None or _bus_tap_owner(c["target"]["node"], bus_ids) == s_owner:
                continue
            tap_x = node_by_id[c["source"]["node"]]["position"]["x"]
            target_x = node_by_id[c["target"]["node"]]["position"]["x"]
            rows.append((tap_x, target_x))
        rows.sort()
        target_xs = [r[1] for r in rows]
        assert target_xs == sorted(target_xs), (
            "reatribuição não corrigiu a ordem sintética scrambled"
        )


class TestBusAnchorsGenuinelyNearest:
    """Achado de revisão original (pre-RailPlanner): o espalhamento por
    índice proporcional (ranking) ignora a posição real quando a
    distribuição dos targets não é uniforme -- o vão grande entre os
    blocos de átomo e a zona de potência produzia erro de até 1530px numa
    sequência de 12 átomos. rail.py's assign_sorted (Task 3) keeps the
    same sort-and-match approach (real X order on both sides), so this
    regression coverage carries over -- reading each tap's real x directly
    from its materialized node instead of an anchor-index formula. The old
    "spread beyond leftmost prefix" companion test (checking against a
    fixed-size anchors array) has no equivalent here: RailPlanner has no
    such array -- assign_sorted places exactly one tap per connection."""

    def test_max_tap_target_delta_stays_small(self):
        data = layout.apply(sbe.generate(parse("A+B+C+A-B-C-A+B+C+A-B-C-")))
        node_by_id = {n["id"]: n for n in data["nodes"]}
        bus_ids = {"gen-vsource"}

        max_delta = 0.0
        checked = 0
        for c in data["connections"]:
            s_owner = _bus_tap_owner(c["source"]["node"], bus_ids)
            if s_owner is None or _bus_tap_owner(c["target"]["node"], bus_ids) == s_owner:
                continue
            ax = node_by_id[c["source"]["node"]]["position"]["x"]
            tx = node_by_id[c["target"]["node"]]["position"]["x"]
            max_delta = max(max_delta, abs(ax - tx))
            checked += 1
        assert checked > 0
        assert max_delta < 200, f"max delta {max_delta} -- esperado bem abaixo de 200px"

    def test_max_tap_source_delta_stays_small_ground(self):
        # Achado de revisão: o teste acima só cobre a barra VoltageSource --
        # espelha o mesmo teste pro lado Ground (Ground não tinha bug
        # conhecido, isso só confirma que o comportamento também é correto
        # lá).
        data = layout.apply(sbe.generate(parse("A+B+C+A-B-C-A+B+C+A-B-C-")))
        node_by_id = {n["id"]: n for n in data["nodes"]}
        bus_ids = {"gen-ground"}

        max_delta = 0.0
        checked = 0
        for c in data["connections"]:
            t_owner = _bus_tap_owner(c["target"]["node"], bus_ids)
            if t_owner is None or _bus_tap_owner(c["source"]["node"], bus_ids) == t_owner:
                continue
            ax = node_by_id[c["target"]["node"]]["position"]["x"]
            sx = node_by_id[c["source"]["node"]]["position"]["x"]
            max_delta = max(max_delta, abs(ax - sx))
            checked += 1
        assert checked > 0
        assert max_delta < 200, f"max delta {max_delta} -- esperado bem abaixo de 200px"


class TestBusAnchorsDistinctPerConnection:
    """Achado de revisão original: a busca de vizinho-mais-próximo pura
    (sem guarda contra colisão de índice) podia atribuir o MESMO anchor a
    duas conexões diferentes da mesma barra quando dois targets caem no
    mesmo X real -- caso real dos contatos de potência empilhados em
    múltiplos ciclos (mesma coluna X, Y diferente -- ver
    TestMultiCyclePowerStacking). O resultado visível era dois fios
    roteados exatamente sobrepostos. rail.py's assign_sorted (Task 3)
    enforces min_spacing between taps unconditionally, so the equivalent
    check post-migration is: every connection into a bus resolves to its
    OWN tap node, and no two taps of the same bus share a real (x, y)
    position (TestMultiCyclePowerStacking already covers this for
    stacked power contacts specifically at the node level; this is the
    integration-level, bus-side check, across more reference sequences)."""

    @pytest.mark.parametrize("seq", [
        "A+B+A-B-",
        "C+(A+B+)C-A-B-",
        "A+B+A-A+B-A-",
        "A+B+C+A-B-C-A+B+C+A-B-C-",
    ])
    def test_no_two_bus_taps_share_a_position(self, seq):
        data = layout.apply(sbe.generate(parse(seq)))
        node_by_id = {n["id"]: n for n in data["nodes"]}

        for bus_id in ("gen-vsource", "gen-ground"):
            bus_ids = {bus_id}
            tap_positions = []
            for c in data["connections"]:
                for side, other in ((c["source"], c["target"]), (c["target"], c["source"])):
                    owner = _bus_tap_owner(side["node"], bus_ids)
                    if owner is None or _bus_tap_owner(other["node"], bus_ids) == owner:
                        continue  # not this bus, or an internal bus-chain segment
                    pos = node_by_id[side["node"]]["position"]
                    tap_positions.append((pos["x"], pos["y"]))
            assert len(tap_positions) == len(set(tap_positions)), (
                f"taps compartilhando posição na barra {bus_id} para {seq!r}: {tap_positions}"
            )


class TestAllConnectionsOrthogonal:
    @pytest.mark.parametrize("seq", ["A+B+A-B-", "A+B+A-A+B-A-", "C+(A+B+)C-A-B-"])
    def test_no_diagonal_connections(self, seq):
        data = layout.apply(sbe.generate(parse(seq)))
        assert data["connections"], "circuito de teste sem nenhuma conexão"
        for conn in data["connections"]:
            _assert_connection_orthogonal(data, conn)


class TestBusConnectionsRouteDeterministicallyVH:
    """VoltageSource/Ground usam roteamento VH determinístico (não A*) -- ver
    docs/superpowers/specs (fix do "degrau" acima da barra +24V, causado por
    snap de exit-point do A* perto do retângulo de bloqueio do sprite).

    Identifies "connections from/to the bus" via _bus_tap_owner (any node
    belonging to the bus post-materialize: the bus's own node, an interior
    JunctionNodeItem tap, or the far-end JunctionNodeItem) instead of the
    old plain node-type check -- after rail.materialize(), only ONE
    connection (the bus's own unconditional internal chain link) still has
    the literal VoltageSource/Ground type as its node, so a type-only
    check would make these tests vacuous (checking nothing) for every
    other, real component<->bus connection. Excludes the bus's own
    internal chain segments (both sides on the same bus) -- those draw
    the physical rail itself, not component wiring, and are not subject to
    this invariant (see rail.py's materialize(): the bus's own sprite
    anchor uses its real height*0.69 offset while interior/far-end
    JunctionNodeItem taps sit at the bus's raw un-offset y -- a small,
    pre-existing vertical mismatch inherent to materialize() for every bus
    type, e.g. PressureLine's pl_pix_h offset vs. its JunctionNodeItem
    taps, not something introduced by this file)."""

    @pytest.mark.parametrize("seq", ["A+B+A-B-", "A+B+A-A+B-A-", "C+(A+B+)C-A-B-"])
    def test_voltage_source_connections_never_go_above_the_source_anchor(self, seq):
        data = layout.apply(sbe.generate(parse(seq)))
        node_by_id = {n["id"]: n for n in data["nodes"]}
        node_type_map = {n["id"]: n["type"] for n in data["nodes"]}
        bus_ids = {"gen-vsource"}
        checked = 0
        for conn in data["connections"]:
            s_owner = _bus_tap_owner(conn["source"]["node"], bus_ids)
            if s_owner is None or _bus_tap_owner(conn["target"]["node"], bus_ids) == s_owner:
                continue
            src_x, src_y = _scene_xy(
                node_by_id, node_type_map, conn["source"]["node"], conn["source"]["anchor"])
            for wp in conn.get("waypoints", []):
                assert wp["y"] >= src_y - 0.5, (
                    f"waypoint {wp} sobe acima do anchor fonte {(src_x, src_y)} em {conn}"
                )
            checked += 1
        assert checked > 0

    @pytest.mark.parametrize("seq", ["A+B+A-B-", "A+B+A-A+B-A-", "C+(A+B+)C-A-B-"])
    def test_ground_connections_never_go_below_the_ground_anchor(self, seq):
        data = layout.apply(sbe.generate(parse(seq)))
        node_by_id = {n["id"]: n for n in data["nodes"]}
        node_type_map = {n["id"]: n["type"] for n in data["nodes"]}
        bus_ids = {"gen-ground"}
        checked = 0
        for conn in data["connections"]:
            t_owner = _bus_tap_owner(conn["target"]["node"], bus_ids)
            if t_owner is None or _bus_tap_owner(conn["source"]["node"], bus_ids) == t_owner:
                continue
            tgt_x, tgt_y = _scene_xy(
                node_by_id, node_type_map, conn["target"]["node"], conn["target"]["anchor"])
            for wp in conn.get("waypoints", []):
                assert wp["y"] <= tgt_y + 0.5, (
                    f"waypoint {wp} desce abaixo do anchor terra {(tgt_x, tgt_y)} em {conn}"
                )
            checked += 1
        assert checked > 0

    @pytest.mark.parametrize("seq", ["A+B+A-B-", "A+B+A-A+B-A-", "C+(A+B+)C-A-B-"])
    def test_voltage_source_connections_have_at_most_two_waypoints(self, seq):
        """VH determinístico: no máximo 1 jog horizontal -> no máximo 2 waypoints."""
        data = layout.apply(sbe.generate(parse(seq)))
        bus_ids = {"gen-vsource"}
        checked = 0
        for conn in data["connections"]:
            s_owner = _bus_tap_owner(conn["source"]["node"], bus_ids)
            if s_owner is None or _bus_tap_owner(conn["target"]["node"], bus_ids) == s_owner:
                continue
            assert len(conn.get("waypoints", [])) <= 2, conn
            checked += 1
        assert checked > 0


class TestRegressionCounts:
    """Counts grew after the RailPlanner migration: rail.py's materialize()
    (Task 2/3) adds one real node (a JunctionNodeItem, interior tap or
    far-end) AND one connection (the chain segment leading to it) per bus
    tap, replacing the old single-node properties["anchors"] array -- see
    task-7-report.md."""

    @pytest.mark.parametrize("seq,n_nodes,n_conns", [
        ("A+B+A-B-", 62, 73),
        ("C+(A+B+)C-A-B-", 83, 98),
        ("A+B+A-A+B-A-", 82, 99),
    ])
    def test_node_and_connection_counts_unchanged_from_topology(self, seq, n_nodes, n_conns):
        data = layout.apply(sbe.generate(parse(seq)))
        assert len(data["nodes"]) == n_nodes
        assert len(data["connections"]) == n_conns
