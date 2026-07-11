"""
Posicionamento espacial do método passo a passo pneumático.

Recebe o dicionário de dados do circuito (com _role em cada nó, gerado
por circuit_generator.methods.step_by_step_pneumatic) e preenche as
posições x/y de cada componente usando circuit_generator.grid_layout.Grid.

Três regiões verticais (ver docs/superpowers/specs/
2026-07-11-step-by-step-positioning-design.md):
  1. Pistões/válvulas (cilindro + 4/2), uma coluna por letra.
  2. PressureLines (uma por átomo), empilhadas na ordem dos átomos --
     cada uma É uma linha do Grid (diferente do cascata).
  3. Lógica (memória + sig de confirmação/relay), uma coluna por átomo.
     A Válvula 1 (relay) fica sempre 1 linha abaixo e 1 coluna à
     esquerda da Válvula 2 (memória) que ela alimenta -- exceto o bloco
     do átomo 0 (botão + sig de fechamento), que fica na MESMA coluna
     que MC_0, empilhado verticalmente.

Os anchors das PressureLines (X1, X2, ...) já foram atribuídos pelo
gerador de topologia -- este módulo só converte esses anchors em pixels
(mesma fórmula genérica usada por layout_engine.py), sem resolver
conflito.
"""

import json
from pathlib import Path

from circuit_generator.grid_layout import Grid
from circuit_generator.sprite_metrics import METRICS as _M

_CONFIG_PATH = Path(__file__).parent / "step_by_step_layout_config.json"


def _build_role_maps(data: dict) -> dict:
    """Extrai os mapas letra/índice -> node_id a partir dos _role dos nós."""
    role_map = {n["id"]: n.get("_role", "") for n in data["nodes"]}

    cyl_by_letter: dict[str, str] = {}
    v42_by_letter: dict[str, str] = {}
    pl_by_idx: dict[int, str] = {}
    mc_by_idx: dict[int, str] = {}
    btn_id: str | None = None

    for nid, role in role_map.items():
        if role.startswith("cylinder:"):
            cyl_by_letter[role.split(":", 1)[1]] = nid
        elif role.startswith("main_valve:"):
            v42_by_letter[role.split(":", 1)[1]] = nid
        elif role.startswith("pressure_line_step:"):
            pl_by_idx[int(role.split(":", 1)[1])] = nid
        elif role.startswith("memory:"):
            mc_by_idx[int(role.split(":", 1)[1])] = nid
        elif role == "button":
            btn_id = nid

    return {
        "role_map":     role_map,
        "cyl_by_letter": cyl_by_letter,
        "v42_by_letter": v42_by_letter,
        "pl_by_idx":     pl_by_idx,
        "mc_by_idx":     mc_by_idx,
        "btn_id":        btn_id,
        "n_atoms":       len(mc_by_idx),
    }


def _build_confirmation_chains(data: dict, roles: dict) -> dict[str, list[str]]:
    """Deriva, a partir das conexões, a cadeia serial de sigs que
    confirma cada transição -- alvo (memory node_id, ou btn_id pro
    fechamento) -> lista ordenada de sig_ids (1 elemento se o átomo-fonte
    não é bloco paralelo, 2+ se é)."""
    role_map = roles["role_map"]

    sig_out: dict[str, tuple[str, str]] = {}       # sig_id -> (target_id, target_anchor)
    sig_p_from_pl: set[str] = set()                 # sig_ids cujo P vem de uma PressureLine
    sig_p_from_sig: dict[str, str] = {}              # sig_id -> sig_id anterior na cadeia
    node_type_map = {n["id"]: n["type"] for n in data["nodes"]}

    for conn in data["connections"]:
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]

        if role_map.get(s_id, "").startswith("signal_valve:") and s_anc == "A":
            sig_out[s_id] = (t_id, t_anc)

        if role_map.get(t_id, "").startswith("signal_valve:") and t_anc == "P":
            if node_type_map.get(s_id) == "PressureLine":
                sig_p_from_pl.add(t_id)
            elif role_map.get(s_id, "").startswith("signal_valve:"):
                sig_p_from_sig[t_id] = s_id

    chains: dict[str, list[str]] = {}
    for head_sig in sig_p_from_pl:
        chain = [head_sig]
        current = head_sig
        while current in sig_out:
            target_id, target_anchor = sig_out[current]
            if role_map.get(target_id, "").startswith("signal_valve:"):
                chain.append(target_id)
                current = target_id
            else:
                chains[target_id] = chain
                break

    return chains


def apply(data: dict) -> dict:
    cfg  = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    cols = cfg["columns"]
    rows = cfg["rows"]

    node_type_map = {n["id"]: n["type"] for n in data["nodes"]}
    roles = _build_role_maps(data)
    node_by_id = {n["id"]: n for n in data["nodes"]}

    grid = Grid()

    # ── Região de pistões/válvulas ────────────────────────────────────────
    cyl_cell_w = cols["group_gap"]
    grid.add_row("cylinder",   cyl_cell_w, _M.cyl_height, rows["cylinder"],
                 x_origin=cols["cylinder_first_x"])
    # NOTE: v42_align_offset_x from config is NOT applied here -- applying it
    # to this row's x_origin (as the brief's Step 4 draft literally showed)
    # makes cylinder and main_valve x positions diverge by that offset,
    # contradicting the brief's own Step 2 test
    # (test_cylinders_and_v42_positioned_same_column_per_letter, which
    # asserts cyl_a.x == v42_a.x). Left in the config for a later task that
    # may need it for a different purpose (e.g. connector/anchor alignment).
    grid.add_row("main_valve", cyl_cell_w, _M.v42_height, rows["main_valve"],
                 x_origin=cols["cylinder_first_x"])

    letters = sorted(roles["cyl_by_letter"])
    for letter in letters:
        cyl_id = roles["cyl_by_letter"][letter]
        v42_id = roles["v42_by_letter"][letter]
        x, y = grid.place("cylinder", letter, cyl_id)
        node_by_id[cyl_id]["position"] = {"x": x, "y": y}
        x, y = grid.place("main_valve", letter, v42_id)
        node_by_id[v42_id]["position"] = {"x": x, "y": y}

    # ── PressureLines: uma linha do Grid por átomo, empilhadas ──────────────
    pl_cell_w = 200  # única coluna por linha, valor não usado pra alinhamento
    for k in sorted(roles["pl_by_idx"]):
        pl_id = roles["pl_by_idx"][k]
        y = rows["pl_base"] + k * rows["pl_gap"]
        grid.add_row(f"pl_row_{k}", pl_cell_w, _M.pl_pix_h, y,
                     x_origin=cols["cylinder_first_x"])
        x, y2 = grid.place(f"pl_row_{k}", 0, pl_id)
        node_by_id[pl_id]["position"] = {"x": x, "y": y2}

    # ── Região de lógica: memória (Válvula 2) + relay (Válvula 1) ───────────
    n_atoms       = roles["n_atoms"]
    logic_cell_w  = cols["logic_cell_width"]
    memory_x0     = cols["cylinder_first_x"]
    memory_y      = rows["pl_base"] + n_atoms * rows["pl_gap"] + rows["logic_row_gap"]

    grid.add_row("memory", logic_cell_w, _M.v32_height, memory_y, x_origin=memory_x0)
    for k in sorted(roles["mc_by_idx"]):
        mc_id = roles["mc_by_idx"][k]
        x, y = grid.place("memory", k, mc_id)
        node_by_id[mc_id]["position"] = {"x": x, "y": y}

    chains = _build_confirmation_chains(data, roles)

    # NOTA (segunda inconsistência real encontrada no texto literal do
    # brief, independente da acima): as fórmulas literais do Step 3 dão
    # à linha "btn_row" (memory_y + 1*logic_row_gap, coluna 0 relativa a
    # memory_x0) EXATAMENTE a mesma célula que a cabeça da cadeia de
    # relay do átomo 1 ocupa na linha "relay" (memory_y + 1*logic_row_gap
    # também, e coluna mc1.x - logic_cell_w == mc0.x == memory_x0 por
    # aritmética pura -- MC_1 é sempre exatamente 1 célula à direita de
    # MC_0 na linha "memory", que é densa/sem buracos). Isso não é um
    # artefato de implementação: dado que
    #   test_relay_sig_one_column_left_of_its_memory exige
    #     sig.x == mc1.x - logic_cell_w  e  sig.y == mc1.y + logic_row_gap
    # e mc1.x - logic_cell_w == mc0.x sempre, essa posição SEMPRE colide
    # com "MESMA coluna que MC_0" -- e o btn_row do Step 3 usa a mesma
    # linha (memory_y + 1*logic_row_gap) que a linha "relay". Confirmado
    # rodando os testes com o Step 3 literal: gen-btn e a cabeça da
    # cadeia de relay do átomo 1 (ex: gen-sig-A-ext-0) caem no mesmo
    # (x, y) -- em AMBAS as sequências de teste, não só na paralela.
    #
    # test_mc0_button_closure_sig_share_same_column só exige mc0.x ==
    # btn.x == closure.x e mc0.y < btn.y < closure.y (SEM fixar o
    # espaçamento numérico exato) -- diferente de
    # test_relay_sig_one_column_left_of_its_memory, que fixa o
    # deslocamento exato do relay em relação a MC_1. Resolvendo a
    # contradição a favor da intenção de design documentada no docstring
    # do módulo (bloco do átomo 0 fica na MESMA COLUNA de MC_0, mas é um
    # bloco à parte, empilhado) sem violar a fórmula numérica exigida
    # para o relay: o bloco do átomo 0 (btn_row + closure_row) é
    # colocado ABAIXO de todas as linhas de relay/relay_stack (cuja
    # profundidade máxima é conhecida a partir de `chains`), preservando
    # coluna e ordem vertical, mas sem colidir com nenhuma célula de
    # relay.
    relay_max_depth = max(
        (len(chains[roles["mc_by_idx"][k]]) - 1
         for k in roles["mc_by_idx"] if k != 0),
        default=0,
    )
    btn_row_level = relay_max_depth + 2       # 1 abaixo da última linha de relay_stack
    closure_row_level = relay_max_depth + 3

    # Bloco do átomo 0 (botão): MESMA coluna que MC_0, empilhado.
    btn_id = roles["btn_id"]
    grid.add_row("btn_row", logic_cell_w, _M.v32_height,
                 memory_y + btn_row_level * rows["logic_row_gap"], x_origin=memory_x0)
    x, y = grid.place("btn_row", 0, btn_id)
    node_by_id[btn_id]["position"] = {"x": x, "y": y}

    closure_chain = chains[btn_id]
    grid.add_row("closure_row", logic_cell_w, _M.v32_height,
                 memory_y + closure_row_level * rows["logic_row_gap"], x_origin=memory_x0)
    x, y = grid.place("closure_row", 0, closure_chain[0])
    node_by_id[closure_chain[0]]["position"] = {"x": x, "y": y}

    # Cauda da cadeia de fechamento (quando o último átomo é um bloco
    # paralelo, closure_chain tem 2+ sigs em série): mesma coluna que
    # closure_row (== MC_0 == btn), empilhada 1 logic_row_gap por
    # profundidade abaixo de closure_row -- mesmo padrão de
    # relay_stack_N, mas ancorado em closure_row em vez de "relay".
    for depth, sig_id in enumerate(closure_chain[1:], start=1):
        stack_row_id = f"closure_stack_{depth}"
        grid.add_row(stack_row_id, logic_cell_w, _M.v32_height,
                     memory_y + closure_row_level * rows["logic_row_gap"]
                     + depth * rows["logic_row_gap"],
                     x_origin=memory_x0)
        x, y = grid.place(stack_row_id, 0, sig_id)
        node_by_id[sig_id]["position"] = {"x": x, "y": y}

    # Relay (Válvula 1) dos demais átomos: 1 coluna à esquerda da memória
    # que alimenta -- x_origin da linha relay = x_origin da memória menos
    # 1 cell_width, mesma ordem de átomo nas duas linhas.
    #
    # NOTA (desvio do texto literal do brief): Grid.place indexa colunas
    # pela ORDEM DE CHEGADA dentro de cada linha (ver grid_layout.py),
    # não pelo valor de column_key. A linha "memory" recebe k=0..n-1 sem
    # buracos, então col_idx(k) == k ali. Mas a linha "relay" pula k=0
    # (tratado à parte, bloco do botão), e as linhas "relay_stack_N" só
    # recebem os k's cuja cadeia tem profundidade > N (esparso). Usar
    # grid.place ingenuamente nessas linhas produz col_idx(k) != k, e
    # portanto x's que NÃO se alinham com a coluna k da memória --
    # contradizendo tanto o docstring do módulo ("relay fica sempre ...
    # 1 coluna à esquerda da memória que alimenta") quanto os testes do
    # próprio brief (test_relay_sig_one_column_left_of_its_memory,
    # test_parallel_chain_stacks_vertically_same_column). Confirmado
    # rodando os testes: os dois falhavam com exatamente esse desvio de
    # 1 cell_width. Corrigido reservando, em cada linha, colunas
    # "fantasma" (placeholder ids não usados em node_by_id) para todo
    # k' < k ainda não inserido, garantindo col_idx(k) == k em todas as
    # linhas de lógica -- sem alterar a semântica do Grid em si.
    relay_x0 = memory_x0 - logic_cell_w
    grid.add_row("relay", logic_cell_w, _M.v32_height,
                 memory_y + rows["logic_row_gap"], x_origin=relay_x0)

    _reserved_cols: dict[str, set[int]] = {}

    def _place_aligned(row_id: str, k: int, node_id: str) -> tuple[float, float]:
        """grid.place, mas garante col_idx == k reservando colunas
        anteriores ainda não usadas nesta linha com ids placeholder."""
        reserved = _reserved_cols.setdefault(row_id, set())
        for kk in range(k):
            if kk not in reserved:
                grid.place(row_id, kk, f"__reserved__{row_id}__{kk}__")
                reserved.add(kk)
        reserved.add(k)
        return grid.place(row_id, k, node_id)

    stack_rows_added: set[str] = set()
    for k in sorted(roles["mc_by_idx"]):
        if k == 0:
            continue  # átomo 0 já tratado acima (bloco do botão)
        mc_id = roles["mc_by_idx"][k]
        sig_chain = chains[mc_id]
        x, y = _place_aligned("relay", k, sig_chain[0])
        node_by_id[sig_chain[0]]["position"] = {"x": x, "y": y}
        for depth, sig_id in enumerate(sig_chain[1:], start=1):
            stack_row_id = f"relay_stack_{depth}"
            if stack_row_id not in stack_rows_added:
                grid.add_row(stack_row_id, logic_cell_w, _M.v32_height,
                             memory_y + rows["logic_row_gap"] + depth * rows["logic_row_gap"],
                             x_origin=relay_x0)
                stack_rows_added.add(stack_row_id)
            x, y = _place_aligned(stack_row_id, k, sig_id)
            node_by_id[sig_id]["position"] = {"x": x, "y": y}

    # ── Filhos (Exhaust / PressureSource) posicionados relativo ao pai ──────
    _CHILD_ANCHOR = {"Exhaust": "R", "PressureSource": "P"}
    child_parent: dict[str, tuple[str, str]] = {}
    for conn in data["connections"]:
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        for child, parent, p_anc in [(s_id, t_id, t_anc), (t_id, s_id, s_anc)]:
            if node_type_map.get(child) in _CHILD_ANCHOR:
                child_parent.setdefault(child, (parent, p_anc))

    gap = cols.get("anchor_child_gap", 32)
    for child_id, (parent_id, parent_anchor) in child_parent.items():
        parent_pos   = node_by_id[parent_id]["position"]
        parent_local = _M.anchor_local.get(node_type_map[parent_id], {}).get(parent_anchor)
        if parent_local is None:
            node_by_id[child_id]["position"] = {"x": parent_pos["x"], "y": parent_pos["y"] + 100}
            continue
        anc_x = parent_pos["x"] + parent_local[0]
        anc_y = parent_pos["y"] + parent_local[1]
        child_type  = node_type_map[child_id]
        child_local = _M.anchor_local.get(child_type, {}).get(_CHILD_ANCHOR[child_type])
        cx = anc_x - (child_local[0] if child_local else 0.0)
        cy = anc_y + gap
        node_by_id[child_id]["position"] = {"x": cx, "y": cy}

    # ── Limpeza final: remove _role de todos os nós ──────────────────────────
    for node in data["nodes"]:
        node.pop("_role", None)

    return data
