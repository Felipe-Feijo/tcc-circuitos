import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.sequence_parser import parse
from circuit_generator.methods import cascade
from circuit_generator import cascade_layout as layout


def _node(data, node_id):
    return next(n for n in data["nodes"] if n["id"] == node_id)


class TestRoleMaps:
    def test_role_maps_extract_cylinders_v42_pl_memory(self):
        # NOTE: the brief's literal draft used "A+B+A-B-A+A-" here, but that
        # sequence produces 4 pressure_line_group nodes and 3 memory nodes
        # under cascade.generate()'s (unchanged) grouping algorithm --
        # verified via sequence_parser.split_into_groups, which starts a new
        # cascade group whenever a letter repeats within the current group:
        # "A+B+A-B-A+A-" -> [[A+,B+],[A-,B-],[A+],[A-]] (4 groups), not the
        # 2 groups / 1 memory this test asserts. "A+B+A-B-" (this sequence,
        # without the trailing "A+A-") is the shortest input that actually
        # produces the asserted role maps -- confirmed by running
        # cascade.generate() directly.
        data = cascade.generate(parse("A+B+A-B-"))
        roles = layout._build_role_maps(data)
        assert roles["cyl_by_letter"] == {"A": "gen-cyl-A", "B": "gen-cyl-B"}
        assert roles["v42_by_letter"] == {"A": "gen-v42-A", "B": "gen-v42-B"}
        assert roles["pl_by_idx"] == {0: "gen-pl-grp1", 1: "gen-pl-grp2"}
        assert roles["mc_by_idx"] == {0: "gen-mc-0"}
        assert roles["btn_id"] == "gen-btn"
        assert roles["n_groups"] == 2
        assert roles["n_mc"] == 1


class TestPistonValveRegion:
    def test_cylinders_and_v42_positioned_same_column_per_letter(self):
        data = cascade.generate(parse("A+B+A-B-A+A-"))
        result = layout.apply(data)
        cyl_a = _node(result, "gen-cyl-A")
        v42_a = _node(result, "gen-v42-A")
        assert cyl_a["position"]["x"] == v42_a["position"]["x"]
        assert cyl_a["position"]["y"] != v42_a["position"]["y"]

    def test_different_letters_get_different_columns(self):
        data = cascade.generate(parse("A+B+A-B-A+A-"))
        result = layout.apply(data)
        cyl_a = _node(result, "gen-cyl-A")
        cyl_b = _node(result, "gen-cyl-B")
        assert cyl_a["position"]["x"] != cyl_b["position"]["x"]


class TestTriggerSourceChains:
    def test_single_group_no_repeat_gives_one_raw_leaf_per_side(self):
        # "A+B+A-B-": split_into_groups gives 2 groups ([A+,B+], [A-,B-]),
        # each atomized into 2 single-event atoms (no parallel blocks, so
        # every event is its own atom -- see cascade._atomize_group). Only
        # the FIRST atom of a group is a raw source (entry_sources is None
        # -> fed straight from the group's PressureLine bus); every later
        # atom in the same group is triggered by the confirmation sig of
        # the atom before it. A+ is the first atom of group 0 -> raw.
        # B+ is the SECOND atom of group 0 -> NOT raw, it is confirmed by
        # a single sig (the "A extended" limit switch), depth 1.
        #
        # The brief's literal draft asserted sources[("B", "PR")] == [[]]
        # (claiming "every source here is the first atom of its group, so
        # every source is raw"), but B- is the second atom of group 1
        # (after A-), just like B+ is the second atom of group 0 -- so
        # its PR side is fed by 1 sig (gen-sig-A-ret-2, confirming A-),
        # not raw. Verified by dumping cascade.generate(parse("A+B+A-B-"))
        # ["connections"] directly: it contains
        # "gen-sig-A-ret-2.A -> gen-v42-B.PR" (a sig->pilot edge), and
        # "gen-pl-grp2.X3 -> gen-sig-A-ret-2.P" (that sig's P comes
        # straight from the group bus, i.e. depth 1, not chained further).
        data = cascade.generate(parse("A+B+A-B-"))
        roles = layout._build_role_maps(data)
        sources = layout._build_trigger_sources(data, roles)
        assert sources[("A", "PL")] == [[]]
        assert sources[("B", "PR")] == [["gen-sig-A-ret-2"]]

    def test_repeated_movement_gives_two_leaves(self):
        # "A+B+A-B-B+B-": B+ ocorre 2x (grupo1 átomo1, grupo2 átomo0) ->
        # 2 fontes no lado PL de B. A segunda ocorrência (grupo2, primeiro
        # átomo do grupo) é crua; a primeira (grupo1, NÃO primeiro átomo,
        # precedida por A+) vem de 1 sig (confirmação de A+, fan_out=1).
        data = cascade.generate(parse("A+B+A-B-B+B-"))
        roles = layout._build_role_maps(data)
        sources = layout._build_trigger_sources(data, roles)
        leaves = sources[("B", "PL")]
        assert len(leaves) == 2
        depths = sorted(len(leaf) for leaf in leaves)
        assert depths == [0, 1]

    def test_leaf_preceded_by_parallel_block_has_depth_two(self):
        # "(A+C+)B+A-B-C-B+B-": B+ ocorre 2x. A 1a ocorrência (grupo1,
        # átomo1) é precedida pelo bloco (A+C+) (átomo0, 2 eventos) ->
        # cadeia serial de 2 sigs. A 2a ocorrência (grupo2, átomo0) é
        # crua.
        data = cascade.generate(parse("(A+C+)B+A-B-C-B+B-"))
        roles = layout._build_role_maps(data)
        sources = layout._build_trigger_sources(data, roles)
        leaves = sources[("B", "PL")]
        assert len(leaves) == 2
        depths = sorted(len(leaf) for leaf in leaves)
        assert depths == [0, 2]


class TestOrSigStaircase:
    def test_multi_cycle_creates_one_or_and_two_leaf_columns(self):
        # "A+B+A-B-B+B-": B+ tem 2 fontes -> 1 OrValve, 2 colunas de folha.
        data = cascade.generate(parse("A+B+A-B-B+B-"))
        result = layout.apply(data)
        or_nodes = [n for n in result["nodes"] if n["type"] == "OrValve"]
        assert len(or_nodes) == 2  # 1 no lado PL de B, 1 no lado PR de B
        for n in or_nodes:
            assert n["position"] != {"x": 0, "y": 0}
        # 2 colunas distintas por lado -> 2 x distintos entre as 2 OrValve
        xs = {round(n["position"]["x"]) for n in or_nodes}
        assert len(xs) == 2

    def test_deep_leaf_chain_stacks_vertically_without_colliding(self):
        # "(A+C+)B+A-B-C-B+B-": uma das folhas de B+ tem cadeia de
        # profundidade 2 -- as 2 sigs dessa cadeia ficam na MESMA coluna,
        # linhas diferentes.
        data = cascade.generate(parse("(A+C+)B+A-B-C-B+B-"))
        roles = layout._build_role_maps(data)
        sources = layout._build_trigger_sources(data, roles)
        deep_leaf = next(leaf for leaf in sources[("B", "PL")] if len(leaf) == 2)
        result = layout.apply(data)
        sig0 = _node(result, deep_leaf[0])
        sig1 = _node(result, deep_leaf[1])
        assert sig0["position"]["x"] == sig1["position"]["x"]
        assert sig0["position"]["y"] != sig1["position"]["y"]

    def test_pl_and_pr_or_rows_align_at_the_same_height_per_cylinder(self):
        # A altura (linhas) da região de OR/sig é uniforme pros dois lados
        # do MESMO cilindro -- mesmo se só um lado tiver cadeia profunda.
        data = cascade.generate(parse("(A+C+)B+A-B-C-B+B-"))
        role_by_id = {n["id"]: n.get("_role", "") for n in data["nodes"]}
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        pl_or = next(nid for nid, r in role_by_id.items() if r.startswith("or_valve:B:PL:"))
        pr_or = next(nid for nid, r in role_by_id.items() if r.startswith("or_valve:B:PR:"))
        assert node_by_id[pl_or]["position"]["y"] == node_by_id[pr_or]["position"]["y"]

    def test_or_rows_are_shared_globally_across_different_cylinders(self):
        # Documenta explicitamente o design ATUAL (intencional, não
        # acidental): or_row e sig_stack_{depth} são linhas GLOBAIS,
        # compartilhadas por TODOS os cilindros do circuito -- não uma
        # linha por cilindro. Isso é uma consequência mais forte do que
        # "PL e PR do MESMO cilindro compartilham altura" (que também vale,
        # ver test_pl_and_pr_or_rows_align_at_the_same_height_per_cylinder),
        # mas é o comportamento real hoje: aqui, tanto o OR de B (lado PL)
        # quanto o OR de C (lado PL) caem na mesma or_row -> mesmo y.
        data = cascade.generate(parse("A+B+C+A-B-C-A+B+C+A-B-C-"))
        role_by_id = {n["id"]: n.get("_role", "") for n in data["nodes"]}
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        b_or = next(nid for nid, r in role_by_id.items() if r.startswith("or_valve:B:PL:"))
        c_or = next(nid for nid, r in role_by_id.items() if r.startswith("or_valve:C:PL:"))
        assert node_by_id[b_or]["position"]["y"] == node_by_id[c_or]["position"]["y"]
        assert node_by_id[b_or]["position"]["x"] != node_by_id[c_or]["position"]["x"]

    def test_multi_cylinder_multi_cycle_sequence_does_not_raise_and_has_no_collisions(self):
        # Regressão: sequência com 3 cilindros e 2 ciclos completos produz,
        # pro lado PR de cada cilindro, folhas cujo vcol é DESCENDENTE em j
        # (offset = n pra j==0, depois n-j) -- chamar _place_aligned na
        # ordem de iteração de j (em vez de ordem ascendente de vcol)
        # colidia com um placeholder já reservado e lançava ValueError.
        # Ver circuit_generator/cascade_layout.py, bloco "Posiciona as
        # cadeias de sig de cada folha".
        # Nem todo Valve_3_2_Ways gerado entra numa cadeia de folha desta
        # Região A (alguns sigs só serão usados na Região B, Tasks 4/5,
        # ainda não implementada) -- esses ficam no placeholder {0, 0} de
        # cascade.generate e são ignorados aqui, mesma convenção já usada
        # em test_multi_cycle_creates_one_or_and_two_leaf_columns acima.
        data = cascade.generate(parse("A+B+C+A-B-C-A+B+C+A-B-C-"))
        result = layout.apply(data)  # não deve lançar ValueError
        positions = [(n["position"]["x"], n["position"]["y"]) for n in result["nodes"]
                     if n["type"] in ("Valve_3_2_Ways", "OrValve")
                     and n["position"] != {"x": 0, "y": 0}]
        assert len(positions) == len(set(positions))

    def test_pl_rows_start_below_the_deepest_sig_stack_row(self):
        # Regressão real: pl_base_y (Região B) somava só
        # `len(sig_stack_row_ids_created) * v32_height * 1.5` ao topo de
        # or_row, esquecendo de somar a ALTURA do próprio corpo da linha
        # mais funda -- com profundidade 2 (bloco paralelo antes de um
        # multi-ciclo), a linha de PL mais alta (pl_base_y=1040) começava
        # 10px ANTES do fim do sig_stack mais fundo (870..1050), uma
        # sobreposição real de sprite.
        #
        # Só os sigs da REGIÃO A (folhas de _build_trigger_sources, que
        # ficam empilhadas logo abaixo de or_row) importam aqui -- os sigs
        # de confirmação da Região B (confirm_row) ficam ainda mais abaixo
        # de qualquer forma, então incluí-los no cálculo do "mais fundo"
        # tornaria este teste verdadeiro mesmo sem o fix (falso negativo).
        from circuit_generator.sprite_metrics import METRICS as _M
        seq = "(A+C+)B+A-B-C-B+B-A+A-"
        data = cascade.generate(parse(seq))
        roles = layout._build_role_maps(data)
        sources = layout._build_trigger_sources(data, roles)
        region_a_sig_ids = {
            sig_id
            for leaves in sources.values()
            for leaf in leaves
            for sig_id in leaf
        }
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}

        sig_stack_bottoms = [node_by_id[sid]["position"]["y"] + _M.v32_height
                              for sid in region_a_sig_ids]
        pl_tops = [n["position"]["y"] for n in result["nodes"] if n["type"] == "PressureLine"]
        assert sig_stack_bottoms  # sanity check: a sequência precisa exercitar cadeia com profundidade > 0
        assert min(pl_tops) >= max(sig_stack_bottoms), (
            f"PL mais alta (y={min(pl_tops)}) sobrepõe o sig_stack mais "
            f"fundo da Região A (termina em y={max(sig_stack_bottoms)})"
        )


class TestLogicRegionRows:
    # NOTE: the brief's literal draft used "A+B+A-B-A+A-" for every test in
    # this class, with a "# n_groups=2, n_mc=1" comment. As already found in
    # TestRoleMaps above, that sequence actually produces n_groups=4,
    # n_mc=3 under cascade.generate()'s grouping algorithm -- confirmed by
    # running layout._build_role_maps() directly. With n_groups=4, mem[0].B
    # connects to pl_grp[M-1-0] = pl_grp4 (0-idx 3), not pl_grp2 (0-idx 1)
    # as test_memory_sits_on_the_row_of_the_pl_it_drives_via_b asserts --
    # confirmed by dumping cascade.generate(parse("A+B+A-B-A+A-"))
    # ["connections"]: it contains "gen-mc-0 B -> gen-pl-grp4 X1", never
    # "-> gen-pl-grp2". "A+B+A-B-" (used by TestRoleMaps for the same
    # reason) is the shortest sequence that actually yields the n_groups=2,
    # n_mc=1 the brief's comment and assertions assume -- verified the same
    # way: it produces "gen-mc-0 B -> gen-pl-grp2 X1", matching the test.
    def test_pressure_lines_are_grid_rows_stacked_by_group_index(self):
        data = cascade.generate(parse("A+B+A-B-"))  # n_groups=2, n_mc=1
        result = layout.apply(data)
        pl0 = _node(result, "gen-pl-grp1")
        pl1 = _node(result, "gen-pl-grp2")
        assert pl0["position"]["y"] < pl1["position"]["y"]
        assert pl0["position"] != {"x": 0, "y": 0}

    def test_memory_block_sits_entirely_below_every_pressure_line(self):
        # Regressão real: a versão anterior colocava mem[i] na MESMA linha
        # (mesmo y) da PL que ele aciona via B -- como a PL é desenhada
        # como um traço fino nessa altura, o corpo bem mais alto da
        # memória (v52_height) acabava cruzando por CIMA do traço da PL
        # (visível testando na UI real). O bloco de memórias inteiro
        # precisa ficar abaixo de TODAS as PLs, nunca na mesma altura de
        # nenhuma delas -- mesmo padrão de step_by_step_layout.py (região
        # de lógica sempre abaixo da região de PL, nunca intercalada).
        data = cascade.generate(parse("A+B+A-B-A+A-C+C-"))  # 5 grupos, 4 memórias
        result = layout.apply(data)
        pl_ys = [_node(result, f"gen-pl-grp{g}")["position"]["y"] for g in range(1, 6)]
        mem_ys = [_node(result, f"gen-mc-{i}")["position"]["y"] for i in range(4)]
        assert min(mem_ys) > max(pl_ys), (
            f"memória mais alta (y={min(mem_ys)}) não fica abaixo da PL "
            f"mais baixa (y={max(pl_ys)})"
        )

    def test_memory_order_still_matches_the_pl_it_drives_via_b(self):
        # O mapeamento lógico mem[i] <-> pl_grp[n_groups-1-i] continua
        # valendo mesmo com o bloco de memórias deslocado pra baixo --
        # mem[0] (a mais baixa) confirma o grupo mais baixo (pl_grp de
        # maior índice), mem[n_mc-1] (a mais alta) confirma o mais alto.
        data = cascade.generate(parse("A+B+A-B-A+A-C+C-"))
        result = layout.apply(data)
        mc0 = _node(result, "gen-mc-0")
        mc3 = _node(result, "gen-mc-3")  # topo, per test_topmost_memory_confirmation...
        assert mc0["position"]["y"] > mc3["position"]["y"]

    def test_closure_sig_sits_in_the_button_column_not_the_confirmation_staircase(self):
        # Regressão real (achada testando na UI): a cadeia de fechamento
        # (btn.P) estava entrando na MESMA escada de confirmação das
        # memórias (colunas à direita, offset acumulado) -- deveria ficar
        # na coluna do PRÓPRIO botão, empilhada logo abaixo dele, igual
        # ao btn_row/closure_row/closure_stack_N do passo a passo.
        seq = "A+B+A-B-A+A-C+C-"
        data = cascade.generate(parse(seq))
        roles = layout._build_role_maps(data)
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        btn = node_by_id[roles["btn_id"]]
        closure_sig_id = next(
            c["source"]["node"] for c in result["connections"]
            if c["target"]["node"] == roles["btn_id"] and c["target"]["anchor"] == "P"
        )
        closure_sig = node_by_id[closure_sig_id]
        assert closure_sig["position"]["x"] == btn["position"]["x"]
        assert closure_sig["position"]["y"] > btn["position"]["y"]

    def test_confirmation_chain_p_connections_exit_to_the_right_clearing_the_spring(self):
        # Regressão real (feedback direto testando a UI, com imagem
        # anotada): a conexão PL -> sig.P das cadeias de confirmação da
        # Região B (mem.PR e btn.P) entrava pela ESQUERDA (mesma lógica
        # herdada do passo a passo para a Região A), passando por cima da
        # mola quando a válvula estava no estado comutado (BODY_VISUALS[1]
        # desloca o sprite +147px). Precisa sair pela DIREITA -- o
        # endpoint final já é o pior-caso ajustado por
        # anchor_local_for_routing("Valve_3_2_Ways","P") (mesmo fix de
        # sprite_metrics.py), então o anchor de PL escolhido só precisa
        # ficar à direita do sig (nunca à esquerda dele -- entrar pela
        # esquerda é exatamente o bug original).
        from circuit_generator.sprite_metrics import anchor_local_for_routing

        seq = "A+B+A-B-A+A-C+C-"
        data = cascade.generate(parse(seq))
        roles = layout._build_role_maps(data)
        sources = layout._build_trigger_sources(data, roles)
        region_a_sig_ids = {sid for leaves in sources.values() for leaf in leaves for sid in leaf}

        # A cadeia de fechamento (btn.P) também entra pela esquerda (ver
        # test_closure_sig_still_enters_from_the_left abaixo) -- excluída
        # aqui do jeito mesmo, andando pra trás a partir de btn.P via
        # sig.A -> sig.P, sem duplicar _chain_feeding (privada do módulo).
        raw_data = cascade.generate(parse(seq))
        node_type_map_raw = {n["id"]: n["type"] for n in raw_data["nodes"]}
        sig_in_raw: dict[str, str] = {}
        for c in raw_data["connections"]:
            if (node_type_map_raw.get(c["target"]["node"]) == "Valve_3_2_Ways"
                    and c["target"]["anchor"] == "P"
                    and node_type_map_raw.get(c["source"]["node"]) == "Valve_3_2_Ways"):
                sig_in_raw[c["target"]["node"]] = c["source"]["node"]
        closure_sig_ids = set()
        head = next((c["source"]["node"] for c in raw_data["connections"]
                     if c["target"]["node"] == roles["btn_id"] and c["target"]["anchor"] == "P"), None)
        while head is not None:
            closure_sig_ids.add(head)
            head = sig_in_raw.get(head)

        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        node_type_map = {n["id"]: n["type"] for n in result["nodes"]}

        p_local_x = anchor_local_for_routing("Valve_3_2_Ways", "P")[0]
        checked = 0
        for conn in result["connections"]:
            s, t = conn["source"], conn["target"]
            if (t["anchor"] != "P" or node_type_map.get(t["node"]) != "Valve_3_2_Ways"
                    or node_type_map.get(s["node"]) != "PressureLine"
                    or t["node"] in region_a_sig_ids
                    or t["node"] in closure_sig_ids):
                continue
            wps = conn.get("waypoints")
            assert wps, f"conexão {s} -> {t} sem waypoints"
            entry_x = wps[-1]["x"]
            sig_x = node_by_id[t["node"]]["position"]["x"]
            assert entry_x >= sig_x, (
                f"{s} -> {t}: entrada em x={entry_x} ficou à ESQUERDA do "
                f"sig (x={sig_x}) -- exatamente o bug original"
            )
            # o endpoint final é sempre o pior-caso ajustado (sig_x + P local
            # com deslocamento de comutação), independente do estado real
            assert abs(entry_x - (sig_x + p_local_x)) < 1.0, (
                f"{s} -> {t}: entrada em x={entry_x} não bate com o "
                f"endpoint pior-caso esperado x={sig_x + p_local_x}"
            )
            checked += 1
        assert checked > 0  # sanity check -- a sequência precisa exercitar ao menos 1 dessas conexões

    def test_closure_sig_still_enters_from_the_left(self):
        # Feedback direto do usuário: a sig que alimenta o botão (cadeia
        # de fechamento) deve CONTINUAR entrando pela esquerda, igual ao
        # passo a passo -- só a escada de confirmação PR das memórias
        # precisa da abordagem pela direita (ver
        # test_confirmation_chain_p_connections_exit_to_the_right_clearing_the_spring
        # acima). Verifica que o caminho passa por algum ponto à ESQUERDA
        # do sig antes de entrar (diferente da abordagem pela direita, que
        # nunca visita um x menor que o do sig).
        seq = "A+B+A-B-A+A-C+C-"
        data = cascade.generate(parse(seq))
        roles = layout._build_role_maps(data)
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}

        closure_sig_id = next(
            c["source"]["node"] for c in result["connections"]
            if c["target"]["node"] == roles["btn_id"] and c["target"]["anchor"] == "P"
        )
        conn = next(c for c in result["connections"]
                    if c["target"]["node"] == closure_sig_id and c["target"]["anchor"] == "P")
        wps = conn.get("waypoints")
        assert wps, f"conexão {conn['source']} -> {conn['target']} sem waypoints"
        sig_x = node_by_id[closure_sig_id]["position"]["x"]
        assert any(wp["x"] < sig_x for wp in wps), (
            f"caminho da sig de fechamento nunca visita x < {sig_x} -- "
            f"não está entrando pela esquerda"
        )

    def test_button_sits_one_row_below_the_bottom_memory(self):
        import json
        cfg = json.loads(layout._CONFIG_PATH.read_text(encoding="utf-8"))
        row_gap = cfg["rows"]["logic_row_gap"]

        data = cascade.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        mc0 = _node(result, "gen-mc-0")
        btn = _node(result, "gen-btn")
        assert btn["position"]["y"] == mc0["position"]["y"] + row_gap
        assert btn["position"]["x"] != mc0["position"]["x"]

    def test_memories_and_button_occupy_distinct_columns(self):
        data = cascade.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        mc0 = _node(result, "gen-mc-0")
        btn = _node(result, "gen-btn")
        assert mc0["position"]["x"] != btn["position"]["x"]


class TestConfirmationStaircase:
    def test_no_two_confirmation_sigs_share_a_column_across_rows(self):
        # 5 groups, 4 memories under cascade.generate()'s grouping (verified
        # via layout._build_role_maps -- the brief's draft comment said
        # "3 groups, 2 memories", which is not what this sequence produces).
        data = cascade.generate(parse("A+B+A-B-A+A-C+C-"))
        result = layout.apply(data)
        role_by_id = {n["id"]: n.get("_role", "") for n in
                      cascade.generate(parse("A+B+A-B-A+A-C+C-"))["nodes"]}
        confirm_sigs = [n for n in result["nodes"]
                        if n["type"] == "Valve_3_2_Ways"
                        and role_by_id.get(n["id"], "").startswith("signal_valve:")
                        and n["position"]["x"] > _node(result, "gen-mc-0")["position"]["x"]]
        xs = [round(n["position"]["x"]) for n in confirm_sigs]
        assert len(xs) == len(set(xs)), f"colunas repetidas: {xs}"

    def test_topmost_memory_confirmation_is_the_innermost_column(self):
        # NOTE: the brief's draft used a guessed id "gen-sig-C-ret-9" here.
        # Verified the real id by running cascade.generate(parse(...)) and
        # dumping data["connections"] for the (letter, "PR") edges into each
        # mem[i].PR: with n_mc=4, mc_by_idx = {0: gen-mc-0, .., 3: gen-mc-3},
        # and the topmost row (offset 0, processed first by apply()'s
        # ordered_targets = mc_by_idx[n_mc-1 .. 0]) is gen-mc-3 (smallest y
        # -- confirmed both by pl_row_y/local-row arithmetic in Task 4's
        # code and by directly reading positions after layout.apply()).
        # gen-mc-3.PR is fed straight from a PressureLine via a single sig,
        # gen-sig-B-ext-1 (connection "gen-sig-B-ext-1.A -> gen-mc-3.PR",
        # "gen-pl-grp1.X4 -> gen-sig-B-ext-1.P") -- chain length 1, so it
        # lands at offset 0 -> virtual_col 1 -> mem_col_x + one cell width.
        data = cascade.generate(parse("A+B+A-B-A+A-C+C-"))
        result = layout.apply(data)
        mem_col_x = _node(result, "gen-mc-1")["position"]["x"]  # any mem: shared column
        confirm = _node(result, "gen-sig-B-ext-1")
        assert confirm["position"]["x"] == mem_col_x + layout._logic_cell_width()

    def test_confirmation_sig_sits_diagonally_below_its_memory(self):
        # Decisão confirmada com o usuário: a sig de confirmação PR fica
        # na MESMA regra diagonal já usada pro par botão/mem[0] (1 linha
        # abaixo de quem ela alimenta), não mais na mesma linha da
        # memória -- consistência com o resto da Região B.
        import json
        cfg = json.loads(layout._CONFIG_PATH.read_text(encoding="utf-8"))
        row_gap = cfg["rows"]["logic_row_gap"]

        data = cascade.generate(parse("A+B+A-B-A+A-C+C-"))
        result = layout.apply(data)
        mc3 = _node(result, "gen-mc-3")  # topo, per test acima
        confirm = _node(result, "gen-sig-B-ext-1")
        assert confirm["position"]["y"] == mc3["position"]["y"] + row_gap

    def test_pl_gap_leaves_room_for_the_diagonal_confirmation_sig(self):
        # rows["pl_gap"] (espaçamento entre linhas de memória) precisa ser
        # >= logic_row_gap + v32_height, senão a sig diagonal de uma
        # memória invade o espaço da próxima memória abaixo dela.
        import json
        from circuit_generator.sprite_metrics import METRICS as _M
        cfg = json.loads(layout._CONFIG_PATH.read_text(encoding="utf-8"))
        assert cfg["rows"]["pl_gap"] >= cfg["rows"]["logic_row_gap"] + _M.v32_height

    def test_deep_row_confirmation_grows_in_columns_not_rows(self):
        # Se a confirmação de uma memória for uma cadeia de 2 sigs (bloco
        # paralelo antes dela), as 2 sigs ficam na MESMA linha (mesmo y),
        # colunas diferentes.
        #
        # NOTE: the brief's draft filtered on
        # role.startswith("signal_valve:2") assuming role encodes chain
        # depth -- it does not (cascade.py builds it as
        # f"signal_valve:{g_idx*100+e_idx}{role_suffix}", verified by
        # reading circuit_generator/methods/cascade.py line ~299 and by
        # dumping the real roles for this sequence: no role starts with
        # "signal_valve:2" at all here). Verified directly instead, by
        # walking the mem[i].PR chains the same way apply() does: for
        # "A+B+(A-B-)A+A-" (n_groups=4, n_mc=3), mem[1] (gen-mc-1) is the
        # only target whose confirmation chain has length 2 --
        # ["gen-sig-A-ret-2", "gen-sig-B-ret-3"] (the parallel block
        # (A-B-) preceding it).
        data = cascade.generate(parse("A+B+(A-B-)A+A-"))
        result = layout.apply(data)
        chain_sigs = [_node(result, "gen-sig-A-ret-2"), _node(result, "gen-sig-B-ret-3")]
        assert chain_sigs[0]["position"]["y"] == chain_sigs[1]["position"]["y"]
        assert chain_sigs[0]["position"]["x"] != chain_sigs[1]["position"]["x"]


class TestMemoryToPressureLineStagger:
    def test_different_memories_never_share_the_same_pl_anchor(self):
        # Regressão real (feedback direto testando a UI): mem[i].PL/A/B ->
        # PL sempre mirava no MESMO src_x (o anchor local não depende de
        # qual memória, só do tipo/anchor) -- diferentes memórias
        # acabavam escolhendo o mesmo índice de anchor em suas respectivas
        # PLs (não pega na checagem de conflito porque essas conexões não
        # se cruzam entre si, só ficam empilhadas na mesma coluna,
        # atravessando o corpo de outras memórias/sigs no caminho).
        # Checa por tipo de anchor de origem (PL / A / B) separadamente --
        # duas memórias diferentes usando o mesmo índice pra tipos DE
        # ORIGEM diferentes (ex: mem[1].B e mem[3].A) não é o problema
        # relatado (são conexões de natureza diferente, não ficam
        # empilhadas uma sobre a outra); o que precisa ser único é o
        # anchor entre memórias diferentes que usam o MESMO anchor de
        # origem (ex: mem[0].B vs mem[1].B vs mem[2].B).
        seq = "A+B+A-B-A+A-C+C-"
        data = cascade.generate(parse(seq))
        result = layout.apply(data)
        node_type_map = {n["id"]: n["type"] for n in result["nodes"]}

        anchors_by_source_anchor: dict[str, list[str]] = {}
        checked = 0
        for conn in result["connections"]:
            s, t = conn["source"], conn["target"]
            if (s["anchor"] not in ("PL", "A", "B")
                    or node_type_map.get(s["node"]) != "Valve_5_2_Ways"
                    or node_type_map.get(t["node"]) != "PressureLine"):
                continue
            anchors_by_source_anchor.setdefault(s["anchor"], []).append(t["anchor"])
            checked += 1

        assert checked > 0  # sanity check -- a sequência precisa exercitar isso
        for source_anchor, target_anchors in anchors_by_source_anchor.items():
            assert len(target_anchors) == len(set(target_anchors)), (
                f"anchors repetidos entre memórias diferentes pro anchor "
                f"de origem {source_anchor!r}: {target_anchors}"
            )

    def test_routing_is_manual_not_astar(self):
        # Feedback direto do usuário: não dá pra confiar no A* pra essas
        # conexões, mesmo com o stagger evitando anchors repetidos -- o
        # A* podia escolher um caminho atravessando outra memória/sig no
        # meio. Rota manual e determinística: stub reto na direção de
        # saída do anchor (get_exit_dir), depois um cotovelo alinhando
        # com a coluna do anchor de destino -- exatamente 2 waypoints,
        # com o segundo já no MESMO x do anchor de destino (o trecho
        # final até o anchor é reto, sem decisão de pathfinding).
        from circuit_generator.astar_router import get_exit_dir

        seq = "A+B+A-B-A+A-C+C-"
        data = cascade.generate(parse(seq))
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        node_type_map = {n["id"]: n["type"] for n in result["nodes"]}

        checked = 0
        for conn in result["connections"]:
            s, t = conn["source"], conn["target"]
            if (s["anchor"] not in ("PL", "A", "B")
                    or node_type_map.get(s["node"]) != "Valve_5_2_Ways"
                    or node_type_map.get(t["node"]) != "PressureLine"):
                continue
            wps = conn.get("waypoints")
            assert wps is not None and len(wps) == 2, (
                f"{s} -> {t}: esperava exatamente 2 waypoints (rota manual), achou {wps}"
            )
            src_pos = node_by_id[s["node"]]["position"]
            src_dir = get_exit_dir("Valve_5_2_Ways", s["anchor"])
            # o stub (1o waypoint) sai na direção correta a partir da origem;
            # o cotovelo (2o waypoint) fica na MESMA altura do stub -- o
            # trecho final até o anchor é sempre reto (mesmo x do anchor)
            assert wps[1]["y"] == wps[0]["y"]
            if src_dir == "UP":
                assert wps[0]["y"] < src_pos["y"]
            elif src_dir == "LEFT":
                assert wps[0]["x"] < src_pos["x"]
            checked += 1
        assert checked > 0  # sanity check -- a sequência precisa exercitar isso

    def test_mem_b_targets_left_of_the_sig_driving_the_memory_above(self):
        # Feedback direto do usuário (com desenho anexado): mem[i].B (i
        # != mem[-1], a mais alta) deve mirar bem à ESQUERDA do sprite da
        # 3/2 que aciona mem[i+1].PR diretamente -- não um stagger
        # genérico -- senão o traço atravessa essa válvula subindo.
        from circuit_generator.sprite_metrics import METRICS as _M

        seq = "A+B+A-B-A+A-C+C-"
        data = cascade.generate(parse(seq))
        roles = layout._build_role_maps(data)
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        node_type_map = {n["id"]: n["type"] for n in result["nodes"]}

        n_mc = roles["n_mc"]
        checked = 0
        for i in range(n_mc - 1):  # exclui a mais alta (mem[n_mc-1])
            mem_id = roles["mc_by_idx"][i]
            next_mem_id = roles["mc_by_idx"][i + 1]
            # acha a sig que alimenta next_mem_id.PR diretamente (chain[-1])
            driving_sig_id = next(
                c["source"]["node"] for c in result["connections"]
                if c["target"]["node"] == next_mem_id and c["target"]["anchor"] == "PR"
            )
            driving_x = node_by_id[driving_sig_id]["position"]["x"]

            conn = next(c for c in result["connections"]
                        if c["source"]["node"] == mem_id and c["source"]["anchor"] == "B")
            assert node_type_map.get(conn["target"]["node"]) == "PressureLine"
            wps = conn["waypoints"]
            entry_x = wps[-1]["x"]
            assert entry_x <= driving_x - _M.v32_width, (
                f"mem[{i}].B entra em x={entry_x}, não fica à esquerda "
                f"do corpo da sig que aciona mem[{i+1}] (x={driving_x})"
            )
            checked += 1
        assert checked > 0  # sanity check -- a sequência precisa exercitar isso


class TestChildPositioningAndRouting:
    def test_every_node_has_role_removed(self):
        data = cascade.generate(parse("A+B+A-B-A+A-"))
        result = layout.apply(data)
        assert all("_role" not in n for n in result["nodes"])

    def test_no_node_left_at_origin_by_accident(self):
        data = cascade.generate(parse("A+B+A-B-A+A-"))
        result = layout.apply(data)
        at_origin = [n["id"] for n in result["nodes"]
                     if n["position"]["x"] == 0 and n["position"]["y"] == 0]
        assert at_origin == []

    def test_no_two_nodes_share_the_same_position(self):
        data = cascade.generate(parse("(A+C+)B+A-B-C-B+B-"))
        result = layout.apply(data)
        positions = [(n["id"], n["position"]["x"], n["position"]["y"]) for n in result["nodes"]]
        coords = [(x, y) for _, x, y in positions]
        assert len(coords) == len(set(coords)), (
            f"duplicate positions: {[p for p in positions if coords.count((p[1], p[2])) > 1]}")

    def test_connections_get_waypoints(self):
        data = cascade.generate(parse("A+B+A-B-A+A-"))
        result = layout.apply(data)
        with_waypoints = [c for c in result["connections"] if "waypoints" in c]
        assert len(with_waypoints) > 0

    def test_all_pressure_lines_share_the_same_anchor_count(self):
        data = cascade.generate(parse("A+B+A-B-A+A-"))
        result = layout.apply(data)
        counts = {len(n["properties"]["anchors"]) for n in result["nodes"]
                  if n["type"] == "PressureLine"}
        assert len(counts) == 1, f"larguras diferentes entre linhas: {counts}"


class TestEndToEndDispatch:
    def test_layout_map_points_cascade_to_the_new_module(self):
        from circuit_generator import circuit_generator as cg
        assert cg.LAYOUT_MAP[("cascade", None)] is layout.apply

    def test_full_pipeline_runs_without_raising_for_a_realistic_sequence(self):
        # Sequência com múltiplos grupos, multi-ciclo e bloco paralelo --
        # a mesma classe de estresse já usada nos testes de passo a passo.
        data = cascade.generate(parse("(A+C+)B+A-B-C-B+B-"))
        result = layout.apply(data)
        assert len(result["nodes"]) == len(data["nodes"])
        at_origin = [n["id"] for n in result["nodes"]
                     if n["position"]["x"] == 0 and n["position"]["y"] == 0]
        assert at_origin == []
