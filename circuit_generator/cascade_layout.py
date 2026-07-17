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

# Margem extra (além de _PL_ANCHOR_MIN_MARGIN) só pra conexão PL -> sig.P
# da escada de confirmação PR das memórias (Região B, confirm_row) --
# _PL_ANCHOR_MIN_MARGIN sozinho ainda deixava pouca folga nesse caso
# específico (feedback direto testando a UI real). A Região A usa só a
# margem base -- não tem o mesmo aperto de geometria que justificou essa
# folga extra aqui (feedback direto testando a UI real: "vai tão longe
# mesmo sem nenhum anchor bloqueado").
_CONFIRM_ROW_P_EXTRA_MARGIN = 150

# Espalha (stagger) o alvo das conexões mem.PL/A/B -> PL por índice de
# memória, em px, crescendo pra direita -- sem isso, toda memória mira no
# MESMO anchor (mesmo src_x, não depende de qual memória), empilhando
# várias conexões não-cruzantes na mesma coluna (feedback direto testando
# a UI real).
_MEM_PL_STAGGER = 60

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

    # REGRESSÃO REAL (feedback direto testando a UI real, com imagem
    # anotada): com cols["group_gap"] sozinho, duas sigs adjacentes de
    # colunas vizinhas (ex: PR de um cilindro e PL do próximo) podiam se
    # sobrepor visualmente -- a folga (group_gap - largura do sprite da
    # sig) não cobria o pior caso em que a sig da esquerda está no estado
    # comutado (BODY_VISUALS[1] desloca o corpo INTEIRO, incluindo os
    # atuadores, +pilot_side_offset_x pra direita -- ver sig_col_pitch em
    # sprite_metrics.py). Usa o maior entre o valor configurado e o pitch
    # mínimo que garante não-sobreposição nesse pior caso.
    cyl_cell_w = max(cols["group_gap"], _M.sig_col_pitch)
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
                # REGRESSÃO REAL (feedback direto testando a UI): `leaf`
                # vem em ordem raiz->ponta (leaf[0] = alimentada pela PL,
                # leaf[-1] = cujo A alimenta o pilot/OrValve). A ponta
                # precisa ficar mais PERTO do pilot/OrValve que alimenta
                # (linha de MENOR y, mais perto de or_row) -- a raiz, que
                # só precisa alcançar a PL (mais abaixo), fica mais longe
                # (maior y). Sem o reversed(), a ordem saía invertida:
                # raiz em cima, ponta embaixo.
                for depth, sig_id in enumerate(reversed(leaf)):
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

    # mem_id -> x da válvula que ALIMENTA (aciona) diretamente o PR dessa
    # memória (o último elo da cadeia, chain[-1] -- o mais à direita na
    # escada) -- usado abaixo pra rotear mem[i].B (i != mem[-1], a mais
    # alta) até logo à esquerda do sprite dessa válvula, em vez de um
    # stagger genérico (feedback direto testando a UI real, com desenho
    # anexado mostrando a rota esperada).
    driving_sig_x_by_mem: dict[str, float] = {}

    offset = 0
    for target_id, target_anchor in ordered_targets:
        chain = _chain_feeding(target_id, target_anchor)
        if not chain:
            continue
        # Diagonal (1 linha abaixo da memória que alimenta), mesma regra
        # já usada pro par botão/mem[0] -- decisão confirmada com o
        # usuário (antes ficava na MESMA linha da memória). rows["pl_gap"]
        # precisa ser >= logic_row_gap + v32_height pra essa diagonal não
        # colidir com a próxima memória abaixo (ver cascade_layout_config.json).
        target_y = node_by_id[target_id]["position"]["y"] + rows["logic_row_gap"]
        row_id = f"confirm_row_{target_id}"
        grid.add_row(row_id, logic_cell_w, _M.v32_height, target_y, x_origin=memory_x0)
        # REGRESSÃO REAL (feedback direto testando a UI): `chain` vem em
        # ordem raiz->ponta (chain[0] = alimentada pela PL, chain[-1] =
        # cujo A alimenta target_id.PR). A ponta (que conecta na memória)
        # precisa ficar mais PERTO da coluna de memórias (menor offset,
        # mais à esquerda) -- a raiz, que só precisa alcançar a PL (mais
        # longe), fica mais à direita. Sem o reversed(), a ordem saía
        # invertida: raiz colada na memória, ponta longe.
        for k, sig_id in enumerate(reversed(chain)):
            x, y = _place_aligned(row_id, offset + 1 + k, sig_id)
            node_by_id[sig_id]["position"] = {"x": x, "y": y}
        offset += len(chain)
        driving_sig_x_by_mem[target_id] = node_by_id[chain[-1]]["position"]["x"]

    # ── Cadeia de fechamento (btn.P): coluna do botão, empilhada abaixo ──
    #
    #   Mesma coluna de btn_x0 (não a coluna de memórias) -- igual ao
    #   btn_row/closure_row/closure_stack_N do passo a passo. A cadeia é
    #   percorrida de trás pra frente ao posicionar: o elo mais próximo do
    #   botão (cujo A alimenta btn.P) fica na linha logo abaixo dele
    #   (depth 1); elos mais distantes (mais perto da raiz alimentada pela
    #   PL) ficam ainda mais abaixo.
    closure_sig_ids: set[str] = set()
    if n_mc:
        closure_chain = _chain_feeding(btn_id, "P")
        if closure_chain:
            closure_sig_ids = set(closure_chain)
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

    # sig_ids da Região A (folhas empilhadas logo abaixo de or_row, ver
    # Task 3) -- as que alimentam o pilot da 4/2 (PL/PR) direto ou via
    # OrValve. REGRESSÃO REAL (feedback direto testando a UI real, com
    # imagem anotada mostrando a rota esperada): a conexão PL -> sig.P
    # dessas sigs deve sair pela DIREITA (desce e depois vira à direita
    # até a PressureLine), não pela esquerda.
    region_a_sig_ids = {sid for leaves in sources.values() for leaf in leaves for sid in leaf}

    # sig_ids que entram pela ESQUERDA na conexão PL -> sig.P: só a cadeia
    # de fechamento (closure_sig_ids, coluna do botão) -- feedback direto
    # do usuário: essa sig deve continuar entrando pela esquerda.
    left_entry_sig_ids = set(closure_sig_ids)

    # mem_id -> índice i (mc_by_idx invertido) -- usado abaixo pra
    # espalhar (stagger) o alvo das conexões mem.PL/A/B -> PL por memória.
    mc_idx_by_id = {mid: i for i, mid in roles["mc_by_idx"].items()}

    # Rastreia os X (arredondados, globais -- não por PL) já usados pelas
    # conexões mem.PL/A/B -> PL, SEPARADO POR TIPO de anchor de origem
    # (PL/A/B cada um com seu próprio set) -- pra garantir que memórias
    # DIFERENTES usando o MESMO tipo de anchor nunca acabem na mesma
    # coluna mesmo indo pra PLs diferentes. _resolve_conflict/
    # avoid_global_x sozinho não pega isso quando as duas rotas não se
    # cruzam (same_order), que é justamente o caso mais comum aqui
    # (achado testando a UI real: mem[2].B e mem[3].B colidindo por
    # coincidência, um vindo do cálculo "à esquerda da 3/2" e outro do
    # stagger genérico). Separado por tipo (não um set global único) pra
    # não deixar o dedup de B empurrar o anchor de uma conexão PL sem
    # necessidade -- regressão real: o usuário reportou o PL mudando de
    # posição mesmo sem nenhum pedido de mudança ali.
    _mem_pl_used_x: dict[str, set[int]] = {"PL": set(), "A": set(), "B": set()}

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

    # ── Corrige orientação X/Y das OrValve (evita fio cruzado) ───────────
    #
    #   cascade.py conecta X à fonte cronologicamente mais cedo e Y à mais
    #   tarde (ver methods/cascade.py seção 6b), sem saber onde cada uma
    #   vai parar no layout. Isso funciona por coincidência no lado PL (a
    #   fonte mais distante cronologicamente também fica mais à ESQUERDA
    #   física, ver sign=-1 em leaf_virtual_col acima), mas inverte no
    #   lado PR (a fonte mais distante fica mais à DIREITA física, ver
    #   sign=+1) -- feedback direto testando a UI real, com imagem
    #   anotada: no lado PR a fonte mais à direita entrava em X (anchor
    #   ESQUERDO da OrValve, exit_directions left), obrigando o fio a
    #   cruzar por cima da OrValve inteira pra entrar do lado errado.
    #
    #   X é sempre o anchor da ESQUERDA da OrValve e Y o da DIREITA (ver
    #   or_valve.py). Troca as duas pontas sempre que a fonte ligada em X
    #   está fisicamente à direita da fonte ligada em Y -- garante que a
    #   fonte mais à esquerda sempre entra em X e a mais à direita em Y,
    #   não importa a ordem cronológica que cascade.py usou pra ligar.
    def _or_source_x(node_id: str, anchor_name: str) -> float | None:
        ntype = node_type_map.get(node_id, "")
        if ntype == "PressureLine" and anchor_name.startswith("X"):
            return _pl_anchor_x(node_by_id[node_id], anchor_name)
        pos = node_by_id.get(node_id, {}).get("position")
        if pos is None:
            return None
        local = anchor_local_for_routing(ntype, anchor_name)
        return pos["x"] + (local[0] if local else 0.0)

    or_xy_conns: dict[str, dict[str, dict]] = {}
    for conn in data["connections"]:
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        if node_type_map.get(t_id) == "OrValve" and t_anc in ("X", "Y"):
            or_xy_conns.setdefault(t_id, {})[t_anc] = conn

    for sides in or_xy_conns.values():
        x_conn, y_conn = sides.get("X"), sides.get("Y")
        if x_conn is None or y_conn is None:
            continue
        x_src_x = _or_source_x(x_conn["source"]["node"], x_conn["source"]["anchor"])
        y_src_x = _or_source_x(y_conn["source"]["node"], y_conn["source"]["anchor"])
        if x_src_x is None or y_src_x is None:
            continue
        if x_src_x > y_src_x:
            x_conn["target"]["anchor"], y_conn["target"]["anchor"] = "Y", "X"

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
            elif t_anc == "P" and node_type_map.get(t_id) == "Valve_3_2_Ways" and t_id in left_entry_sig_ids:
                # Sig da cadeia de fechamento (coluna do botão, à esquerda
                # de tudo): entra pela esquerda -- mesma lógica herdada do
                # passo a passo (feedback direto do usuário: deve
                # continuar entrando pela esquerda). É a ÚNICA exceção --
                # tanto a Região A (folha do OR/sig-staircase que alimenta
                # o pilot da 4/2) quanto a Região B (confirm_row, alimenta
                # mem.PR) saem pela direita, ver branches abaixo.
                valve_left_x = node_by_id[t_id]["position"]["x"]
                safe_x = valve_left_x - _M.pilot_w
                anc = _nearest_pl_anchor(pl, safe_x, "left")
                push_dir = -1
                avoid_global_x = True
            elif t_anc == "P" and node_type_map.get(t_id) == "Valve_3_2_Ways" and t_id in region_a_sig_ids:
                # Região A (folha do OR/sig-staircase que alimenta o pilot
                # da 4/2 direto ou via OrValve): sai pela DIREITA (feedback
                # direto testando a UI real, com imagem anotada mostrando a
                # rota esperada: sai pra direita, depois sobe até o anchor
                # mais próximo à direita). Só a margem BASE
                # (_PL_ANCHOR_MIN_MARGIN) -- sem a margem extra do
                # confirm_row abaixo, que nesse caso não tem nenhum
                # obstáculo pra justificar (feedback direto testando a UI
                # real: "vai tão longe mesmo sem nenhum anchor bloqueado").
                anc = _nearest_pl_anchor(pl, tgt_x, "right", min_margin=_PL_ANCHOR_MIN_MARGIN)
                push_dir = 1
                avoid_global_x = True
            elif t_anc == "P" and node_type_map.get(t_id) == "Valve_3_2_Ways":
                # Região B (confirm_row, alimenta mem.PR): sai pela DIREITA
                # (feedback direto testando a UI real, com imagem anotada
                # mostrando a rota esperada: sai pra direita, depois sobe
                # até o anchor mais próximo à direita). `tgt_x` (calculado
                # acima via _target_x -> anchor_local_for_routing) já é o
                # pior caso ajustado pro deslocamento de comutação (mesmo
                # fix de anchor_local_for_routing("Valve_3_2_Ways","P") em
                # sprite_metrics.py) -- usar um safe_x diferente aqui
                # (ex: baseado só em v32_width+pilot_w) faria o roteador
                # mirar num ponto MAIS À DIREITA do que o endpoint real
                # (sempre tgt_x), obrigando o traço a voltar pra
                # esquerda no último trecho -- exatamente o zigue-zague
                # que este fix deveria eliminar, não criar. Margem extra
                # (_CONFIRM_ROW_P_EXTRA_MARGIN): a margem padrão sozinha
                # ainda deixava pouca folga aqui especificamente (feedback
                # direto testando a UI real) -- diferente da Região A
                # acima, que não precisa dessa folga extra.
                anc = _nearest_pl_anchor(pl, tgt_x, "right",
                                          min_margin=_PL_ANCHOR_MIN_MARGIN + _CONFIRM_ROW_P_EXTRA_MARGIN)
                push_dir = 1
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
            # REGRESSÃO REAL (feedback direto testando a UI): toda
            # memória calcula o MESMO src_x pra PL/A/B (o anchor local
            # não depende de QUAL memória, só do tipo/anchor), então
            # mem[0].B, mem[1].B, mem[2].B... miravam todas no MESMO
            # anchor em suas respectivas PLs -- a checagem de conflito
            # (avoid_global_x/same_order) não pega isso porque essas
            # conexões não se CRUZAM entre si (mantêm ordem consistente),
            # só ficam empilhadas na mesma coluna, atravessando o corpo de
            # outras memórias/sigs no caminho.
            if node_type_map.get(s_id) == "Valve_5_2_Ways" and s_id in mc_idx_by_id:
                mem_idx = mc_idx_by_id[s_id]
                next_mem_id = roles["mc_by_idx"].get(mem_idx + 1)
                driving_x = (driving_sig_x_by_mem.get(next_mem_id)
                             if s_anc == "B" and next_mem_id else None)
                if driving_x is not None:
                    # mem[i].B (i != mem[-1], a mais alta): mira bem à
                    # esquerda do sprite da 3/2 que aciona mem[i+1]
                    # diretamente (chain[-1] daquela confirmação) --
                    # senão o traço atravessa essa válvula no caminho pra
                    # cima (feedback direto testando a UI, com desenho
                    # anexado mostrando a rota esperada). mem[-1] (sem
                    # próxima memória acima) e o resto (PL/A) continuam
                    # com o stagger genérico abaixo.
                    #
                    # REGRESSÃO REAL (feedback direto testando a UI, com
                    # imagem anotada): a margem original (v32_width +
                    # pilot_w = 400px) deixava o traço longe demais da
                    # sig, criando um desvio visualmente grande em vez de
                    # "colar" nela -- só pilot_w já é suficiente pra
                    # limpar o atuador esquerdo (limit_switch) da sig.
                    src_x = driving_x - _M.pilot_w
                else:
                    # Espalha (stagger) o alvo por memória, crescendo pra
                    # direita conforme o índice -- cada memória passa a
                    # mirar numa coluna própria.
                    src_x += mem_idx * _MEM_PL_STAGGER
            anc = _nearest_pl_anchor(pl, src_x)
            if (node_type_map.get(s_id) == "Valve_5_2_Ways" and s_id in mc_idx_by_id
                    and s_anc in _mem_pl_used_x):
                used_x = _mem_pl_used_x[s_anc]
                gx = round(_pl_anchor_x(pl, anc))
                _guard = 0
                while gx in used_x and _guard < n_mc + 2:
                    idx = int(anc[1:]) + 1
                    anc = f"X{idx}"
                    gx = round(_pl_anchor_x(pl, anc))
                    _guard += 1
                used_x.add(gx)
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

    # ── Roteamento manual determinístico: mem.PL/A/B -> PL ───────────────
    #
    #   Feedback direto testando a UI real: não dá pra confiar no A* pra
    #   essas conexões -- mesmo com o stagger por memória (acima) evitando
    #   que duas memórias mirem no mesmo anchor, o A* ainda podia escolher
    #   um caminho que atravessa outra memória/sig no meio do caminho,
    #   já que ele só evita OBSTÁCULOS conhecidos, não sabe que "cada
    #   memória devia ficar na sua própria pista". Constrói a rota à mão:
    #   sai na direção natural do anchor de origem (stub de EXIT_PX, igual
    #   ao A*), dobra pra alinhar com a coluna (x) do anchor de destino já
    #   escolhido acima, e sobe reto até ele -- 2 waypoints fixos, sem
    #   nenhuma decisão de pathfinding envolvida.
    _EXIT_DIR_VEC = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}
    _MANUAL_EXIT_PX = 40  # mesmo EXIT_PX usado pelo astar_router, pra ficar visualmente coerente

    manually_routed: set[int] = set()
    for i, conn in enumerate(data.get("connections", [])):
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        if not (s_anc in ("PL", "A", "B") and node_type_map.get(s_id) == "Valve_5_2_Ways"
                and node_type_map.get(t_id) == "PressureLine"):
            continue
        spos = _scene_xy(s_id, s_anc)
        tpos = _scene_xy(t_id, t_anc)
        if spos is None or tpos is None:
            continue
        src_dir = get_exit_dir("Valve_5_2_Ways", s_anc)
        if src_dir in ("LEFT", "RIGHT"):
            # REGRESSÃO REAL (feedback direto testando a UI, com imagem
            # anotada -- "rabinho"): PL (e PR, se algum dia usado aqui) já
            # sai posicionado FORA do corpo por conta própria
            # (anchor_local_for_routing = -pilot_w/+pilot_w, não em cima
            # da borda como B/A) -- somar mais um stub de EXIT_PX podia
            # jogar o ponto além de onde o anchor de destino realmente
            # está (que costuma ficar mais perto do corpo, por causa do
            # stagger), obrigando o traço a voltar pra trás logo na saída.
            # Sem stub aqui: vai direto da origem até a coluna do anchor
            # de destino -- SEGUNDA REGRESSÃO REAL (mesmo "rabinho",
            # achada de novo testando a UI): como stub == spos nesse
            # caso, os DOIS waypoints abaixo ficavam no mesmíssimo ponto
            # (mesmo x, mesmo y) -- um segmento de comprimento zero, que o
            # desenho renderiza como um "rabinho"/nó visual espúrio bem em
            # cima do anchor. Um waypoint só (o cotovelo) já é suficiente:
            # o primeiro segmento (anchor -> cotovelo) já é o trecho
            # horizontal que sai da origem, sem precisar repetir o ponto
            # de partida como waypoint.
            corner = (tpos[0], spos[1])
            conn["waypoints"] = [{"x": corner[0], "y": corner[1]}]
            manually_routed.add(i)
            continue
        dx, dy = _EXIT_DIR_VEC[src_dir]
        stub = (spos[0] + dx * _MANUAL_EXIT_PX, spos[1] + dy * _MANUAL_EXIT_PX)
        corner = (tpos[0], stub[1])
        conn["waypoints"] = [{"x": stub[0], "y": stub[1]}, {"x": corner[0], "y": corner[1]}]
        manually_routed.add(i)

    # ── Roteamento manual determinístico: sig.A -> sig.P (elos de cadeia) ──
    #
    #   Cobre tanto os elos do sig_stack da Região A (mesma coluna, ver
    #   Task 3) quanto os do confirm_row da Região B (mesma linha, colunas
    #   diferentes, ver Task 5) e a cadeia de fechamento (mesma coluna do
    #   botão) -- todos usam a MESMA forma de conexão (sig.A ->
    #   próximo_sig.P ou sig.A -> btn.P, já que btn também é
    #   Valve_3_2_Ways). Feedback direto testando a UI real: não dá pra
    #   confiar no A* aqui também -- mesmo o caso "mesma coluna" (que
    #   deveria ser uma reta vertical simples) estava saindo com um
    #   zigue-zague de 4 waypoints.
    #
    #   Mesma coluna (A e P compartilham x, caso mais comum -- sig_stack e
    #   cadeia de fechamento): reta vertical, sem waypoint nenhum (A* nem
    #   precisa entrar em ação, o segmento reto entre os dois anchors já
    #   é o caminho certo).
    #   Colunas diferentes (confirm_row, quando o átomo confirmado é um
    #   bloco paralelo): sai de A na horizontal até o meio do caminho,
    #   desce/sobe pra altura de P, entra em P na horizontal -- 2
    #   waypoints, formando um "Z" (H-V-H) em vez de zigue-zaguear.
    for i, conn in enumerate(data.get("connections", [])):
        if i in manually_routed:
            continue
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        if not (s_anc == "A" and t_anc == "P"
                and node_type_map.get(s_id) == "Valve_3_2_Ways"
                and node_type_map.get(t_id) == "Valve_3_2_Ways"):
            continue
        spos = _scene_xy(s_id, s_anc)
        tpos = _scene_xy(t_id, t_anc)
        if spos is None or tpos is None:
            continue
        # Detecta "mesma coluna" pela posição do NÓ, não do anchor: "P"
        # sempre soma o offset de pior-caso de comutação
        # (anchor_local_for_routing, ver fix anterior), "A" nunca soma
        # nada -- comparar spos/tpos diretamente faz um sig_stack/cadeia
        # de fechamento (mesma coluna de verdade) parecer "coluna
        # diferente" só por causa desse offset, disparando o Z
        # desnecessariamente.
        same_column = round(node_by_id[s_id]["position"]["x"]) == round(node_by_id[t_id]["position"]["x"])
        if same_column:
            conn["waypoints"] = []
        else:
            mid_x = (spos[0] + tpos[0]) / 2
            conn["waypoints"] = [{"x": mid_x, "y": spos[1]}, {"x": mid_x, "y": tpos[1]}]
        manually_routed.add(i)

    astar_grid = build_grid(data["nodes"])
    for i, conn in enumerate(data.get("connections", [])):
        if i in manually_routed:
            continue
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
