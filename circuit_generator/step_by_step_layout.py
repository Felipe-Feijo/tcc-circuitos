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

Os anchors das PressureLines (X1, X2, ...) chegam do gerador de topologia
com índices sequenciais arbitrários (sem noção de posição de tela) --
este módulo os REATRIBUI por proximidade real (posição X do componente
do outro lado de cada conexão), com resolução de conflito quando duas
conexões disputam o mesmo anchor (mesma ideia da "Fase 3" de
layout_engine.py, cascata).
"""

import json
import math
from pathlib import Path

from circuit_generator.grid_layout import Grid
from circuit_generator.sprite_metrics import METRICS as _M, anchor_local_for_routing

_CONFIG_PATH = Path(__file__).parent / "step_by_step_layout_config.json"

# Precisa bater com o _OFFSET de astar_router.route_connection (offset de
# entrada aplicado na direção do anchor de destino) -- um anchor de PL
# escolhido a menos dessa distância do X do pilot PR produz um caminho
# apertado/ruim (jog quase nulo seguido de reentrada no próprio offset).
_PL_ANCHOR_MIN_MARGIN = 20

# Quantos anchors de sobra a poda global mantém além do range efetivamente
# usado (used_min/used_max) em cada ponta da PressureLine -- dá ao roteador
# espaço de manobra além da última conexão real, e no lado esquerdo
# frequentemente não chega a remover nada (mantém a reserva inteira gerada
# por step_by_step_pneumatic.py), o que é o objetivo.
_PL_PRUNE_MARGIN = 8


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

    # _place_aligned/_reserved_cols definidos aqui em cima (não só perto da
    # região de lógica, onde nasceram) porque agora a região de
    # pistões/válvulas também precisa de índice de coluna VIRTUAL --
    # ver nota abaixo.
    _reserved_cols: dict[str, set[int]] = {}

    def _place_aligned(row_id: str, virtual_col: int, node_id: str) -> tuple[float, float]:
        """grid.place, mas garante col_idx == virtual_col reservando
        colunas anteriores ainda não usadas nesta linha com ids
        placeholder -- Grid.place indexa por ordem de chegada, não pelo
        valor de column_key (ver grid_layout.py)."""
        reserved = _reserved_cols.setdefault(row_id, set())
        for kk in range(virtual_col):
            if kk not in reserved:
                grid.place(row_id, kk, f"__reserved__{row_id}__{kk}__")
                reserved.add(kk)
        reserved.add(virtual_col)
        return grid.place(row_id, virtual_col, node_id)

    # ── Região de pistões/válvulas ────────────────────────────────────────
    #
    #   Cada letra ocupa coluna VIRTUAL 2*idx (mesmo esquema de índice
    #   dobrado da região de lógica, mais abaixo) -- deixa a coluna ÍMPAR
    #   entre cilindros consecutivos vazia, de propósito: espaço
    #   reservado para o bloco de uma OrValve associada a cada cilindro
    #   (a implementar depois; ver pedido do usuário). cyl_cell_w
    #   continua sendo a largura de UM slot -- a distância real entre
    #   cilindros vizinhos passa a ser 2*cyl_cell_w.
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

    # Reserva de colunas por letra/lado: max(1, nº de OrValve daquele
    # lado) -- cada OrValve na cadeia de um pilot ocupa 1 coluna dedicada
    # (crescendo só em X, uma linha só -- ver "Posicionamento das
    # OrValve", mais abaixo). O _role de cada OrValve
    # (f"or_valve:{letra}:{PL|PR}:{i}") já entrega letra e lado
    # diretamente -- não precisa reabrir a sequência original de eventos.
    or_chain_len: dict[tuple[str, str], int] = {}
    for n in data["nodes"]:
        if n["type"] != "OrValve":
            continue
        _, or_letter, or_side, _or_i = n["_role"].split(":")
        key = (or_letter, or_side)
        or_chain_len[key] = or_chain_len.get(key, 0) + 1

    def _pilot_reserve(letter: str, side: str) -> int:
        # NOTA: nome deliberadamente diferente do "_reserved_cols" dict já
        # usado por _place_aligned (definido no topo de apply()) -- reusar
        # o mesmo nome aqui sombrearia aquele dict dentro deste escopo e
        # quebraria _place_aligned silenciosamente.
        return max(1, or_chain_len.get((letter, side), 0))

    letters = sorted(roles["cyl_by_letter"])
    cyl_col: dict[str, int] = {}
    col = 0
    for letter in letters:
        col += _pilot_reserve(letter, "PL")
        cyl_col[letter] = col
        col += 1 + _pilot_reserve(letter, "PR")

    for letter in letters:
        cyl_id = roles["cyl_by_letter"][letter]
        v42_id = roles["v42_by_letter"][letter]
        x, y = _place_aligned("cylinder", cyl_col[letter], cyl_id)
        node_by_id[cyl_id]["position"] = {"x": x, "y": y}
        x, y = _place_aligned("main_valve", cyl_col[letter], v42_id)
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

    # Índice de coluna VIRTUAL dobrado (2k pra memória, 2k-1 pro relay que
    # a alimenta) -- cada átomo ocupa 2 colunas dedicadas ("M + 2k", ver
    # spec), nunca reaproveitando a coluna da memória do átomo anterior.
    # _place_aligned (definido acima, junto com _reserved_cols) evita que
    # a linha "memory" (esparsa em termos de índice virtual -- só usa os
    # pares 0,2,4,...) sofra do problema de ordem-de-chegada do Grid --
    # achado ao investigar um relato do usuário: o relay do átomo k
    # estava caindo exatamente na MESMA coluna da memória do átomo k-1
    # (confirmado rodando o código: sig.x == mc_anterior.x), porque antes
    # desta correção a linha "memory" avançava 1 cell_width por átomo
    # (não 2), fazendo o relay (memory.x - 1 cell_width) coincidir com a
    # memória anterior.
    grid.add_row("memory", logic_cell_w, _M.v32_height, memory_y, x_origin=memory_x0)
    for k in sorted(roles["mc_by_idx"]):
        mc_id = roles["mc_by_idx"][k]
        x, y = _place_aligned("memory", 2 * k, mc_id)
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
    # Reversão de design (a pedido do usuário): o bloco do átomo 0 (botão
    # + sig de fechamento) seguia antes uma regra própria -- MESMA coluna
    # que MC_0, empilhado (ver histórico em
    # docs/superpowers/specs/2026-07-11-step-by-step-positioning-design.md,
    # seção "Bloco do átomo 0"). Agora o botão segue a MESMA regra
    # diagonal geral de qualquer par Válvula1/Válvula2 (1 coluna à
    # esquerda, 1 linha abaixo de quem alimenta): faz o papel de
    # "Válvula 1" de MC_0. A cadeia de fechamento (closure_chain), por
    # sua vez, está EM SÉRIE com o botão (não é outro par diagonal) --
    # fica na MESMA coluna do botão, 1 linha abaixo, exatamente como
    # relay_stack_N fica na mesma coluna do relay que ele estende.
    #
    # Grid.place indexa colunas por ORDEM DE CHEGADA dentro da linha, não
    # pelo valor de column_key (ver grid_layout.py) -- col_idx nunca é
    # negativo (começa em 0 e só cresce). _place_aligned contorna isso
    # reservando placeholders 0..virtual_col-1 ANTES de colocar em
    # virtual_col, mas só funciona pra virtual_col >= 0. Como o botão
    # precisa de uma coluna efetivamente NEGATIVA (à esquerda de MC_0,
    # que já está na coluna 0), usamos linhas dedicadas com x_origin
    # explicitamente deslocado pra esquerda, em vez de
    # _place_aligned/coluna virtual.
    btn_id = roles["btn_id"]
    btn_x0 = memory_x0 - logic_cell_w
    grid.add_row("btn_row", logic_cell_w, _M.v32_height,
                 memory_y + rows["logic_row_gap"], x_origin=btn_x0)
    x, y = grid.place("btn_row", 0, btn_id)
    node_by_id[btn_id]["position"] = {"x": x, "y": y}

    # A cadeia de fechamento é percorrida de trás pra frente ao posicionar
    # (closure_chain[-1], cujo A alimenta btn.P, fica no topo -- mais
    # perto do botão; closure_chain[0], que recebe P direto da PL do
    # último átomo, fica no fundo) -- confirmado pelo usuário: o fio
    # desce da PL até a válvula MAIS embaixo, e a cadeia de confirmação
    # sobe (A -> P) até a última, que alimenta a Válvula 2 (aqui, o
    # botão) por cima. Mesmo princípio pro relay dos demais átomos, logo
    # abaixo.
    closure_chain_top_down = list(reversed(chains[btn_id]))
    grid.add_row("closure_row", logic_cell_w, _M.v32_height,
                 memory_y + 2 * rows["logic_row_gap"], x_origin=btn_x0)
    x, y = grid.place("closure_row", 0, closure_chain_top_down[0])
    node_by_id[closure_chain_top_down[0]]["position"] = {"x": x, "y": y}

    # Cauda da cadeia de fechamento (quando o último átomo é um bloco
    # paralelo, a cadeia tem 2+ sigs em série): mesma coluna que
    # closure_row (== botão), empilhada 1 logic_row_gap por profundidade
    # abaixo dela -- mesmo padrão de relay_stack_N, mas ancorado em
    # closure_row.
    for depth, sig_id in enumerate(closure_chain_top_down[1:], start=1):
        stack_row_id = f"closure_stack_{depth}"
        grid.add_row(stack_row_id, logic_cell_w, _M.v32_height,
                     memory_y + 2 * rows["logic_row_gap"] + depth * rows["logic_row_gap"],
                     x_origin=btn_x0)
        x, y = grid.place(stack_row_id, 0, sig_id)
        node_by_id[sig_id]["position"] = {"x": x, "y": y}

    # Relay (Válvula 1) dos demais átomos: coluna DEDICADA (índice virtual
    # 2k-1), 1 cell_width à esquerda da memória que alimenta (virtual 2k)
    # e 1 cell_width à direita da memória do átomo anterior (virtual
    # 2(k-1) = 2k-2) -- nunca reaproveita a coluna de outro bloco. Mesma
    # x_origin da linha "memory" (não mais deslocada por -1 cell_width),
    # já que agora o índice virtual por si só garante a posição relativa
    # correta em ambas as direções.
    grid.add_row("relay", logic_cell_w, _M.v32_height,
                 memory_y + rows["logic_row_gap"], x_origin=memory_x0)

    stack_rows_added: set[str] = set()
    for k in sorted(roles["mc_by_idx"]):
        if k == 0:
            continue  # átomo 0 já tratado acima (bloco do botão)
        mc_id = roles["mc_by_idx"][k]
        # Percorrida de trás pra frente ao posicionar -- ver nota acima,
        # no bloco do botão/fechamento: quem alimenta mc_id.PL (último da
        # cadeia) fica no topo (linha "relay"), quem recebe P direto da
        # PL (primeiro da cadeia) fica no fundo.
        sig_chain = list(reversed(chains[mc_id]))
        x, y = _place_aligned("relay", 2 * k - 1, sig_chain[0])
        node_by_id[sig_chain[0]]["position"] = {"x": x, "y": y}
        for depth, sig_id in enumerate(sig_chain[1:], start=1):
            stack_row_id = f"relay_stack_{depth}"
            if stack_row_id not in stack_rows_added:
                grid.add_row(stack_row_id, logic_cell_w, _M.v32_height,
                             memory_y + rows["logic_row_gap"] + depth * rows["logic_row_gap"],
                             x_origin=memory_x0)
                stack_rows_added.add(stack_row_id)
            x, y = _place_aligned(stack_row_id, 2 * k - 1, sig_id)
            node_by_id[sig_id]["position"] = {"x": x, "y": y}

    node_pos = {nid: (n["position"]["x"], n["position"]["y"]) for nid, n in node_by_id.items()}
    pl_node_map = {pid: node_by_id[pid] for pid in roles["pl_by_idx"].values()}

    # ── Dimensiona as PressureLines pelo alcance real do grid ───────────────
    #
    #   step_by_step_pneumatic.py não tem nenhuma posição de tela real pra
    #   decidir quantos anchors uma PressureLine precisa -- só quem sabe é
    #   esta etapa, via Grid (que já posicionou toda região de pistões/
    #   válvulas/lógica acima). Cresce (nunca encolhe) o array de anchors
    #   de cada PL pra cobrir, EM AMBAS as direções, todo o alcance físico
    #   do circuito inteiro -- feito uma única vez aqui, ANTES de qualquer
    #   conexão ser resolvida, então nenhuma conexão de PL -> Valve_3_2_Ways.P
    #   (ver astar_router "PressureLine -> Valve_3_2_Ways.P", que desce reto
    #   a partir do anchor) precisa crescer o array reativamente por conta
    #   própria -- ela só ESCOLHE, entre os anchors que já existem, o mais
    #   próximo à esquerda do corpo da válvula + atuador de fim-de-curso
    #   (limit_switch, mesma largura do pilot: METRICS.pilot_w). A poda
    #   global (mais abaixo, já existente) corta de volta pro range
    #   realmente usado + margem, então superestimar aqui não deixa a
    #   PressureLine final maior que o necessário.
    #
    #   Reservar a partir do min_x/max_x GLOBAIS do grid (não de um nó
    #   específico) garante margem tanto pro componente mais à direita
    #   quanto pro mais à esquerda de TODO o circuito -- não só do alvo da
    #   conexão em questão, que era o problema de uma versão anterior desta
    #   correção (só enxergava a válvula da própria conexão, não outras na
    #   mesma coluna, ex: MC_0/botão na coluna de fechamento).
    pl_row_ids = {f"pl_row_{k}" for k in roles["pl_by_idx"]}
    x_range = grid.occupied_x_range(exclude_rows=pl_row_ids)
    if x_range is not None:
        min_x, max_x = x_range
        reach_margin = cols["logic_cell_width"]
        left_margin = _M.pilot_w
        for pl_id, pl_node in pl_node_map.items():
            existing_idxs = [int(a[1:]) for a in pl_node["properties"]["anchors"]]
            needed_max = max(1, math.ceil(
                (max_x + reach_margin - pl_node["position"]["x"] - _M.pl_pix_w / 2) / _M.pl_spacing
            ) + 1)
            needed_min = math.floor(
                (min_x - left_margin - pl_node["position"]["x"] - _M.pl_pix_w / 2) / _M.pl_spacing
            ) + 1
            lo = min(needed_min, min(existing_idxs) if existing_idxs else 1)
            hi = max(needed_max, max(existing_idxs) if existing_idxs else 1)
            pl_node["properties"]["anchors"] = [f"X{i}" for i in range(lo, hi + 1)]
            # PressureLine.layout_anchors() (graphics/items/base/nodes/
            # expandable/pressure_line.py) posiciona cada anchor pelo seu
            # ÍNDICE NA LISTA (enumerate), não pelo número no nome "Xi" --
            # as duas coisas só coincidem se o array começar em X1. Ao
            # reservar anchors à esquerda (lo < 1), a posição precisa
            # deslocar pra compensar, senão TODOS os anchors nomeados
            # (inclusive os já escolhidos por conexões antigas) renderizam
            # deslocados pra DIREITA na cena real -- mesma lógica já usada
            # na poda global (mais abaixo), que compensa o lado oposto
            # (encolher em vez de crescer) da mesma forma.
            if lo < 1:
                pl_node["position"]["x"] += (lo - 1) * _M.pl_spacing
                node_pos[pl_id] = (pl_node["position"]["x"], pl_node["position"]["y"])

    # ── Reatribuição dos anchors das PressureLines por proximidade ──────────
    #
    #   O gerador de topologia atribui X1, X2, ... sequencialmente, sem
    #   nenhuma noção de posição de tela -- isso produz fios que
    #   atravessam o desenho sem necessidade (o componente mais à direita
    #   pode ficar preso a um anchor bem à esquerda). Reatribui cada
    #   anchor pro mais próximo da posição X real do componente do outro
    #   lado da conexão -- mesma ideia da "Fase 3" de layout_engine.py
    #   (cascata), com _pl_anchor_x/_nearest_pl_anchor/_resolve_conflict
    #   copiados de lá (genéricos, sem nada específico de Valve_5_2_Ways)
    #   e adaptados pro conjunto de conexões do passo a passo (só 4
    #   formas, bem menos que o cascata -- não precisa da lógica de
    #   "coluna livre" que o cascata usa pro caso sig.P, porque a região
    #   de lógica do passo a passo está sempre abaixo de qualquer PL, sem
    #   a ambiguidade acima/abaixo que motiva aquela função lá).
    def _pl_anchor_x(pl_node: dict, anchor_name: str) -> float:
        # PressureLine.layout_anchors() (graphics/items/base/nodes/
        # expandable/pressure_line.py) posiciona cada anchor pelo seu
        # ÍNDICE NA LISTA (enumerate(self.anchor_list)), não pelo número
        # no nome "Xi" -- as duas coisas só coincidem se o array for
        # contíguo E começar em X1. A compensação de position.x feita em
        # "Dimensiona as PressureLines..." (mais acima) e na poda global
        # (mais abaixo) mantêm X1 sempre no MESMO x físico de antes de
        # qualquer reserva de anchors à esquerda -- mas só funciona se
        # aqui usarmos o menor índice ATUAL do array como origem (em vez
        # da constante 1), reproduzindo o mesmo deslocamento que
        # layout_anchors() aplica de verdade.
        pl_x = node_pos[pl_node["id"]][0]
        list_origin = min(int(a[1:]) for a in pl_node["properties"]["anchors"])
        return pl_x + _M.pl_pix_w / 2 + (int(anchor_name[1:]) - list_origin) * _M.pl_spacing

    def _nearest_pl_anchor(pl_node: dict, target_x: float, side: str = "any",
                            min_margin: float = 0.0) -> str:
        anchors = pl_node["properties"]["anchors"]
        scored = [(int(n[1:]), _pl_anchor_x(pl_node, n), n) for n in anchors]
        if side == "left":
            candidates = [(abs(ax - target_x), n) for _, ax, n in scored if ax < target_x - min_margin]
            fallback = sorted(scored)[0][2]
        elif side == "right":
            candidates = [(abs(ax - target_x), n) for _, ax, n in scored if ax > target_x + min_margin]
            fallback = sorted(scored, reverse=True)[0][2]
        else:
            candidates = [(abs(ax - target_x), n) for _, ax, n in scored]
            fallback = anchors[0]
        return min(candidates)[1] if candidates else fallback

    # Chaveado por (id da PressureLine, x arredondado) / (id da PressureLine,
    # owner) -- não só pela posição X ou pelo owner isolados. Todas as
    # PressureLines do passo a passo compartilham o mesmo x_origin (mesma
    # coluna X0), então o mesmo índice de anchor (ex: X8) cai na MESMA
    # posição de tela em qualquer linha -- sem o namespace por PL, uma
    # colisão espúria entre conexões de linhas DIFERENTES (que não competem
    # pelo mesmo anchor de verdade) podia empurrar uma conexão pra cima de
    # outra que já estava legitimamente registrada na SUA própria linha,
    # avaliando o heurístico "lados opostos" com o pl_y da linha ERRADA.
    pl_anchor_used: dict[tuple[str, int], tuple[str, float, float]] = {}
    conn_by_owner: dict[tuple[str, str], tuple] = {}

    def _resolve_conflict(pl_node: dict, anchor: str, owner: str,
                           owner_y: float, conn_ref: dict, side: str,
                           push_dir: int = 0) -> str:
        # push_dir: direção forçada pra reempurrar em caso de colisão
        # (+1 = sempre mais pra direita, -1 = sempre mais pra esquerda,
        # 0 = heurística antiga baseada no meio da linha). Necessário pros
        # casos com viés de lado (PL/PR): sem isso, uma colisão empurrava
        # o anchor de volta em direção ao meio da PressureLine, podendo
        # cruzar de volta pra baixo da margem mínima (ou pro lado errado
        # do alvo) -- o "push" precisa continuar na mesma direção que
        # motivou a escolha do lado em primeiro lugar.
        anchors = pl_node["properties"]["anchors"]
        n, mid = len(anchors), len(anchors) / 2

        def _next(anc: str, direction: int) -> str:
            idx = int(anc[1:])
            step = direction if direction else ((-1) if idx <= mid else 1)
            return f"X{max(1, min(n, idx + step))}"

        pl_y = node_pos.get(pl_node["id"], (0, 0))[1]

        def _reg(anc: str, oid: str, oy: float, cref: dict, seen: set, pdir: int) -> str:
            if anc in seen:
                return anc  # sem slot livre nessa direção -- desiste, mantém
            seen = seen | {anc}
            ax = _pl_anchor_x(pl_node, anc)
            key = (pl_node["id"], round(ax))
            owner_key = (pl_node["id"], oid)
            if key not in pl_anchor_used:
                pl_anchor_used[key] = (oid, oy, pl_y)
                conn_by_owner[owner_key] = (cref, side, pl_node, pdir)
                return anc
            prev_id, prev_y, prev_pl_y = pl_anchor_used[key]
            if prev_id == oid:
                return anc
            curr_above = oy < pl_y
            prev_above = prev_y < prev_pl_y
            opp_sides = curr_above != prev_above
            if pl_y != prev_pl_y:
                same_order = (oy < prev_y) == (pl_y < prev_pl_y)
            else:
                same_order = True
            if opp_sides and same_order:
                return anc
            if oy >= prev_y:
                return _reg(_next(anc, pdir), oid, oy, cref, seen, pdir)
            else:
                pl_anchor_used[key] = (oid, oy, pl_y)
                conn_by_owner[owner_key] = (cref, side, pl_node, pdir)
                prev_owner_key = (pl_node["id"], prev_id)
                prev_conn, prev_side, prev_pl, prev_pdir = conn_by_owner.get(
                    prev_owner_key, (None, None, None, 0))
                if prev_conn is not None:
                    new_anc = _reg(_next(anc, prev_pdir), prev_id, prev_y, prev_conn, set(), prev_pdir)
                    prev_conn[prev_side]["anchor"] = new_anc
                return anc

        return _reg(anchor, owner, owner_y, conn_ref, set(), push_dir)

    def _target_x(node_id: str, anchor_name: str) -> float:
        ntype = node_type_map.get(node_id, "")
        pos = node_by_id[node_id]["position"]
        local = anchor_local_for_routing(ntype, anchor_name)
        return pos["x"] + local[0] if local else pos["x"]

    def _conn_sort_key(c: dict) -> tuple:
        t_id = c["target"]["node"]
        return (0, 0) if t_id in pl_node_map else (1, 0)

    connections_sorted = sorted(
        [c for c in data["connections"] if c["source"]["node"] != c["target"]["node"]],
        key=_conn_sort_key,
    )

    for conn in connections_sorted:
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]

        if s_id in pl_node_map and s_anc.startswith("X"):
            pl = pl_node_map[s_id]
            tgt_x = _target_x(t_id, t_anc)
            if t_anc == "PL":
                anc = _nearest_pl_anchor(pl, tgt_x, "left")
                push_dir = -1
            elif t_anc == "PR":
                anc = _nearest_pl_anchor(pl, tgt_x, "right", min_margin=_PL_ANCHOR_MIN_MARGIN)
                push_dir = 1
            elif t_anc == "P" and node_type_map.get(t_id) == "Valve_3_2_Ways":
                # O fio desce reto a partir deste anchor até a válvula (ver
                # astar_router "PressureLine -> Valve_3_2_Ways.P") -- precisa
                # ficar à esquerda do CORPO da válvula e do atuador de
                # fim-de-curso (limit_switch, mesma largura do pilot:
                # METRICS.pilot_w), senão o traço desce por DENTRO dela (ou
                # de outra válvula na mesma coluna, ex: MC_0/botão na coluna
                # de fechamento). Os anchors necessários já foram criados
                # (ver "Estende as PressureLines pra esquerda...", acima).
                valve_left_x = node_by_id[t_id]["position"]["x"]
                safe_x = valve_left_x - _M.pilot_w
                anc = _nearest_pl_anchor(pl, safe_x, "left")
                push_dir = -1
            else:
                anc = _nearest_pl_anchor(pl, tgt_x)
                push_dir = 0
            conn["source"]["anchor"] = _resolve_conflict(
                pl, anc, t_id, node_pos.get(t_id, (0, 0))[1], conn, "source", push_dir)

        elif t_id in pl_node_map and t_anc.startswith("X"):
            pl = pl_node_map[t_id]
            src_x = _target_x(s_id, s_anc)
            anc = _nearest_pl_anchor(pl, src_x)
            conn["target"]["anchor"] = _resolve_conflict(
                pl, anc, s_id, node_pos.get(s_id, (0, 0))[1], conn, "target")

    # ── Poda global das PressureLines ────────────────────────────────────
    #
    #   Todas as PLs do circuito ficam com a MESMA largura (cobrindo da
    #   primeira até a última coluna do circuito inteiro, com margem de
    #   _PL_PRUNE_MARGIN anchors de cada lado) -- mesmo espírito da poda
    #   do cascata (Fase 3.9 de layout_engine.py), que também usa um
    #   range GLOBAL compartilhado entre todas as PLs, não um range
    #   por-linha (poda por-linha, tentada num sub-projeto anterior,
    #   produzia larguras diferentes entre linhas -- parecia pedaços
    #   soltos em vez de um barramento contínuo). Diferença do cascata:
    #   margem maior que 1 de cada lado (confirmado com o usuário).
    #
    #   Largura final IGUAL entre todas as PLs não vem mais de um orçamento
    #   de anchors dado na geração (step_by_step_pneumatic.py hoje só bota
    #   um anchor por conexão real que toca a linha -- PLs diferentes podem
    #   sair da topologia com contagens diferentes) -- quem garante a
    #   igualdade agora é o passo "Dimensiona as PressureLines pelo alcance
    #   real do grid" (mais acima nesta função), que cresce o array de
    #   anchors de TODA PL até o mesmo `needed`, calculado a partir do mesmo
    #   x_origin (cols["cylinder_first_x"]) e do mesmo max_x global
    #   (Grid.occupied_x_range()) pra todas elas. Isso pressupõe que nenhuma
    #   PL chegue da topologia já com mais anchors reais do que esse
    #   `needed` compartilhado -- não acontece nos circuitos que este
    #   gerador produz, e test_all_pressure_lines_share_the_same_anchor_count
    #   (tests/test_step_by_step_layout.py) guarda o invariante.
    used_min, used_max = float("inf"), float("-inf")
    for conn in data["connections"]:
        for side in (conn["source"], conn["target"]):
            if side["node"] in pl_node_map and side["anchor"].startswith("X"):
                idx = int(side["anchor"][1:])
                used_min = min(used_min, idx)
                used_max = max(used_max, idx)

    if used_min != float("inf"):
        for pl_id, pl_node in pl_node_map.items():
            all_idxs = [int(a[1:]) for a in pl_node["properties"]["anchors"]]
            keep_min = max(min(all_idxs), used_min - _PL_PRUNE_MARGIN)
            keep_max = min(max(all_idxs), used_max + _PL_PRUNE_MARGIN)
            pl_node["properties"]["anchors"] = [f"X{i}" for i in all_idxs if keep_min <= i <= keep_max]
            removed_left = keep_min - min(all_idxs)
            pl_node["position"]["x"] += removed_left * _M.pl_spacing
            node_pos[pl_id] = (pl_node["position"]["x"], pl_node["position"]["y"])

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

    # ── Roteamento A* ─────────────────────────────────────────────────────
    from circuit_generator.astar_router import build_grid, route_connection, get_exit_dir

    def _scene_xy(node_id: str, anchor_name: str) -> tuple[float, float] | None:
        pos = node_by_id[node_id]["position"]
        ntype = node_type_map.get(node_id, "")
        if ntype == "PressureLine" and anchor_name.startswith("X"):
            idx = int(anchor_name[1:])
            # PressureLine.layout_anchors() (graphics/items/base/nodes/
            # expandable/pressure_line.py) posiciona cada anchor em
            # y0=self.pix_h -- pl_pix_h abaixo da posição do nó, não na
            # própria posição. Sem essa soma, o roteamento acha que o
            # anchor está pl_pix_h mais acima do que é renderizado de
            # verdade, e a conexão cruza de volta por cima dele.
            #
            # O X tem a mesma ressalva de _pl_anchor_x (mais acima):
            # layout_anchors() posiciona pelo ÍNDICE NA LISTA, não pelo
            # número do nome -- usa o menor índice ATUAL do array como
            # origem, não a constante 1, senão o waypoint computado aqui
            # não bate com onde o anchor realmente é desenhado sempre que
            # a PL reservou anchors à esquerda.
            list_origin = min(int(a[1:]) for a in node_by_id[node_id]["properties"]["anchors"])
            return (pos["x"] + _M.pl_pix_w / 2 + (idx - list_origin) * _M.pl_spacing, pos["y"] + _M.pl_pix_h)
        local = anchor_local_for_routing(ntype, anchor_name)
        return (pos["x"] + local[0], pos["y"] + local[1]) if local else (pos["x"], pos["y"])

    astar_grid = build_grid(data["nodes"])
    for conn in data.get("connections", []):
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        spos = _scene_xy(s_id, s_anc)
        tpos = _scene_xy(t_id, t_anc)
        if spos is None or tpos is None:
            continue
        s_type, t_type = node_type_map.get(s_id, ""), node_type_map.get(t_id, "")
        wps = route_connection(astar_grid, spos, get_exit_dir(s_type, s_anc),
                                tpos, get_exit_dir(t_type, t_anc),
                                src_type=s_type, tgt_type=t_type,
                                src_id=s_id, tgt_id=t_id)
        if wps is not None:
            conn["waypoints"] = wps

    return data
