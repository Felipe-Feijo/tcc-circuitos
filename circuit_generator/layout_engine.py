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
        "P": (300 * 191/300, 180),
        "A": (300 * 191/300,   0),
        "B": (300 * 256/300,   0),
        "R": (300 * 256/300, 180),
    },
    "Valve_5_2_Ways": {
        "P":  (450 * 338/450, 180),
        "A":  (450 * 270/450,   0),
        "B":  (450 * 405/450,   0),
        "R1": (450 * 271/450, 180),
        "R2": (450 * 405/450, 180),
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

    # ── Fase 1: posicionar nós primários ─────────────────────────────────────
    deferred: list[dict] = []  # Exhaust / PS que serão posicionados na fase 2

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
        elif role.startswith("memory:"):
            n = int(role.split(":", 1)[1])
            x = memory_x + n * cyl_group_w
            y = rows["memory"]

        # ── Linhas de pressão de grupo ────────────────────────────────────────
        elif role.startswith("pressure_line_group:"):
            n = int(role.split(":", 1)[1])
            x = pl_grp_x
            y = rows["pl_grp_base"] + n * rows["pl_grp_gap"]

        # ── Válvulas de sinalização ───────────────────────────────────────────
        elif role.startswith("signal_valve:"):
            code  = int(role.split(":", 1)[1])
            g_idx = code // 100
            e_idx = code % 100
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
    # Para cada filho diferido:
    #   1. Obtém posição do pai (já em node_pos).
    #   2. Calcula posição de cena do anchor pai:
    #        anchor_scene = parent_pos + anchor_local_offset
    #   3. Calcula posição do filho tal que seu próprio anchor de conexão
    #      fique alinhado horizontalmente com anchor pai, e imediatamente
    #      abaixo (+ gap):
    #        child.x = anchor_scene_x - child_anchor_local_x
    #        child.y = anchor_scene_y + gap

    for node in deferred:
        nid   = node["id"]
        ntype = node["type"]
        role  = node.get("_role", "")

        parent_id, parent_anc = child_parent[nid]
        parent_ntype = node_type_map.get(parent_id, "")

        # Posição do pai (pode não estar em node_pos se também foi diferido — improvável)
        px, py = node_pos.get(parent_id, (0.0, 0.0))

        # Offset local do anchor do pai
        parent_anc_local = _anchor_local(parent_ntype, parent_anc)
        if parent_anc_local is None:
            # Tipo de pai desconhecido → fallback simples
            x, y = px, py + 100
        else:
            anc_x = px + parent_anc_local[0]
            anc_y = py + parent_anc_local[1]

            # Offset local do próprio anchor de conexão do filho
            child_anc_name  = _CHILD_CONNECT_ANCHOR[ntype]
            child_anc_local = _anchor_local(ntype, child_anc_name)
            child_dx = child_anc_local[0] if child_anc_local else 0.0

            x = anc_x - child_dx
            y = anc_y + gap

        node["position"] = {"x": x, "y": y}
        node_pos[nid] = (x, y)
        node.pop("_role", None)

    return data