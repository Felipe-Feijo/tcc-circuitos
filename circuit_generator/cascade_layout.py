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
