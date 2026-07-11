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

    return data
