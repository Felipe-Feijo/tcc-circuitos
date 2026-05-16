import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "layout_config.json"


def _load_config() -> dict:
    with _CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


# ── Anchor offsets (coordenadas locais dentro do item) ────────────────────────
#
# Derivados diretamente dos arquivos de cada NodeItem:
#
#   Exhaust      (33×36):  R  → (width*0.5,   0)    = (16.5,  0)
#   PressureSource (31×37): P  → (width*0.467, 0)    = (14.48, 0)
#   Valve_3_2_Ways (300×180):
#       A → (width*254/300,  0)   = (254,   0)   topo
#       R → (width*190/300, 180)  = (190, 180)   base
#       P → (width*254/300, 180)  = (254, 180)   base
#   Valve_4_2_Ways (300×180):
#       P → (width*191/300, 180)  = (191, 180)   base
#       A → (width*191/300,  0)   = (191,   0)   topo
#       B → (width*256/300,  0)   = (256,   0)   topo
#       R → (width*256/300, 180)  = (256, 180)   base
#   Valve_5_2_Ways (450×180):
#       P  → (width*338/450, 180) = (338, 180)   base
#       A  → (width*270/450,  0)  = (270,   0)   topo
#       B  → (width*405/450,  0)  = (405,   0)   topo
#       R1 → (width*271/450, 180) = (271, 180)   base
#       R2 → (width*405/450, 180) = (405, 180)   base

_ANCHOR_LOCAL: dict[str, dict[str, tuple[float, float]]] = {
    "Exhaust": {
        "R": (33 * 0.5, 0),
    },
    "PressureSource": {
        "P": (31 * 0.467, 0),
    },
    "Valve_3_2_Ways": {
        "A": (300 * 254/300,   0),
        "R": (300 * 190/300, 180),
        "P": (300 * 254/300, 180),
    },
    "Valve_4_2_Ways": {
        "P":  (300 * 191/300, 180),
        "A":  (300 * 191/300,   0),
        "B":  (300 * 256/300,   0),
        "R":  (300 * 256/300, 180),
        # Pilots: body.left() - pilot_w e body.right() + pilot_w; y = height*0.6222
        # pilot sprite = 100×180 → PL.x = 0 - 100 = -100; PR.x = 300 + 100 = 400
        "PL": (-100, 180 * 0.6222),
        "PR": (400,  180 * 0.6222),
    },
    "Valve_5_2_Ways": {
        "P":  (450 * 338/450, 180),
        "A":  (450 * 270/450,   0),
        "B":  (450 * 405/450,   0),
        "R1": (450 * 271/450, 180),
        "R2": (450 * 405/450, 180),
        # Pilots: mesmo padrão da 4/2 — pilot sprite 100px
        "PL": (-100, 180 * 0.6222),
        "PR": (550,  180 * 0.6222),
    },
}

# Anchor local do próprio filho que será alinhado ao anchor do pai
_CHILD_CONNECT_ANCHOR: dict[str, str] = {
    "Exhaust":       "R",   # Exhaust conecta pelo "R" (topo)
    "PressureSource": "P",  # PressureSource conecta pelo "P" (topo)
}


def _anchor_local(node_type: str, anchor_name: str) -> tuple[float, float] | None:
    """Retorna (dx, dy) do anchor dentro do item, ou None se desconhecido."""
    return _ANCHOR_LOCAL.get(node_type, {}).get(anchor_name)


def apply(data: dict) -> dict:
    """
    Recebe o JSON com _role em cada nó.
    Lê layout_config.json, calcula e preenche position.x e position.y.
    Remove _role de todos os nós.
    Retorna o dict modificado (in-place).

    Fase 1 — posiciona todos os nós primários (não-Exhaust, não-PS dedicados)
              com base no _role, igual antes.
    Fase 2 — posiciona Exhaust e PressureSource relativos ao anchor do nó pai
              ao qual estão conectados, usando _ANCHOR_LOCAL.

    Roles suportados (cascade pneumático):
      "pressure_source"              — gen-ps (fonte principal)
      "pressure_line_main"           — (legacy)
      "button"                       — gen-btn
      "and_start"
      "cylinder:{letter}"
      "main_valve:{letter}"          — gen-v42-{letter}
      "exhaust:v42-{letter}-P"       — Exhaust dedicado da porta P da v42
      "pressure_source:v42-{letter}-R" — PS dedicado da porta R da v42
      "memory:{n}"                   — gen-mc-grp{n}-grp{n+1}
      "exhaust:{mem_id}-r1/r2"       — Exhausts do mc
      "pressure_line_group:{n}"      — gen-pl-grp{n+1}
      "signal_valve:{g*100+e}"       — gen-sig-*
      "exhaust:sig-{sig_id}"         — Exhaust dedicado de cada sig
      "exhaust:btn-R"                — Exhaust dedicado do botão
      "step_module:{i}"
      "relay_coil:{i}"
      "relay_switch:{i}"
      "solenoid_coil:{id}"
      "voltage_source"
      "ground"
    """
    cfg = _load_config()
    rows = cfg["rows"]
    cols = cfg["columns"]
    gap  = cfg.get("anchor_child_gap", 20)  # espaçamento vertical entre anchor pai e filho

    cyl_first_x    = cols["cylinder_first_x"]
    cyl_group_w    = cols["cylinder_group_width"]
    pl_grp_x       = cols["pl_grp_x"]
    memory_x       = cols["memory_x"]
    btn_offset_x   = cols["btn_offset_x"]
    ps_offset_x    = cols["ps_offset_x"]
    step_mod_w     = cols["step_module_width"]

    # ── Passo 1: mapear letter → coluna x ────────────────────────────────────
    cyl_col: dict[str, float] = {}
    for node in data["nodes"]:
        role: str = node.get("_role", "")
        if role.startswith("cylinder:"):
            letter = role.split(":", 1)[1]
            if letter not in cyl_col:
                idx = len(cyl_col)
                cyl_col[letter] = cyl_first_x + idx * cyl_group_w

    # ── Passo 2: construir mapa id → posição para nós já posicionados ─────────
    # Preenchido na fase 1 e consultado na fase 2.
    node_pos: dict[str, tuple[float, float]] = {}   # id → (x, y)
    node_type_map: dict[str, str] = {}              # id → type string (ex: "Valve_4_2_Ways")

    for node in data["nodes"]:
        node_type_map[node["id"]] = node["type"]

    # ── Passo 3: construir mapa de conexões ───────────────────────────────────
    # Para cada nó filho (Exhaust / PS), queremos saber: a qual anchor de qual
    # nó pai ele está conectado?
    # conn = { source: {node, anchor}, target: {node, anchor} }
    # O filho (Exhaust/PS) pode ser source ou target.
    child_parent: dict[str, tuple[str, str]] = {}  # child_id → (parent_id, parent_anchor)
    sig_to_v42_pilot: dict[str, tuple[str, str]] = {}  # sig_id → (v42_id, 'PL'|'PR')
    mc_to_pl: dict[str, str] = {}                        # mc_id → pl_id alimentada por mc.A

    for conn in data.get("connections", []):
        src_id  = conn["source"]["node"]
        src_anc = conn["source"]["anchor"]
        tgt_id  = conn["target"]["node"]
        tgt_anc = conn["target"]["anchor"]

        # Descobre qual dos dois é o filho (Exhaust ou PS)
        for child_id, parent_id, parent_anc in [
            (src_id, tgt_id, tgt_anc),
            (tgt_id, src_id, src_anc),
        ]:
            if node_type_map.get(child_id) in _CHILD_CONNECT_ANCHOR:
                # Só registra se ainda não foi atribuído
                if child_id not in child_parent:
                    child_parent[child_id] = (parent_id, parent_anc)

        # Mapear sig_valve → v42 pilot: sig.A → v42.PL ou v42.PR
        if (node_type_map.get(src_id) == "Valve_3_2_Ways" and src_anc == "A" and
                node_type_map.get(tgt_id) == "Valve_4_2_Ways" and tgt_anc in ("PL", "PR")):
            sig_to_v42_pilot[src_id] = (tgt_id, tgt_anc)

        # Mapear memory → pl-grp alimentada por mc.A (usada para centralizar mc)
        if (node_type_map.get(src_id) == "Valve_5_2_Ways" and src_anc == "A" and
                node_type_map.get(tgt_id) == "PressureLine"):
            mc_to_pl[src_id] = tgt_id

    # ── Fase 1: posicionar nós primários ─────────────────────────────────────
    deferred: list[dict] = []     # Exhaust / PS → posicionados na fase 2
    deferred_mc: list[dict] = []  # Valve_5_2_Ways → posicionados na fase 2.5

    for node in data["nodes"]:
        role: str = node.get("_role", "")
        ntype = node["type"]

        if not role:
            node.pop("_role", None)
            continue

        # Exhaust e PressureSource com pai conhecido → diferir para fase 2
        if ntype in _CHILD_CONNECT_ANCHOR and node["id"] in child_parent:
            deferred.append(node)
            continue

        x, y = 0.0, 0.0  # fallback

        # ── Fonte principal ──────────────────────────────────────────────────
        if role == "pressure_source":
            x = memory_x + ps_offset_x
            y = rows["infra"]

        elif role == "pressure_line_main":
            x = 0.0
            y = rows["infra"]

        # ── Botão ────────────────────────────────────────────────────────────
        elif role == "button":
            x = memory_x + btn_offset_x
            y = rows["button"]

        elif role == "and_start":
            x = cols["infra_and_offset_x"]
            y = rows["infra"]

        # ── Cilindros ────────────────────────────────────────────────────────
        elif role.startswith("cylinder:"):
            letter = role.split(":", 1)[1]
            x = cyl_col.get(letter, 0.0)
            y = rows["cylinder"]

        # ── Válvulas 4/2 ─────────────────────────────────────────────────────
        # Alinhada pelo ponto médio entre seus anchors A e B com o ponto
        # médio entre os anchors A e B do cilindro correspondente.
        #   cyl mid = (18.04 + 408.82) / 2 = 213.43  (width=498, A=18/497, B=408/497)
        #   v42 mid = (191   + 256   ) / 2 = 223.50  (width=300, A=191/300, B=256/300)
        #   offset  = 213.43 - 223.50       = -10.07
        elif role.startswith("main_valve:"):
            letter = role.split(":", 1)[1]
            x = cyl_col.get(letter, 0.0) + cols.get("v42_align_offset_x", -10)
            y = rows["main_valve"]

        # ── Memórias 5/2 ─────────────────────────────────────────────────────
        # Diferido para fase 2.5 — precisa da PressureLine já posicionada.
        elif role.startswith("memory:"):
            deferred_mc.append(node)
            continue

        # ── Linhas de pressão de grupo ────────────────────────────────────────
        elif role.startswith("pressure_line_group:"):
            n = int(role.split(":", 1)[1])
            x = pl_grp_x
            y = rows["pl_grp_base"] + n * rows["pl_grp_gap"]

        # ── Válvulas de sinalização ───────────────────────────────────────────
        # Se a sig está ligada diretamente ao pilot de uma v42 (sig.A → v42.PL/PR),
        # posiciona ela alinhada ao pilot + offset lateral configurável.
        #
        #   PL (esquerdo):  v42.PL está em v42.x - 100 (local x=-100)
        #     sig.A está em sig.x + 254 (local)
        #     → sig.x = v42.x + PL_x - sig_A_x + offset_esquerda
        #             = v42.x - 100 - 254 + offset_PL
        #   PR (direito):   v42.PR está em v42.x + 400 (local x=400)
        #     → sig.x = v42.x + 400 - 254 + offset_PR
        #
        # offset_PL e offset_PR estão em layout_config.json como
        # "sig_pilot_offset_PL" e "sig_pilot_offset_PR" (ajuste fino visual).
        elif role.startswith("signal_valve:"):
            code  = int(role.split(":", 1)[1])
            g_idx = code // 100
            e_idx = code % 100
            nid = node["id"]

            if nid in sig_to_v42_pilot:
                v42_id, pilot_anc = sig_to_v42_pilot[nid]
                v42_pos = node_pos.get(v42_id)
                if v42_pos is not None:
                    v42_x_pos = v42_pos[0]
                    pl_local_x, pl_local_y = _ANCHOR_LOCAL["Valve_4_2_Ways"][pilot_anc]  # PL=-100 ou PR=400
                    sig_A_local_x = _ANCHOR_LOCAL["Valve_3_2_Ways"]["A"][0]              # 254
                    if pilot_anc == "PL":
                        offset = cols.get("sig_pilot_offset_PL", -50)
                    else:
                        offset = cols.get("sig_pilot_offset_PR", 50)
                    x = v42_x_pos + pl_local_x - sig_A_local_x + offset
                    y = rows["main_valve"] + cols.get("sig_pilot_offset_y", 0)
                else:
                    # v42 ainda não posicionada (não deveria acontecer)
                    x = cyl_first_x + e_idx * (cyl_group_w // max(1, 2))
                    y = rows["v42_ps_exh"] - 10
            else:
                # sig não conecta a pilot de v42 → posição legacy
                if g_idx == 0:
                    x = cyl_first_x + e_idx * (cyl_group_w // max(1, 2))
                    y = rows["v42_ps_exh"] - 10
                else:
                    x = memory_x + (e_idx - 1) * (cyl_group_w // 2) + 330
                    y = rows["memory"] + g_idx * 185

        # ── Elétrico (legacy) ─────────────────────────────────────────────────
        elif role.startswith("step_module:"):
            i = int(role.split(":", 1)[1])
            x = i * step_mod_w
            y = rows["steps"]

        elif role.startswith("relay_coil:"):
            i = int(role.split(":", 1)[1])
            x = i * step_mod_w
            y = rows["steps"]

        elif role.startswith("relay_switch:"):
            i = int(role.split(":", 1)[1])
            x = int((i + cols["relay_switch_half_offset"]) * step_mod_w)
            y = rows["steps"]

        elif role.startswith("solenoid_coil:"):
            cyl_x = node.pop("_cyl_col_x", 0.0)
            x = cyl_x
            y = rows["electric"]

        elif role == "voltage_source":
            x = 0.0
            y = rows["electric"]

        elif role == "ground":
            x = cols.get("ground_dx", 100)
            y = rows["electric"]

        node["position"] = {"x": x, "y": y}
        node_pos[node["id"]] = (x, y)
        node.pop("_role", None)

    # ── Fase 2: posicionar Exhaust / PressureSource ancorados ao pai ──────────
    #
    # Se o pai ainda não foi posicionado (ex: Exhaust de mc, que é diferido para
    # fase 2.5), o nó vai para deferred_late e é processado após a fase 2.5.

    def _position_child(node: dict) -> bool:
        """Tenta posicionar um filho. Retorna True se conseguiu, False se o pai
        ainda não está em node_pos."""
        nid   = node["id"]
        ntype = node["type"]

        parent_id, parent_anc = child_parent[nid]
        if parent_id not in node_pos:
            return False  # pai ainda não posicionado

        parent_ntype = node_type_map.get(parent_id, "")
        px, py = node_pos[parent_id]

        parent_anc_local = _anchor_local(parent_ntype, parent_anc)
        if parent_anc_local is None:
            x, y = px, py + 100
        else:
            anc_x = px + parent_anc_local[0]
            anc_y = py + parent_anc_local[1]
            child_anc_name  = _CHILD_CONNECT_ANCHOR[ntype]
            child_anc_local = _anchor_local(ntype, child_anc_name)
            child_dx = child_anc_local[0] if child_anc_local else 0.0
            x = anc_x - child_dx
            y = anc_y + gap

        node["position"] = {"x": x, "y": y}
        node_pos[nid] = (x, y)
        node.pop("_role", None)
        return True

    deferred_late: list[dict] = []
    for node in deferred:
        if not _position_child(node):
            deferred_late.append(node)


    # ── Fase 2.5: posicionar memórias 5/2 centradas sobre a PressureLine ────────
    #
    # Cada memória é centralizada pela PL que ela alimenta via mc.A → pl.
    # Centro da PL: pl.x + PL_PIX_W/2 + (n_anchors - 1) * PL_SPACING / 2
    # Centro do sprite v52: 225 (width=450 / 2)
    # → mc.x = pl_center - 225
    #
    # O encadeamento mc[n].B → mc[n-1].P é tratado pela fase 3 (anchor mais próximo).

    MC_PL_PIX_W   = 71
    MC_PL_SPACING = 120
    V52_SPRITE_CX = 225  # 450 / 2

    pl_node_by_id = {n["id"]: n for n in data["nodes"] if n["type"] == "PressureLine"}

    # V52 anchor local x — usados para alinhar o encadeamento mc[n].B → mc[n-1].P
    # B_x=405, P_x=338 → mc[n].x = mc[n-1].x + (P_x - B_x) = mc[n-1].x - 67
    V52_B_X = 450 * 405/450   # 405.0
    V52_P_X = 450 * 338/450   # 338.0
    MC_CHAIN_OFFSET = V52_P_X - V52_B_X  # -67.0

    # Ordenar deferred_mc por n_idx para processar mc[0] antes de mc[1], etc.
    deferred_mc.sort(key=lambda nd: int(nd.get("_role","memory:0").split(":",1)[1]))

    mc_x_by_idx: dict[int, float] = {}  # n_idx → x calculado

    for node in deferred_mc:
        nid   = node["id"]
        role  = node.get("_role", "")
        n_idx = int(role.split(":", 1)[1]) if role.startswith("memory:") else 0

        if n_idx == 0:
            # mc[0]: centralizado sobre a PL que alimenta
            pl_id = mc_to_pl.get(nid)
            if pl_id and pl_id in node_pos and pl_id in pl_node_by_id:
                pl_node = pl_node_by_id[pl_id]
                n_anch  = len(pl_node["properties"]["anchors"])
                pl_x    = node_pos[pl_id][0]
                pl_center = pl_x + MC_PL_PIX_W / 2 + (n_anch - 1) * MC_PL_SPACING / 2
                x = pl_center - V52_SPRITE_CX
            else:
                x = memory_x  # fallback
        else:
            # mc[n]: x alinhado para que mc[n].B fique sobre mc[n-1].P
            prev_x = mc_x_by_idx.get(n_idx - 1, memory_x + n_idx * cyl_group_w)
            x = prev_x + MC_CHAIN_OFFSET

        mc_x_by_idx[n_idx] = x
        y = rows["memory"] + n_idx * cols.get("memory_gap_y", 300)
        node["position"] = {"x": x, "y": y}
        node_pos[nid] = (x, y)
        node.pop("_role", None)

    # ── Fase 2.5 late: posicionar filhos cujo pai era uma memória ───────────────
    for node in deferred_late:
        _position_child(node)  # pai já está em node_pos agora

    # ── Fase 3: reatribuir anchors das PressureLines pelo vizinho mais próximo ──
    #
    # Para cada conexão pl.Xi → nó_destino, calcula a posição X do anchor do
    # destino em cena e encontra o Xi da PressureLine com menor distância
    # horizontal, reescrevendo source.anchor.
    #
    # Analogamente, para conexões nó_origem → pl.Xi (ex: mc.A → pl), faz o
    # mesmo pelo lado target.
    #
    # Fórmula de posição local do anchor Xi da PressureLine:
    #   x_local(Xi) = PL_PIX_W / 2 + (i - 1) * PL_SPACING
    # onde PL_PIX_W = 71 (terminal sprite) e PL_SPACING = 120.

    PL_PIX_W   = 71    # largura do terminal sprite (pressure_line_terminal.png)
    PL_SPACING = 120   # espaçamento entre anchors (expandable_item.py)

    def pl_anchor_scene_x(pl_id: str, anchor_name: str) -> float | None:
        """Retorna a posição X em cena do anchor Xi de uma PressureLine."""
        pl_x, _ = node_pos.get(pl_id, (None, None))
        if pl_x is None:
            return None
        idx = int(anchor_name[1:])  # "X3" → 3
        return pl_x + PL_PIX_W / 2 + (idx - 1) * PL_SPACING

    def nearest_pl_anchor(pl_node: dict, target_scene_x: float) -> str:
        """Retorna o nome do anchor Xi mais próximo de target_scene_x."""
        anchors = pl_node["properties"]["anchors"]
        pl_x, _ = node_pos[pl_node["id"]]
        best_name = anchors[0]
        best_dist = float("inf")
        for name in anchors:
            idx = int(name[1:])
            ax = pl_x + PL_PIX_W / 2 + (idx - 1) * PL_SPACING
            d  = abs(ax - target_scene_x)
            if d < best_dist:
                best_dist = d
                best_name = name
        return best_name

    def anchor_scene_x(node_id: str, anchor_name: str) -> float | None:
        """Posição X em cena de um anchor de qualquer nó já posicionado."""
        ntype = node_type_map.get(node_id, "")
        npos  = node_pos.get(node_id)
        if npos is None:
            return None
        local = _anchor_local(ntype, anchor_name)
        if local is None:
            return npos[0]  # fallback: x do nó
        return npos[0] + local[0]

    pl_node_map = {n["id"]: n for n in data["nodes"] if n["type"] == "PressureLine"}

    for conn in data.get("connections", []):
        src_id  = conn["source"]["node"]
        tgt_id  = conn["target"]["node"]
        src_anc = conn["source"]["anchor"]
        tgt_anc = conn["target"]["anchor"]

        # caso 1: PressureLine → qualquer nó
        if src_id in pl_node_map and src_anc.startswith("X"):
            tgt_x = anchor_scene_x(tgt_id, tgt_anc)
            if tgt_x is not None:
                conn["source"]["anchor"] = nearest_pl_anchor(pl_node_map[src_id], tgt_x)

        # caso 2: qualquer nó → PressureLine
        elif tgt_id in pl_node_map and tgt_anc.startswith("X"):
            src_x = anchor_scene_x(src_id, src_anc)
            if src_x is not None:
                conn["target"]["anchor"] = nearest_pl_anchor(pl_node_map[tgt_id], src_x)

    return data