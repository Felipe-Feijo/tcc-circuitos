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
    "DoubleActingCylinder": {
        # Sprite 498×193; anchors na base (y = height = 193)
        "A": (498 * 18/497,  193),   # ≈ (18.04, 193)
        "B": (498 * 408/497, 193),   # ≈ (408.82, 193)
    },
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
    sig_to_mc_pilot:  dict[str, tuple[str, str]] = {}  # sig_id → (mc_id, 'PL'|'PR')
    sig_to_btn:       set[str]                   = set()  # sig_ids que ligam .A → btn.P
    sig_to_sig:       dict[str, str]             = {}  # sig_id → sig_id_destino (.A→sig.P)
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

        # Mapear sig → mc pilot: sig.A → mc.PL ou mc.PR
        # (excluir btn: btn.A → mc.PL é conexão de botão, não de sig de transição)
        if (node_type_map.get(src_id) == "Valve_3_2_Ways" and src_anc == "A" and
                node_type_map.get(tgt_id) == "Valve_5_2_Ways" and tgt_anc in ("PL", "PR")):
            # Só registrar se src é uma sig (começa com gen-sig), não o btn
            src_role = next((n["_role"] for n in data.get("nodes",[]) if n["id"]==src_id), "")
            if src_role.startswith("signal_valve:"):
                sig_to_mc_pilot[src_id] = (tgt_id, tgt_anc)

        # Mapear sig → btn (sig.A → btn.P) e encadeamento sig→sig
        # sig.A → btn.P: src é sig (role=signal_valve:*), tgt é btn (role=button)
        if (node_type_map.get(src_id) == "Valve_3_2_Ways" and src_anc == "A" and
                node_type_map.get(tgt_id) == "Valve_3_2_Ways" and tgt_anc == "P"):
            src_role = next((n["_role"] for n in data.get("nodes",[]) if n["id"]==src_id), "")
            tgt_role = next((n["_role"] for n in data.get("nodes",[]) if n["id"]==tgt_id), "")
            if src_role.startswith("signal_valve:"):
                if tgt_role == "button":
                    sig_to_btn.add(src_id)
                else:
                    sig_to_sig[src_id] = tgt_id

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
        # Diferido para fase 2.5 — precisa do mc[0] já posicionado.
        elif role == "button":
            deferred_mc.append(node)
            continue

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
        # Três casos baseados no destino de sig.A:
        #
        # 1) sig.A → v42.PL/PR: posiciona ao lado do pilot da v42
        #    sig.x = v42.x + pilot_local_x - sig.A.local_x + offset_PL/PR
        #    sig.y = rows["main_valve"] + sig_pilot_offset_y
        #
        # 2) sig.A → mc.PL/PR: posiciona à direita da região das memórias
        #    sig.x = cyl_last_x  (alinhada ao último cilindro)
        #    sig.y = média entre o mc acionado e o mc abaixo dele
        #            ou mc[0].y + memory_gap * fator para o último mc
        #    Diferido para fase 2.5 — precisa dos mc já posicionados.
        #
        # 3) sig.A → btn.P: posiciona abaixo do btn
        #    sig.x = btn.x  (mesma coluna)
        #    sig.y = btn.y + btn_height + offset
        #    Diferido para fase 2.5 — precisa do btn já posicionado.
        elif role.startswith("signal_valve:"):
            nid = node["id"]

            if nid in sig_to_v42_pilot:
                # Caso 1: sig → v42.pilot
                v42_id, pilot_anc = sig_to_v42_pilot[nid]
                v42_pos = node_pos.get(v42_id)
                if v42_pos is not None:
                    v42_x_pos = v42_pos[0]
                    pl_local_x = _ANCHOR_LOCAL["Valve_4_2_Ways"][pilot_anc][0]
                    sig_A_local_x = _ANCHOR_LOCAL["Valve_3_2_Ways"]["A"][0]
                    if pilot_anc == "PL":
                        offset = cols.get("sig_pilot_offset_PL", -50)
                    else:
                        offset = cols.get("sig_pilot_offset_PR", 50)
                    x = v42_x_pos + pl_local_x - sig_A_local_x + offset
                    y = rows["main_valve"] + cols.get("sig_pilot_offset_y", 0)
                else:
                    x = cyl_first_x
                    y = rows["main_valve"] + cols.get("sig_pilot_offset_y", 0)
            elif nid in sig_to_mc_pilot or nid in sig_to_btn or nid in sig_to_sig:
                # Casos 2 e 3: diferir para fase 2.5 (precisa de mc/btn posicionados)
                deferred_mc.append(node)
                continue
            else:
                # Fallback: posição junto ao pilot da primeira v42
                x = cyl_first_x
                y = rows["main_valve"] + cols.get("sig_pilot_offset_y", 0)

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

    # Separar deferred_mc em: memórias reais vs btn/sigs (dependem das mc)
    real_mc_nodes = [n for n in deferred_mc if n.get("_role", "").startswith("memory:")]
    btn_sig_nodes = [n for n in deferred_mc if not n.get("_role", "").startswith("memory:")]

    # Ordenar mc por n_idx para processar mc[0] antes de mc[1], etc.
    real_mc_nodes.sort(key=lambda nd: int(nd.get("_role","memory:0").split(":",1)[1]))

    mc_x_by_idx: dict[int, float] = {}  # n_idx → x calculado
    mc_y_by_idx: dict[int, float] = {}  # n_idx → y calculado

    n_mc_total = len(real_mc_nodes)

    # ── Calcular Y das memórias dinamicamente a partir do espaçamento das PLs ──
    #
    # Ratios derivados do gabarito (A+A-B+B-):
    #   mc[n_mc-1].y = pl_last.y + 1.370 * pl_grp_gap
    #   gap_mc       = 2.064 * pl_grp_gap  (entre memórias consecutivas)
    #
    # pl_last.y = pl_grp_base + (n_pl - 1) * pl_grp_gap
    # n_pl = n_mc_total + 1  (há sempre uma PL a mais que memórias)
    pl_grp_gap   = rows["pl_grp_gap"]
    pl_grp_base  = rows["pl_grp_base"]
    n_pl         = n_mc_total + 1
    pl_last_y    = pl_grp_base + (n_pl - 1) * pl_grp_gap
    mc_top_y     = pl_last_y + round(1.370 * pl_grp_gap)
    gap_mc       = round(2.064 * pl_grp_gap)

    # ── Posicionar mc do mais alto (n_mc-1) para o mais baixo (0) ─────────────
    #
    # X: mc[n_mc-1].x = cyl_first_x + CYL_WIDTH - MC_WIDTH/2 - 15  (do gabarito)
    #    mc[n].x = mc[n+1].x + |chain_offset| + PL_PIX_W = mc[n+1].x + 138
    CYL_WIDTH  = 498   # largura do sprite DoubleActingCylinder
    MC_WIDTH   = 450   # largura do sprite Valve_5_2_Ways
    MC_X_STEP  = int(abs(MC_CHAIN_OFFSET)) + MC_PL_PIX_W  # 67 + 71 = 138
    mc_top_x   = cyl_first_x + CYL_WIDTH - MC_WIDTH / 2 - 15

    for node in reversed(real_mc_nodes):  # do mais alto (n_mc-1) para o mais baixo (0)
        nid   = node["id"]
        role  = node.get("_role", "")
        n_idx = int(role.split(":", 1)[1]) if role.startswith("memory:") else 0

        # X: mc[n_mc-1] como âncora; mc[n] = mc[n+1].x + MC_X_STEP
        steps_from_top = n_mc_total - 1 - n_idx  # 0 para o mais alto, 1, 2...
        x = mc_top_x + steps_from_top * MC_X_STEP

        # Y: mc[n_mc-1] no mc_top_y; mc[n] = mc[n+1].y + gap_mc
        y = mc_top_y + steps_from_top * gap_mc

        mc_x_by_idx[n_idx] = x
        mc_y_by_idx[n_idx] = y
        node["position"] = {"x": x, "y": y}
        node_pos[nid] = (x, y)
        node.pop("_role", None)

    # ── Fase 2.5 late: posicionar filhos cujo pai era uma memória ───────────────
    for node in deferred_late:
        _position_child(node)  # pai já está em node_pos agora

    # ── Fase 2.6: posicionar btn e sigs de transição (dependem dos mc) ───────────
    #
    # BTN:
    #   btn.x = mc[0].x + btn_offset_x
    #   btn.y = mc[0].y + gap_mc / 2
    #
    # Sigs que → mc.PR (transição de grupo g):
    #   sig.x = cyl_last_x  (coluna do último cilindro)
    #   sig aciona mc[n_mc-1-g].PR
    #   Se há mc abaixo: sig.y = (mc[n_mc-1-g].y + mc[n_mc-2-g].y) / 2
    #   Se é o mc mais baixo (idx=0): sig.y = mc[0].y + gap_mc / 2
    #
    # Sigs que → btn.P (fecha ciclo):
    #   sig.x = btn.x
    #   sig.y = btn.y + btn_height + sig_below_btn_offset
    #   btn_height = 180 (sprite Valve_3_2_Ways)

    cyl_last_x = cyl_first_x + (len(cyl_col) - 1) * cyl_group_w if cyl_col else cyl_first_x
    sig_below_btn_offset = cols.get("sig_below_btn_offset", 93)
    btn_height = 180

    # Posicionar btn primeiro
    btn_node = next((n for n in btn_sig_nodes if n.get("_role") == "button"), None)
    btn_x, btn_y = 0.0, 0.0
    if btn_node is not None:
        mc0_x = mc_x_by_idx.get(0, memory_x)
        mc0_y = mc_y_by_idx.get(0, pl_last_y + round(1.370 * pl_grp_gap))
        btn_x = mc0_x + btn_offset_x
        # btn.y = mc[0].y + 0.974 * pl_grp_gap  (ratio do gabarito: 151/155)
        btn_y = mc0_y + round(0.974 * pl_grp_gap)
        btn_node["position"] = {"x": btn_x, "y": btn_y}
        node_pos[btn_node["id"]] = (btn_x, btn_y)
        btn_node.pop("_role", None)

    # Posicionar sigs de transição e sigs finais
    for node in btn_sig_nodes:
        nid  = node["id"]
        role = node.get("_role", "")
        if role == "button":
            continue  # já posicionado

        if nid in sig_to_mc_pilot:
            # Sig → mc.PR: x alinhado ao anchor PR da própria mc que ela pilota
            # sig.A.x = mc.x + V52_PR_local_x + sig_pilot_offset_PR
            # sig.x   = mc.x + V52_PR_local_x - sig.A.local_x + sig_pilot_offset_PR
            #         = mc.x + 405 - 254 + offset_PR
            sig_pr_off = cols.get("sig_pilot_offset_PR", 59)
            mc_id, _ = sig_to_mc_pilot[nid]
            mc_pos = node_pos.get(mc_id)
            V52_PR_local_x = _ANCHOR_LOCAL["Valve_5_2_Ways"]["PR"][0]  # 405
            SIG_A_local_x  = _ANCHOR_LOCAL["Valve_3_2_Ways"]["A"][0]   # 254
            if mc_pos is not None:
                sig_x = mc_pos[0] + V52_PR_local_x - SIG_A_local_x + sig_pr_off
            else:
                v42_align  = cols.get("v42_align_offset_x", 65)
                v42_last_x = cyl_last_x + v42_align
                sig_x = v42_last_x + 256 - sig_pr_off - 254  # fallback antigo

            if mc_pos is not None:
                mc_idx = next((i for i, pos in mc_y_by_idx.items()
                               if abs(pos - mc_pos[1]) < 1), None)
                # Y: média entre este mc e o mc abaixo (idx-1), ou mc[0]+gap/2
                if mc_idx is not None and mc_idx > 0:
                    y_above = mc_y_by_idx[mc_idx]
                    y_below = mc_y_by_idx[mc_idx - 1]
                    sig_y = (y_above + y_below) / 2
                else:
                    # sig aciona mc[0] (o mais baixo): fica logo abaixo do btn
                    sig_y = btn_y + 23 if btn_y > 0 else mc_y_by_idx.get(0, mc_top_y + gap_mc) + round(0.974 * pl_grp_gap) + 23
            else:
                sig_y = mc_top_y + gap_mc + round(0.974 * pl_grp_gap) + 23
            node["position"] = {"x": sig_x, "y": sig_y}
            node_pos[nid] = (sig_x, sig_y)
            node.pop("_role", None)

        elif nid in sig_to_btn:
            # Sig → btn.P: posicionar abaixo do btn, x alinhado a btn.x
            # (sig.A.x ≈ btn.P.x = btn.x + 254; sig.x = btn.x)
            node["position"] = {"x": btn_x, "y": btn_y + btn_height + sig_below_btn_offset}
            node_pos[nid] = (btn_x, btn_y + btn_height + sig_below_btn_offset)
            node.pop("_role", None)

        elif nid in sig_to_sig:
            # Sig → outra sig (encadeamento intra-grupo): mesmo tratamento que sig→mc
            # por ora usa cyl_last_x com y da memória central
            sig_y = mc_y_by_idx.get(0, rows["memory"]) + gap_mc / 2
            node["position"] = {"x": cyl_last_x, "y": sig_y}
            node_pos[nid] = (cyl_last_x, sig_y)
            node.pop("_role", None)

        else:
            node.pop("_role", None)

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
        idx = int(anchor_name[1:])
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

    # ── Fase 2.7: reprocessar Exhausts/PS cujo pai foi posicionado na fase 2.6 ─
    # (sigs de transição e btn são posicionados na fase 2.6; seus exhausts
    #  ficaram em deferred_late sem pai no node_pos e precisam ser reatribuídos)
    for node in list(deferred_late):
        if node["id"] in node_pos:
            continue  # já posicionado
        if _position_child(node):
            deferred_late.remove(node)

    # ── Fase 2.8: centralizar cada PressureLine sobre seus componentes conectados ─
    #
    # Após todos os nós estarem posicionados, recalcula o x de cada PL para que
    # o centro da PL coincida com o centro do range de x dos componentes que
    # conectam a ela (pilots, sigs, mc anchors).
    # Fórmula: pl_x = (min_x + max_x) / 2 - pl_width / 2
    # onde pl_width = PL_PIX_W/2 + (n_anchors - 1) * PL_SPACING

    _pl_nodes_map = {n["id"]: n for n in data["nodes"] if n["type"] == "PressureLine"}

    # Coletar x de componentes conectados a cada PL
    _pl_connected_xs: dict[str, list[float]] = {pl_id: [] for pl_id in _pl_nodes_map}

    for conn in data.get("connections", []):
        src_id  = conn["source"]["node"]
        tgt_id  = conn["target"]["node"]
        src_anc = conn["source"]["anchor"]
        tgt_anc = conn["target"]["anchor"]

        for pl_id, other_id, other_anc in [
            (src_id, tgt_id, tgt_anc),
            (tgt_id, src_id, src_anc),
        ]:
            if pl_id not in _pl_nodes_map:
                continue
            ntype = node_type_map.get(other_id, "")
            npos  = node_pos.get(other_id)
            if npos is None:
                continue
            local = _anchor_local(ntype, other_anc)
            if local:
                _pl_connected_xs[pl_id].append(npos[0] + local[0])
            else:
                _pl_connected_xs[pl_id].append(npos[0])

    # Range global: min e max de todos os componentes conectados a qualquer PL
    all_xs = [x for xs in _pl_connected_xs.values() for x in xs]
    if all_xs:
        global_min_x = min(all_xs)
        global_max_x = max(all_xs)
        global_center = (global_min_x + global_max_x) / 2

        for pl_id, xs in _pl_connected_xs.items():
            if not xs:
                continue
            pl_node = _pl_nodes_map[pl_id]
            n_anchors = len(pl_node["properties"]["anchors"])
            pl_width  = PL_PIX_W / 2 + (n_anchors - 1) * PL_SPACING
            new_pl_x  = global_center - pl_width / 2
            pl_node["position"]["x"] = new_pl_x
            node_pos[pl_id] = (new_pl_x, node_pos[pl_id][1])

    def _anchor_scene_x_for_pl(pl_node: dict, anchor_name: str) -> float:
        """Posição X em cena de um anchor Xi de uma PressureLine."""
        pl_x = node_pos[pl_node["id"]][0]
        idx = int(anchor_name[1:])
        return pl_x + PL_PIX_W / 2 + (idx - 1) * PL_SPACING

    def nearest_pl_anchor_left_of(pl_node: dict, target_x: float) -> str:
        """
        Retorna o anchor Xi mais próximo de target_x à esquerda.
        Se não houver, retorna o mais à esquerda.
        """
        anchors = pl_node["properties"]["anchors"]
        left_anchors = [(abs(_anchor_scene_x_for_pl(pl_node, n) - target_x), n)
                        for n in anchors if _anchor_scene_x_for_pl(pl_node, n) < target_x]
        if left_anchors:
            return min(left_anchors)[1]
        anchors_with_x = [(int(n[1:]), n) for n in anchors]
        anchors_with_x.sort()
        return anchors_with_x[0][1]

    def nearest_pl_anchor_right_of(pl_node: dict, target_x: float) -> str:
        """
        Retorna o anchor Xi mais próximo de target_x à direita.
        Se não houver, retorna o mais à direita.
        """
        anchors = pl_node["properties"]["anchors"]
        right_anchors = [(abs(_anchor_scene_x_for_pl(pl_node, n) - target_x), n)
                         for n in anchors if _anchor_scene_x_for_pl(pl_node, n) > target_x]
        if right_anchors:
            return min(right_anchors)[1]
        anchors_with_x = [(int(n[1:]), n) for n in anchors]
        anchors_with_x.sort(reverse=True)
        return anchors_with_x[0][1]

    def best_pl_anchor_for_u_shape(pl_node: dict, sig_P_x: float,
                                    min_sep: float = 100.0) -> str:
        """
        Para conexões PL→sig.P onde sig está abaixo da PL (U-shape necessário),
        escolhe o anchor da PL que minimiza o comprimento total da rota em U.
        
        A rota tem forma de U invertido: desce da PL, vai horizontal, desce até sig.P.
        O comprimento horizontal do U é |anchor_x - sig_P_x|.
        
        Critério: preferir anchor que esteja do mesmo lado que sig.P (dx com sinal
        consistente) e com |dx| >= min_sep para caber o desvio lateral.
        Entre os candidatos válidos, escolher o de menor |dx| (rota mais curta).
        
        Exemplo corrigido: se sig.P está à DIREITA do anchor X1 (dx > 0),
        prefere um anchor à esquerda de sig.P (também dx < 0) — NÃO X1 que está
        ainda mais à esquerda. Isso evita a rota ir na direção oposta e voltar.
        """
        anchors = pl_node["properties"]["anchors"]
        
        # Separar anchors por lado em relação a sig_P_x
        left_anchors  = []  # anchor à ESQUERDA de sig.P (dx < 0 → PL sai pela esquerda)
        right_anchors = []  # anchor à DIREITA de sig.P  (dx > 0)
        
        for name in anchors:
            ax = _anchor_scene_x_for_pl(pl_node, name)
            dx = ax - sig_P_x
            if abs(dx) >= min_sep:
                if dx < 0:
                    left_anchors.append((abs(dx), name))
                else:
                    right_anchors.append((abs(dx), name))
        
        # Preferir o lado com menor deslocamento total (rota mais curta)
        # Entre candidatos do mesmo lado, pegar o mais próximo (menor |dx|)
        left_anchors.sort()
        right_anchors.sort()
        
        candidates = []
        if left_anchors:
            candidates.append(left_anchors[0])   # melhor da esquerda
        if right_anchors:
            candidates.append(right_anchors[0])  # melhor da direita
        
        if candidates:
            candidates.sort()  # escolher o de menor |dx| total
            return candidates[0][1]
        
        # Fallback: nenhum satisfaz min_sep — usar o mais afastado disponível
        all_anchors = [(abs(_anchor_scene_x_for_pl(pl_node, n) - sig_P_x), n) for n in anchors]
        all_anchors.sort(reverse=True)
        return all_anchors[0][1]

    def _best_pl_anchor_clear_column(pl_node: dict, target_x: float,
                                       pl_y: float, sig_y: float) -> str:
        """
        Escolhe o anchor da PL cuja coluna vertical está mais livre de obstáculos
        entre pl_y e sig_y. Se nenhuma estiver livre, usa o mais próximo de target_x.
        Verifica apenas os blocos conhecidos (node_pos + SPRITE_SIZES + MH).
        """
        from circuit_generator.astar_router import SPRITE_SIZES as _SS
        MH = 80
        anchors = pl_node["properties"]["anchors"]

        # Coletar blocos que interceptam a faixa vertical [pl_y, sig_y]
        blocking_ranges = []  # lista de (x_min, x_max) de blocos no caminho
        for nid2, npos2 in node_pos.items():
            ntype2 = node_type_map.get(nid2, "")
            if ntype2 in ("PressureLine", "Exhaust", "PressureSource"):
                continue
            w2, h2 = _SS.get(ntype2, (0, 0))
            if w2 == 0:
                continue
            margin2 = MH if ntype2 in ("Valve_4_2_Ways","Valve_5_2_Ways","Valve_3_2_Ways") else 30
            bx2 = npos2[0] - margin2
            bx2_end = npos2[0] + w2 + margin2
            by2 = npos2[1]
            by2_end = npos2[1] + h2
            # Intercepta a faixa vertical?
            if by2_end > pl_y and by2 < sig_y:
                blocking_ranges.append((bx2, bx2_end))

        def col_is_clear(ax: float) -> bool:
            for bx2, bx2_end in blocking_ranges:
                if bx2 <= ax <= bx2_end:
                    return False
            return True

        # Candidatos: livre primeiro, depois mais próximo de target_x
        # Também exclui anchors já usados por outra conexão no mesmo x
        candidates = []
        for name in anchors:
            pl_x = node_pos[pl_node["id"]][0]
            idx = int(name[1:])
            ax = pl_x + PL_PIX_W / 2 + (idx - 1) * PL_SPACING
            clear = col_is_clear(ax)
            taken = round(ax) in _pl_anchor_used
            candidates.append((not clear, taken, abs(ax - target_x), name))

        candidates.sort(key=lambda c: (c[0], c[1], c[2]))  # livre, não-tomado, mais próximo
        chosen = candidates[0][3]
        # Registrar no _pl_anchor_used
        chosen_ax = node_pos[pl_node["id"]][0] + PL_PIX_W / 2 + (int(chosen[1:]) - 1) * PL_SPACING
        _pl_anchor_used[round(chosen_ax)] = (target_x, 0.0)
        return chosen

    _pl_anchor_used: dict[int, tuple[str, float]] = {}  # round(x) → (owner_id, owner_y)
    # Mapa de conn por owner_id para poder reatribuir o anchor do ocupante anterior
    _conn_by_owner: dict[str, object] = {}  # owner_id → conn (para reatribuir anchor)

    def _resolve_anchor_conflict(pl_node: dict, anchor: str, owner: str,
                                  owner_y: float, conn_ref: object,
                                  anchor_side: str = "source") -> str:
        """
        Registra o anchor. Se já estiver em uso, o componente com MAIOR y
        move 1 posição em direção à extremidade (iterativamente até ficar livre).
        Direção: idx <= metade → recua (idx-1); idx > metade → avança (idx+1).
        anchor_side: 'source' ou 'target' — qual lado do conn_ref atualizar se
                     o ocupante anterior precisar ser movido.
        """
        anchors = pl_node["properties"]["anchors"]
        n = len(anchors)
        mid = n / 2

        def _next_anchor(current: str) -> str:
            idx = int(current[1:])
            new_idx = (idx - 1) if idx <= mid else (idx + 1)
            new_idx = max(1, min(n, new_idx))
            return f"X{new_idx}"

        def _register(anc: str, oid: str, oy: float, cref: object):
            """Registra anchor; se conflito, move o de maior y."""
            ax = _anchor_scene_x_for_pl(pl_node, anc)
            key = round(ax)
            if key not in _pl_anchor_used:
                _pl_anchor_used[key] = (oid, oy)
                _conn_by_owner[oid] = (cref, anchor_side, pl_node)
                return anc
            # Conflito — quem tem maior y se move
            prev_id, prev_y = _pl_anchor_used[key]
            if oy >= prev_y:
                # novo owner tem maior y → ele se move
                moved = _next_anchor(anc)
                print(f"[layout] ⚠️  mesmo x={ax:.1f}: {oid} (y={oy:.0f}) conflita com "
                      f"{prev_id} (y={prev_y:.0f}), movendo {anc} → {moved}")
                return _register(moved, oid, oy, cref)
            else:
                # ocupante anterior tem maior y → ele se move, novo fica
                _pl_anchor_used[key] = (oid, oy)
                _conn_by_owner[oid] = (cref, anchor_side, pl_node)
                prev_conn, prev_side, prev_pl = _conn_by_owner.get(prev_id, (None, None, None))
                if prev_conn is not None:
                    moved = _next_anchor(anc)
                    print(f"[layout] ⚠️  mesmo x={ax:.1f}: {prev_id} (y={prev_y:.0f}) conflita com "
                          f"{oid} (y={oy:.0f}), movendo {anc} → {moved} (ocupante anterior)")
                    new_anc = _register(moved, prev_id, prev_y, prev_conn)
                    if prev_side == "source":
                        prev_conn["source"]["anchor"] = new_anc
                    else:
                        prev_conn["target"]["anchor"] = new_anc
                return anc

        return _register(anchor, owner, owner_y, conn_ref)

    for conn in data.get("connections", []):
        src_id  = conn["source"]["node"]
        tgt_id  = conn["target"]["node"]
        src_anc = conn["source"]["anchor"]
        tgt_anc = conn["target"]["anchor"]
        src_ntype_p3 = node_type_map.get(src_id, "")
        tgt_ntype_p3 = node_type_map.get(tgt_id, "")

        # caso 1: PressureLine → qualquer nó
        if src_id in pl_node_map and src_anc.startswith("X"):
            tgt_x = anchor_scene_x(tgt_id, tgt_anc)
            if tgt_x is not None:
                # Para PL→sig.P quando sig está ABAIXO da PL:
                # preferir o anchor cuja coluna vertical esteja livre de obstáculos
                # entre a PL e o destino. Se todas estiverem bloqueadas, usar a
                # mais próxima (o A* contorna).
                if (tgt_ntype_p3 == "Valve_3_2_Ways" and tgt_anc == "P"):
                    tgt_pos_n = node_pos.get(tgt_id)
                    pl_pos_n  = node_pos.get(src_id)
                    sig_P_y   = (tgt_pos_n[1] + 180) if tgt_pos_n else 0
                    pl_y      = pl_pos_n[1] if pl_pos_n else 0
                    if sig_P_y > pl_y:
                        conn["source"]["anchor"] = _best_pl_anchor_clear_column(
                            pl_node_map[src_id], tgt_x, pl_y, sig_P_y)
                    elif sig_P_y < pl_y:
                        conn["source"]["anchor"] = _best_pl_anchor_clear_column(
                            pl_node_map[src_id], tgt_x, sig_P_y, pl_y)
                    else:
                        conn["source"]["anchor"] = nearest_pl_anchor(pl_node_map[src_id], tgt_x)
                elif tgt_anc == "PL":
                    # Pilot esquerdo: anchor com x MENOR que o pilot (vem pela esquerda)
                    conn["source"]["anchor"] = nearest_pl_anchor_left_of(pl_node_map[src_id], tgt_x)
                elif tgt_anc == "PR":
                    # Pilot direito: anchor com x MAIOR que o pilot (vem pela direita)
                    conn["source"]["anchor"] = nearest_pl_anchor_right_of(pl_node_map[src_id], tgt_x)
                else:
                    conn["source"]["anchor"] = nearest_pl_anchor(pl_node_map[src_id], tgt_x)

        # caso 2: qualquer nó → PressureLine
        elif tgt_id in pl_node_map and tgt_anc.startswith("X"):
            src_x = anchor_scene_x(src_id, src_anc)
            if src_x is not None:
                _PILOT_PL_OFFSET = 10
                if src_anc == "PL":
                    conn["target"]["anchor"] = nearest_pl_anchor_left_of(pl_node_map[tgt_id], src_x - _PILOT_PL_OFFSET)
                elif src_anc == "PR":
                    conn["target"]["anchor"] = nearest_pl_anchor_right_of(pl_node_map[tgt_id], src_x + _PILOT_PL_OFFSET)
                else:
                    conn["target"]["anchor"] = nearest_pl_anchor(pl_node_map[tgt_id], src_x)
                # Detectar mesmo x que outra conexão PL→sig.P ou pilot→PL
                if src_anc in ("PL", "PR"):
                    owner_y = node_pos.get(src_id, (0, 0))[1]
                    conn["target"]["anchor"] = _resolve_anchor_conflict(
                        pl_node_map[tgt_id], conn["target"]["anchor"], src_id,
                        owner_y, conn, "target")

    # ── Fase 4: roteamento A* ────────────────────────────────────────────────────
    #
    # Constrói um grid 2D com os bounding boxes de todos os sprites como
    # obstáculos e roteia cada conexão com A* ortogonal.
    # Waypoints resultantes são segmentos estritamente horizontais/verticais
    # que desviam automaticamente de qualquer nó no diagrama.

    from circuit_generator.astar_router import (
        build_grid, route_connection, get_exit_dir, SPRITE_SIZES
    )

    # Construir grid com obstáculos
    astar_grid = build_grid(data["nodes"])

    PL_PIX_W_R  = 71
    PL_SPACING_R = 120

    def _scene_xy(node_id: str, anc: str) -> tuple[float, float] | None:
        npos = node_pos.get(node_id)
        if npos is None:
            return None
        ntype = node_type_map.get(node_id, "")
        if ntype == "PressureLine" and anc.startswith("X"):
            idx = int(anc[1:])
            return (npos[0] + PL_PIX_W_R / 2 + (idx - 1) * PL_SPACING_R, npos[1])
        local = _anchor_local(ntype, anc)
        if local is None:
            return npos
        return (npos[0] + local[0], npos[1] + local[1])

    for conn in data.get("connections", []):
        src_id  = conn["source"]["node"]
        tgt_id  = conn["target"]["node"]
        src_anc = conn["source"]["anchor"]
        tgt_anc = conn["target"]["anchor"]

        spos = _scene_xy(src_id, src_anc)
        tpos = _scene_xy(tgt_id, tgt_anc)
        if spos is None or tpos is None:
            continue

        src_ntype = node_type_map.get(src_id, "")
        tgt_ntype = node_type_map.get(tgt_id, "")

        src_dir = get_exit_dir(src_ntype, src_anc)
        tgt_dir = get_exit_dir(tgt_ntype, tgt_anc)

        wps = route_connection(astar_grid, spos, src_dir, tpos, tgt_dir,
                                src_type=src_ntype, tgt_type=tgt_ntype,
                                src_id=src_id, tgt_id=tgt_id)
        if wps is not None:
            conn["waypoints"] = wps

    return data