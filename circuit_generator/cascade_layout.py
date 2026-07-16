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
from pathlib import Path

from circuit_generator.grid_layout import Grid
from circuit_generator.sprite_metrics import METRICS as _M, anchor_local_for_routing

_CONFIG_PATH = Path(__file__).parent / "cascade_layout_config.json"


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


def apply(data: dict) -> dict:
    cfg  = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    cols = cfg["columns"]
    rows = cfg["rows"]

    roles = _build_role_maps(data)
    node_by_id = {n["id"]: n for n in data["nodes"]}

    grid = Grid()

    # ── Região A (parcial): pistão/válvula, 1 coluna sequencial por letra ──
    #
    #   Índice sequencial simples por enquanto (ordem alfabética) -- a
    #   Task 3 substitui esse índice por um cálculo que reserva espaço
    #   extra pra escada de OR/sig de cada lado, igual ao já feito em
    #   step_by_step_layout.py.
    cyl_cell_w = cols["group_gap"]
    grid.add_row("cylinder",   cyl_cell_w, _M.cyl_height, rows["cylinder"],
                 x_origin=cols["cylinder_first_x"])
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

    return data
