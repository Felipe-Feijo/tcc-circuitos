"""
Posicionamento espacial do método cascata (pneumático).

Recebe o dicionário de dados do circuito (com _role em cada nó, gerado por
circuit_generator.methods.cascade) e preenche as posições x/y de cada
componente usando circuit_generator.grid_layout.Grid -- ver design em
docs/superpowers/specs/2026-07-16-cascade-grid-layout-design.md.

Duas regiões:
  A. Pistão/válvula (topo), uma coluna por letra de cilindro -- cilindro e
     4/2 alinhados na mesma coluna, flanqueados por uma escada de OR/sig
     por lado (ver Task 3).
  B. Lógica (embaixo): uma linha de Grid por linha de pressão/memória,
     coluna de botão+fechamento à esquerda, coluna de memórias, escada de
     sigs de confirmação PR à direita (ver Tasks 4/5).
"""

import json
import math
from pathlib import Path

from circuit_generator.grid_layout import Grid
from circuit_generator.sprite_metrics import METRICS as _M, anchor_local_for_routing

_CONFIG_PATH = Path(__file__).parent / "cascade_layout_config.json"

# Precisa bater com o _OFFSET de astar_router.route_connection (offset de
# entrada aplicado na direção do anchor de destino) -- um anchor de PL
# escolhido a menos dessa distância do X do pilot PR produz um caminho
# apertado/ruim (jog quase nulo seguido de reentrada no próprio offset).
# Copiado de step_by_step_layout.py (mesma constante, mesmo motivo).
_PL_ANCHOR_MIN_MARGIN = 20

# Quantos anchors de sobra a poda global mantém além do range efetivamente
# usado (used_min/used_max) em cada ponta da PressureLine -- ver
# step_by_step_layout.py, mesma constante/motivo.
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
        elif role.startswith("pressure_line_group:"):
            pl_by_idx[int(role.split(":", 1)[1])] = nid
        elif role.startswith("memory:"):
            mc_by_idx[int(role.split(":", 1)[1])] = nid
        elif role == "button":
            btn_id = nid

    return {
        "role_map":      role_map,
        "cyl_by_letter": cyl_by_letter,
        "v42_by_letter": v42_by_letter,
        "pl_by_idx":     pl_by_idx,
        "mc_by_idx":     mc_by_idx,
        "btn_id":        btn_id,
        "n_groups":      len(pl_by_idx),
        "n_mc":          len(mc_by_idx),
    }


def _build_trigger_sources(data: dict, roles: dict) -> dict[tuple[str, str], list[list[str]]]:
    """Reconstrói, a partir das conexões, as fontes de disparo de cada
    pilot (letra, lado) -- mesma ideia de sig_to_v42/sig_to_or já usada em
    layout_engine.py (linhas 176-201), generalizada pra devolver a cadeia
    de sigs completa de cada fonte (não só o id do sig mais próximo do
    pilot), na ordem em que cascade.py as encadeia (mais distante do
    cilindro primeiro -- mesma ordem de `sources` em cascade.py seção 6b).

    Key: (letra, lado) onde lado é "PL" ou "PR". Value: lista ordenada de
    leaves (mais distante do cilindro primeiro); cada leaf é uma lista de
    ids de Valve_3_2_Ways da raiz (P alimentado por uma PressureLine) até
    o mais próximo do pilot -- [] significa fonte crua (PressureLine
    direto no pilot ou na OrValve, sem nenhum sig no meio).
    """
    role_map = roles["role_map"]
    node_type_map = {n["id"]: n["type"] for n in data["nodes"]}

    # sig.A -> (tipo do alvo, id do alvo, anchor do alvo)
    sig_out: dict[str, tuple[str, str, str]] = {}
    # sig.P <- fonte (tipo, id) -- "PressureLine" ou "Valve_3_2_Ways"
    sig_in: dict[str, tuple[str, str]] = {}

    for conn in data["connections"]:
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        s_type, t_type = node_type_map.get(s_id, ""), node_type_map.get(t_id, "")

        if s_type == "Valve_3_2_Ways" and s_anc == "A" and role_map.get(s_id, "").startswith("signal_valve:"):
            sig_out[s_id] = (t_type, t_id, t_anc)

        if t_type == "Valve_3_2_Ways" and t_anc == "P" and role_map.get(t_id, "").startswith("signal_valve:"):
            sig_in[t_id] = (s_type, s_id)

    def _walk_chain_to_leaf(sig_id: str) -> list[str]:
        """Sobe a cadeia sig.P <- sig.A a partir de sig_id (que já
        alimenta o pilot/OrValve) até achar a raiz (P alimentado por uma
        PressureLine) -- devolve a cadeia da RAIZ até sig_id (ordem:
        farthest -> nearest, como cascade.py monta com prev_output)."""
        chain = [sig_id]
        current = sig_id
        while True:
            src_type, src_id = sig_in.get(current, (None, None))
            if src_type == "Valve_3_2_Ways":
                chain.insert(0, src_id)
                current = src_id
            else:
                return chain  # src_type == "PressureLine" (ou não encontrado)

    # Pontos de entrada num pilot ou OrValve: sig.A -> v42.PL/PR direto
    # (1 fonte só), sig.A -> OrValve.X/Y (2+ fontes), ou PL -> OrValve.X/Y
    # direto (fonte crua alimentando a OrValve sem nenhum sig).
    or_leaf_ids: dict[str, list[str]] = {}  # or_id -> [leaf sig_id acima dele, X depois Y]
    or_role_of: dict[str, str] = {}

    for n in data["nodes"]:
        if n["type"] == "OrValve":
            or_role_of[n["id"]] = n.get("_role", role_map.get(n["id"], ""))

    for conn in data["connections"]:
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        s_type, t_type = node_type_map.get(s_id, ""), node_type_map.get(t_id, "")
        if t_type == "OrValve" and t_anc in ("X", "Y"):
            or_leaf_ids.setdefault(t_id, [None, None])
            slot = 0 if t_anc == "X" else 1
            if s_type == "Valve_3_2_Ways":
                or_leaf_ids[t_id][slot] = _walk_chain_to_leaf(s_id)
            else:
                or_leaf_ids[t_id][slot] = []  # fonte crua (PressureLine)

    sources: dict[tuple[str, str], list[list[str]]] = {}

    for letter, v42_id in roles["v42_by_letter"].items():
        for pilot_anc, side in (("PL", "PL"), ("PR", "PR")):
            # Caso 1: sig.A -> v42.pilot direto (1 fonte só, sem OrValve)
            direct_sig = next((sid for sid, (tt, tid, ta) in sig_out.items()
                                if tt == "Valve_4_2_Ways" and tid == v42_id and ta == pilot_anc), None)
            if direct_sig is not None:
                sources[(letter, side)] = [_walk_chain_to_leaf(direct_sig)]
                continue

            # Caso 2: v42.pilot -> PL direto (1 fonte só, crua). cascade.py
            # seção 6b (linha 352) monta essa conexão com a 4/2 como
            # "source" e o barramento como "target" (não o contrário) --
            # confirmado lendo circuit_generator/methods/cascade.py e
            # também gerando cascade.generate(parse("A+B+A-B-"))
            # ["connections"] diretamente: contém
            # "gen-v42-A.PL -> gen-pl-grp1.X2", nunca o inverso.
            has_direct_pl = any(
                c["source"]["node"] == v42_id and c["source"]["anchor"] == pilot_anc
                and node_type_map.get(c["target"]["node"]) == "PressureLine"
                for c in data["connections"]
            )
            if has_direct_pl:
                sources[(letter, side)] = [[]]
                continue

            # Caso 3: cadeia de OrValve -- achar a OrValve final (a que
            # alimenta o pilot direto) e desenrolar a cadeia binária de
            # trás pra frente, na mesma ordem de criação de cascade.py
            # seção 6b (sources[0] é a mais distante).
            final_or = next((c["source"]["node"] for c in data["connections"]
                              if c["target"]["node"] == v42_id and c["target"]["anchor"] == pilot_anc
                              and node_type_map.get(c["source"]["node"]) == "OrValve"), None)
            if final_or is None:
                continue  # esse lado nunca dispara nesta sequência

            chain_or_ids = sorted(
                (oid for oid, role in or_role_of.items()
                 if role.startswith(f"or_valve:{letter}:{side}:")),
                key=lambda oid: int(or_role_of[oid].rsplit(":", 1)[1]),
            )
            leaves: list[list[str]] = []
            for i, or_id in enumerate(chain_or_ids):
                x_leaf, y_leaf = or_leaf_ids.get(or_id, [[], []])
                if i == 0:
                    leaves.append(x_leaf if x_leaf is not None else [])
                leaves.append(y_leaf if y_leaf is not None else [])
            sources[(letter, side)] = leaves

    return sources


def _logic_cell_width() -> float:
    cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return cfg["columns"]["logic_cell_width"]


def _walk_chain_to_leaf_generic(sig_in: dict, sig_id: str) -> list[str]:
    """Mesma lógica de _walk_chain_to_leaf (Task 2), fatorada pra reuso
    aqui -- sobe sig.P <- sig.A até achar a raiz alimentada por uma
    PressureLine."""
    chain = [sig_id]
    current = sig_id
    while True:
        src_type, src_id = sig_in.get(current, (None, None))
        if src_type == "Valve_3_2_Ways":
            chain.insert(0, src_id)
            current = src_id
        else:
            return chain


def apply(data: dict) -> dict:
    cfg  = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    cols = cfg["columns"]
    rows = cfg["rows"]

    roles = _build_role_maps(data)
    node_by_id = {n["id"]: n for n in data["nodes"]}
    sources = _build_trigger_sources(data, roles)

    grid = Grid()
    _reserved_cols: dict[str, set[int]] = {}

    def _place_aligned(row_id: str, virtual_col: int, node_id: str) -> tuple[float, float]:
        """Como grid.place, mas garante que virtual_col receba o índice de
        chegada `virtual_col` na linha (reservando as colunas 0..virtual_col-1
        com placeholders fictícios se ainda não tiverem sido usadas), pra que
        colunas puladas continuem alinhadas em X entre linhas diferentes."""
        reserved = _reserved_cols.setdefault(row_id, set())
        for kk in range(virtual_col):
            if kk not in reserved:
                grid.place(row_id, kk, f"__reserved__{row_id}__{kk}__")
                reserved.add(kk)
        reserved.add(virtual_col)
        return grid.place(row_id, virtual_col, node_id)

    # ── Largura de cada lado (nº de colunas = nº de folhas, N) ───────────
    def _side_width(letter: str, side: str) -> int:
        leaves = sources.get((letter, side), [])
        return len(leaves)  # N folhas -> N colunas (ver fórmula da Task 3)

    letters = sorted(roles["cyl_by_letter"])
    cyl_col: dict[str, int] = {}
    col = 0
    for letter in letters:
        col += _side_width(letter, "PL")
        cyl_col[letter] = col
        col += 1 + _side_width(letter, "PR")

    cyl_cell_w = cols["group_gap"]
    grid.add_row("cylinder",   cyl_cell_w, _M.cyl_height, rows["cylinder"],
                 x_origin=cols["cylinder_first_x"])
    grid.add_row("main_valve", cyl_cell_w, _M.v42_height, rows["main_valve"],
                 x_origin=cols["cylinder_first_x"])

    for letter in letters:
        cyl_id = roles["cyl_by_letter"][letter]
        v42_id = roles["v42_by_letter"][letter]
        x, y = _place_aligned("cylinder", cyl_col[letter], cyl_id)
        node_by_id[cyl_id]["position"] = {"x": x, "y": y}
        x, y = _place_aligned("main_valve", cyl_col[letter], v42_id)
        node_by_id[v42_id]["position"] = {"x": x, "y": y}

    # ── Colunas virtuais de cada folha/OrValve, por (letra, lado) ────────
    #
    #   N folhas -> colunas de offset 1..N a partir de cyl_col[letra]
    #   (sinal invertido pro lado PL). offset(leaf_j) = N-j pra j>=1
    #   (mesma coluna da OrValve or_i=j-1, empilhada abaixo dela);
    #   offset(leaf_0) = N (1 coluna a mais que a OrValve mais distante).
    #   offset(OrValve em or_i) = N-1-or_i (fórmula já usada em
    #   step_by_step_layout._or_valve_xy, reaproveitada sem alteração).
    # (max chain length per (letter, side) is not tracked separately -- the
    # "same row height for both sides of a cylinder" requirement holds for
    # free below, since sig_stack_{depth} rows are keyed by depth alone and
    # shared across ALL letters/sides, not allocated per-cylinder.)
    leaf_virtual_col: dict[tuple[str, str, int], int] = {}   # (letter, side, j) -> offset
    or_virtual_col:   dict[str, int] = {}                    # or_id -> offset (absoluto, cyl_col +/- offset)

    for letter in letters:
        for side, sign in (("PL", -1), ("PR", 1)):
            leaves = sources.get((letter, side), [])
            n = len(leaves)
            for j, leaf in enumerate(leaves):
                offset = n if j == 0 else (n - j)
                leaf_virtual_col[(letter, side, j)] = offset
            if n >= 2:
                for or_i in range(n - 1):
                    or_offset = n - 1 - or_i
                    role_prefix = f"or_valve:{letter}:{side}:{or_i}"
                    or_id = next(nid for nid, node in node_by_id.items()
                                 if node.get("_role", "") == role_prefix)
                    or_virtual_col[or_id] = cyl_col[letter] + sign * or_offset

    # ── Posiciona OrValve (linha própria, mesma altura pros 2 lados) ─────
    if or_virtual_col:
        min_vcol = min(or_virtual_col.values())
        grid.add_row("or_row", cyl_cell_w, _M.or_height, rows["or_row"],
                     x_origin=cols["cylinder_first_x"] + min_vcol * cyl_cell_w)
        for or_id in sorted(or_virtual_col, key=lambda k: or_virtual_col[k]):
            vcol = or_virtual_col[or_id]
            x, y = _place_aligned("or_row", vcol - min_vcol, or_id)
            node_by_id[or_id]["position"] = {"x": x, "y": y}

    # ── Posiciona as cadeias de sig de cada folha (0+ linhas empilhadas) ──
    #
    # IMPORTANTE: _place_aligned pressupõe que, para uma dada row_id, as
    # chamadas cheguem em ordem ASCENDENTE de virtual_col (ela pré-reserva
    # placeholders pras colunas 0..virtual_col-1 ainda não usadas). O loop
    # de folhas/leaves, porém, itera j = 0, 1, 2... e pro lado PR (sign=+1)
    # o vcol correspondente é DESCENDENTE em j (offset = n pra j==0, depois
    # n-j) -- ou seja, chamar _place_aligned na ordem de iteração de j
    # quebraria a pré-condição e colidiria com um placeholder já reservado
    # por uma chamada anterior de vcol maior (ValueError). Por isso,
    # primeiro coletamos todas as colocações (por row_id) e só então
    # chamamos _place_aligned em ordem ascendente de vcol dentro de cada
    # row_id -- mesma estratégia já usada acima pro or_row
    # (sorted(or_virtual_col, key=...)), generalizada aqui pra não depender
    # de saber de antemão qual lado precisa ser revertido.
    sig_stack_row_ids_created: set[str] = set()  # rastreia linhas já criadas (Grid não expõe "já existe")
    # row_id -> lista de (vcol, sig_id, depth)
    pending_by_row: dict[str, list[tuple[int, str, int]]] = {}
    for letter in letters:
        for side, sign in (("PL", -1), ("PR", 1)):
            leaves = sources.get((letter, side), [])
            for j, leaf in enumerate(leaves):
                if not leaf:
                    continue  # folha crua -- nenhuma válvula, nenhuma linha
                offset = leaf_virtual_col[(letter, side, j)]
                vcol = cyl_col[letter] + sign * offset
                for depth, sig_id in enumerate(leaf):
                    row_id = f"sig_stack_{depth}"
                    pending_by_row.setdefault(row_id, []).append((vcol, sig_id, depth))

    for row_id in sorted(pending_by_row, key=lambda rid: int(rid.rsplit("_", 1)[1])):
        placements = pending_by_row[row_id]
        depth = placements[0][2]
        if row_id not in sig_stack_row_ids_created:
            # NOTE pra Task 4/5: esta linha é GLOBAL (compartilhada por
            # TODOS os cilindros/letras/lados do circuito), não uma linha
            # por cilindro -- sig_stack_{depth} é chaveada só pela
            # profundidade da cadeia. Isso satisfaz "PL e PR do MESMO
            # cilindro compartilham a mesma altura de linha" como efeito
            # colateral de um invariante mais amplo ("todo mundo na mesma
            # profundidade compartilha a mesma linha", inclusive entre
            # cilindros diferentes) -- não foi verificado se esse
            # compartilhamento global continua correto quando a Região B
            # (Tasks 4/5) for empilhada por cima destas linhas.
            grid.add_row(row_id, cyl_cell_w, _M.v32_height,
                         rows["or_row"] + (depth + 1) * _M.v32_height * 1.5,
                         x_origin=cols["cylinder_first_x"])
            sig_stack_row_ids_created.add(row_id)
        for vcol, sig_id, _depth in sorted(placements, key=lambda p: p[0]):
            x, y = _place_aligned(row_id, vcol, sig_id)
            node_by_id[sig_id]["position"] = {"x": x, "y": y}

    # ── Região B: linhas de pressão + memórias (linhas locais 1..M) ──────
    n_groups = roles["n_groups"]
    n_mc     = roles["n_mc"]
    memory_x0 = cols["cylinder_first_x"]
    logic_cell_w = cols["logic_cell_width"]
    # NOTE (interface from Task 3's actual implementation, not the original
    # draft): Task 3 replaced a planned `max_rows_per_cyl` dict with
    # `sig_stack_row_ids_created`, a `set[str]` of the `sig_stack_{depth}`
    # row ids actually created (Region A's rows are global across all
    # cylinders, keyed only by depth -- see Task 3's code comments). Since
    # depths are always populated contiguously from 0, its length equals
    # the max chain depth reached anywhere in Region A -- use that here
    # instead of max_rows_per_cyl, which no longer exists.
    #
    # REGRESSÃO REAL (encontrada testando na UI de verdade, corrigida
    # aqui): a fórmula original somava só `N * v32_height * 1.5`
    # (o ESPAÇAMENTO entre linhas de sig_stack) ao topo de or_row, sem
    # somar a ALTURA do próprio corpo da linha mais funda -- com N=2, a
    # linha de sig_stack mais funda termina em
    # `or_row + 2*v32_height*1.5 + v32_height`, mas a fórmula antiga dava
    # uma PL começando 1 v32_height ANTES disso: sobreposição real de
    # sprite (ver test_pl_rows_start_below_the_deepest_sig_stack_row).
    # Corrigido calculando o Y real do fundo da Região A (or_row sozinho
    # se N==0, ou o fundo do sig_stack mais profundo se N>0) e preservando
    # a MESMA margem que `rows["pl_base"]` já dava pro caso N==0 (a
    # constante de config nunca mudou de significado, só o cálculo de onde
    # a Região A realmente termina).
    _region_a_margin = rows["pl_base"] - (rows["or_row"] + _M.or_height)
    if sig_stack_row_ids_created:
        _n_stack_rows = len(sig_stack_row_ids_created)
        _region_a_bottom = rows["or_row"] + _n_stack_rows * _M.v32_height * 1.5 + _M.v32_height
    else:
        _region_a_bottom = rows["or_row"] + _M.or_height
    pl_base_y = _region_a_bottom + _region_a_margin

    for g in range(n_groups):
        local_row = g + 1  # linha local 1..M
        y = pl_base_y + (local_row - 1) * rows["pl_gap"]
        pl_id = roles["pl_by_idx"][g]
        grid.add_row(f"pl_row_{g}", 200, _M.pl_pix_h, y, x_origin=memory_x0)
        x, y2 = grid.place(f"pl_row_{g}", 0, pl_id)
        node_by_id[pl_id]["position"] = {"x": x, "y": y2}

    # REGRESSÃO REAL (encontrada testando na UI de verdade, corrigida
    # aqui): a versão anterior colocava mem[i] na MESMA linha (mesmo y)
    # da PL que ele aciona via B -- como a PL é um barramento fino
    # desenhado nessa altura exata, o corpo da memória (bem mais alto,
    # v52_height) ficava literalmente por CIMA do traço da PL, cruzando
    # o desenho. O mapeamento lógico mem[i] <-> pl_grp[n_groups-1-i]
    # continua valendo (mesma ORDEM relativa: mem[n_mc-1] confirma o
    # grupo mais alto, mem[0] o mais baixo), mas o bloco de memórias
    # inteiro fica ABAIXO de TODAS as linhas de PL -- mesmo padrão já
    # usado por step_by_step_layout.py (região de lógica inteira abaixo
    # da região de PL, nunca intercalada linha a linha).
    memory_y_base = pl_base_y + n_groups * rows["pl_gap"] + rows["logic_row_gap"]
    for i in range(n_mc):
        mem_id = roles["mc_by_idx"][i]
        local_rank = n_mc - 1 - i  # 0 = memória mais alta (mem[n_mc-1])
        y = memory_y_base + local_rank * rows["pl_gap"]
        grid.add_row(f"memory_row_{i}", logic_cell_w, _M.v52_height, y, x_origin=memory_x0)
        x, y2 = grid.place(f"memory_row_{i}", 0, mem_id)
        node_by_id[mem_id]["position"] = {"x": x, "y": y2}

    # ── Coluna do botão (coluna 1, à esquerda da coluna de memórias) ─────
    if n_mc:
        mc0_id = roles["mc_by_idx"][0]
        mc0_y  = node_by_id[mc0_id]["position"]["y"]
        btn_id = roles["btn_id"]
        btn_x0 = memory_x0 - logic_cell_w
        grid.add_row("btn_row", logic_cell_w, _M.v32_height,
                     mc0_y + rows["logic_row_gap"], x_origin=btn_x0)
        x, y = grid.place("btn_row", 0, btn_id)
        node_by_id[btn_id]["position"] = {"x": x, "y": y}

    # ── Cadeias de confirmação PR (mem[i].PR) e fechamento (btn.P) ───────
    node_type_map = {n["id"]: n["type"] for n in data["nodes"]}
    sig_in: dict[str, tuple[str, str]] = {}
    for conn in data["connections"]:
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        s_type, t_type = node_type_map.get(s_id, ""), node_type_map.get(t_id, "")
        if t_type == "Valve_3_2_Ways" and t_anc == "P":
            sig_in[t_id] = (s_type, s_id)

    def _chain_feeding(target_id: str, target_anchor: str) -> list[str]:
        head = next((c["source"]["node"] for c in data["connections"]
                     if c["target"]["node"] == target_id and c["target"]["anchor"] == target_anchor
                     and node_type_map.get(c["source"]["node"]) == "Valve_3_2_Ways"), None)
        return _walk_chain_to_leaf_generic(sig_in, head) if head else []

    # Linhas locais de cima pra baixo: mem[-1] (n_mc-1) é o topo (offset 0),
    # mem[0] é o fundo. btn.P (fechamento) NÃO entra nesta escada -- ver
    # bloco dedicado logo abaixo (mesma coluna do botão, não a escada à
    # direita das memórias -- regressão real encontrada testando na UI:
    # a versão anterior tratava btn.P como só mais uma "linha" da escada
    # de confirmação das memórias, jogando a cadeia de fechamento pra
    # bem longe da coluna do botão).
    ordered_targets = [(roles["mc_by_idx"][i], "PR") for i in range(n_mc - 1, -1, -1)]

    offset = 0
    for target_id, target_anchor in ordered_targets:
        chain = _chain_feeding(target_id, target_anchor)
        if not chain:
            continue
        target_y = node_by_id[target_id]["position"]["y"]
        row_id = f"confirm_row_{target_id}"
        grid.add_row(row_id, logic_cell_w, _M.v32_height, target_y, x_origin=memory_x0)
        for k, sig_id in enumerate(chain):
            x, y = _place_aligned(row_id, offset + 1 + k, sig_id)
            node_by_id[sig_id]["position"] = {"x": x, "y": y}
        offset += len(chain)

    # ── Cadeia de fechamento (btn.P): coluna do botão, empilhada abaixo ──
    #
    #   Mesma coluna de btn_x0 (não a coluna de memórias) -- igual ao
    #   btn_row/closure_row/closure_stack_N do passo a passo. A cadeia é
    #   percorrida de trás pra frente ao posicionar: o elo mais próximo do
    #   botão (cujo A alimenta btn.P) fica na linha logo abaixo dele
    #   (depth 1); elos mais distantes (mais perto da raiz alimentada pela
    #   PL) ficam ainda mais abaixo.
    if n_mc:
        closure_chain = _chain_feeding(btn_id, "P")
        if closure_chain:
            closure_chain_top_down = list(reversed(closure_chain))
            btn_y = node_by_id[btn_id]["position"]["y"]
            for depth, sig_id in enumerate(closure_chain_top_down, start=1):
                row_id = f"closure_stack_{depth}"
                grid.add_row(row_id, logic_cell_w, _M.v32_height,
                             btn_y + depth * rows["logic_row_gap"], x_origin=btn_x0)
                x, y = grid.place(row_id, 0, sig_id)
                node_by_id[sig_id]["position"] = {"x": x, "y": y}

    node_pos = {nid: (n["position"]["x"], n["position"]["y"]) for nid, n in node_by_id.items()}
    pl_node_map = {pid: node_by_id[pid] for pid in roles["pl_by_idx"].values()}

    # ── Dimensiona as PressureLines pelo alcance real do grid ───────────────
    #
    #   Portado verbatim de step_by_step_layout.py (mesmo bloco, mesmo
    #   comentário-guia) -- já genérico sobre pl_node_map/
    #   grid.occupied_x_range, nenhuma substituição necessária (ver Task 6
    #   brief, item 1).
    pl_row_ids = {f"pl_row_{g}" for g in roles["pl_by_idx"]}
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
            if lo < 1:
                pl_node["position"]["x"] += (lo - 1) * _M.pl_spacing
                node_pos[pl_id] = (pl_node["position"]["x"], pl_node["position"]["y"])

    # ── Reatribuição dos anchors das PressureLines por proximidade ──────────
    #
    #   Portado de step_by_step_layout.py (_pl_anchor_x/_nearest_pl_anchor/
    #   _resolve_conflict, mesmos nomes e corpo) -- a única mudança real é
    #   no elif chain de connections_sorted mais abaixo, que reconhece as
    #   formas de conexão PL/PR/A/B <-> PressureLine específicas do cascata
    #   (mc é Valve_5_2_Ways, step-by-step só tem Valve_3_2_Ways).
    def _pl_anchor_x(pl_node: dict, anchor_name: str, list_origin: int | None = None) -> float:
        pl_x = node_pos[pl_node["id"]][0]
        if list_origin is None:
            list_origin = min(int(a[1:]) for a in pl_node["properties"]["anchors"])
        return pl_x + _M.pl_pix_w / 2 + (int(anchor_name[1:]) - list_origin) * _M.pl_spacing

    def _nearest_pl_anchor(pl_node: dict, target_x: float, side: str = "any",
                            min_margin: float = 0.0) -> str:
        anchors = pl_node["properties"]["anchors"]
        list_origin = min(int(a[1:]) for a in anchors)
        scored = [(int(n[1:]), _pl_anchor_x(pl_node, n, list_origin), n) for n in anchors]
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

    pl_anchor_used: dict[tuple[str, int], tuple[str, float, float]] = {}
    conn_by_owner: dict[tuple[str, str], tuple] = {}
    or_source_x_used: dict[int, tuple[str, float, float]] = {}

    def _resolve_conflict(pl_node: dict, anchor: str, owner: str,
                           owner_y: float, conn_ref: dict, side: str,
                           push_dir: int = 0, avoid_global_x: bool = False) -> str:
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

            if avoid_global_x:
                gx = round(ax)
                prev_global = or_source_x_used.get(gx)
                if prev_global is not None:
                    prev_oid, prev_oy, prev_pl_y = prev_global
                    same_order = (oy < prev_oy) == (pl_y < prev_pl_y)
                    if prev_oid != oid and not same_order:
                        return _reg(_next(anc, pdir), oid, oy, cref, seen, pdir)
                or_source_x_used[gx] = (oid, oy, pl_y)

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
            avoid_global_x = False
            owner_id = f"{t_id}#{t_anc}" if node_type_map.get(t_id) == "OrValve" else t_id
            if t_anc == "PL":
                anc = _nearest_pl_anchor(pl, tgt_x, "left")
                push_dir = -1
            elif t_anc == "PR":
                anc = _nearest_pl_anchor(pl, tgt_x, "right", min_margin=_PL_ANCHOR_MIN_MARGIN)
                push_dir = 1
            elif t_anc == "P" and node_type_map.get(t_id) == "Valve_3_2_Ways":
                valve_left_x = node_by_id[t_id]["position"]["x"]
                safe_x = valve_left_x - _M.pilot_w
                anc = _nearest_pl_anchor(pl, safe_x, "left")
                push_dir = -1
                avoid_global_x = True
            elif t_anc == "X" and node_type_map.get(t_id) == "OrValve":
                anc = _nearest_pl_anchor(pl, tgt_x, "left", min_margin=_PL_ANCHOR_MIN_MARGIN)
                push_dir = -1
                avoid_global_x = True
            elif t_anc == "Y" and node_type_map.get(t_id) == "OrValve":
                anc = _nearest_pl_anchor(pl, tgt_x, "right", min_margin=_PL_ANCHOR_MIN_MARGIN)
                push_dir = 1
                avoid_global_x = True
            # ── Formas específicas do cascata: PL/PR/A/B de Valve_5_2_Ways
            #   (memória) alimentados DIRETO por uma PressureLine (sem sig
            #   no meio) -- step_by_step_layout.py nunca tem essa forma
            #   porque suas memórias são Valve_3_2_Ways, e o único caso
            #   "PL como fonte" delas é P (já coberto acima). Verificado
            #   rodando cascade.generate() em várias sequências reais
            #   (ver Task 6 report): o gerador atual NUNCA produz uma
            #   PressureLine como origem de conexão pra mem.PL/PR/A/B --
            #   essas conexões vêm sempre de mem ou de um sig (lado
            #   "t_id in pl_node_map" abaixo, ou o "else" genérico do sig).
            #   Mantido por simetria/robustez com o pedido do brief, caso
            #   uma topologia futura produza essa forma diretamente.
            elif t_anc in ("PL", "PR") and node_type_map.get(t_id) == "Valve_5_2_Ways":
                anc = _nearest_pl_anchor(pl, tgt_x, "left" if t_anc == "PL" else "right",
                                          min_margin=_PL_ANCHOR_MIN_MARGIN)
                push_dir = -1 if t_anc == "PL" else 1
            elif t_anc in ("A", "B") and node_type_map.get(t_id) == "Valve_5_2_Ways":
                anc = _nearest_pl_anchor(pl, tgt_x)
                push_dir = 0
            else:
                anc = _nearest_pl_anchor(pl, tgt_x)
                push_dir = 0
                avoid_global_x = False
            conn["source"]["anchor"] = _resolve_conflict(
                pl, anc, owner_id, node_pos.get(t_id, (0, 0))[1], conn, "source", push_dir,
                avoid_global_x=avoid_global_x)

        elif t_id in pl_node_map and t_anc.startswith("X"):
            pl = pl_node_map[t_id]
            src_x = _target_x(s_id, s_anc)
            anc = _nearest_pl_anchor(pl, src_x)
            # Cobre, entre outros, mem[i].A/mem[i].B -> PL (fechamento de
            # anel / bus de grupo do cascata) -- já genérico, sem
            # substituição (ver Task 6 brief, item 2: "a mirrored branch
            # ... needs no change").
            conn["target"]["anchor"] = _resolve_conflict(
                pl, anc, s_id, node_pos.get(s_id, (0, 0))[1], conn, "target",
                avoid_global_x=True)

    # ── Poda global das PressureLines ────────────────────────────────────
    #
    #   Portado verbatim de step_by_step_layout.py (mesmo bloco).
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
    #
    #   Portado verbatim de step_by_step_layout.py (mesmo bloco).
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
    #
    #   Portado verbatim de step_by_step_layout.py (mesmo bloco).
    from circuit_generator.astar_router import build_grid, route_connection, get_exit_dir

    def _scene_xy(node_id: str, anchor_name: str) -> tuple[float, float] | None:
        pos = node_by_id[node_id]["position"]
        ntype = node_type_map.get(node_id, "")
        if ntype == "PressureLine" and anchor_name.startswith("X"):
            idx = int(anchor_name[1:])
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
