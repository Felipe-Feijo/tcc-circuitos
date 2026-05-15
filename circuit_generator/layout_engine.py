import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "layout_config.json"


def _load_config() -> dict:
    with _CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def apply(data: dict) -> dict:
    """
    Recebe o JSON com _role em cada nó.
    Lê layout_config.json, calcula e preenche position.x e position.y.
    Remove _role de todos os nós.
    Retorna o dict modificado (in-place).

    Roles suportados (cascade pneumático):
      "pressure_source"              — gen-ps (fonte principal)
      "pressure_line_main"           — (legacy, mantido por compatibilidade)
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
    offsets = cfg["offsets"]

    cyl_first_x    = cols["cylinder_first_x"]
    cyl_group_w    = cols["cylinder_group_width"]
    pl_grp_x       = cols["pl_grp_x"]
    memory_x       = cols["memory_x"]
    btn_offset_x   = cols["btn_offset_x"]
    ps_offset_x    = cols["ps_offset_x"]
    step_mod_w     = cols["step_module_width"]

    # ── Passo 1: mapear letter → coluna x (para cylinders e v42) ─────────────
    cyl_col: dict[str, float] = {}
    for node in data["nodes"]:
        role: str = node.get("_role", "")
        if role.startswith("cylinder:"):
            letter = role.split(":", 1)[1]
            if letter not in cyl_col:
                idx = len(cyl_col)
                cyl_col[letter] = cyl_first_x + idx * cyl_group_w

    # ── Passo 2: mapear signal_valve → (group_idx, event_idx) ────────────────
    # role = "signal_valve:{g*100+e}"  →  g = i // 100, e = i % 100
    # Precisamos do grupo para calcular y das sigs
    # (sigs do grupo 0 ficam na faixa dos v42/pl-grp, grupos seguintes descem)

    # ── Passo 3: atribuir posições ────────────────────────────────────────────
    for node in data["nodes"]:
        role: str = node.get("_role", "")

        if not role:
            node.pop("_role", None)
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

        elif role == "exhaust:btn-R":
            x = memory_x + btn_offset_x + offsets["btn_exh_dx"]
            y = rows["button"] + offsets["btn_exh_dy"]

        elif role == "and_start":
            x = cols["infra_and_offset_x"]
            y = rows["infra"]

        # ── Cilindros ────────────────────────────────────────────────────────
        elif role.startswith("cylinder:"):
            letter = role.split(":", 1)[1]
            x = cyl_col.get(letter, 0.0)
            y = rows["cylinder"]

        # ── Válvulas 4/2 e seus PS/Exhaust dedicados ─────────────────────────
        elif role.startswith("main_valve:"):
            letter = role.split(":", 1)[1]
            x = cyl_col.get(letter, 0.0)
            y = rows["main_valve"]

        elif role.startswith("exhaust:v42-") and role.endswith("-P"):
            # "exhaust:v42-{letter}-P"
            letter = role.split("-")[1]
            x = cyl_col.get(letter, 0.0) - cols["v42_exh_offset_x"]
            y = rows["v42_ps_exh"]

        elif role.startswith("pressure_source:v42-") and role.endswith("-R"):
            # "pressure_source:v42-{letter}-R"
            letter = role.split("-")[1]
            x = cyl_col.get(letter, 0.0) + cols["v42_ps_offset_x"]
            y = rows["v42_ps_exh"]

        # ── Memórias 5/2 ─────────────────────────────────────────────────────
        elif role.startswith("memory:"):
            n = int(role.split(":", 1)[1])
            x = memory_x + n * cyl_group_w
            y = rows["memory"]

        elif role.startswith("exhaust:") and (role.endswith("-r1") or role.endswith("-r2")):
            # "exhaust:{mem_id}-r1" ou "exhaust:{mem_id}-r2"
            is_r2 = role.endswith("-r2")
            dx = offsets["mc_exh_r2_dx"] if is_r2 else offsets["mc_exh_r1_dx"]
            x = memory_x + dx
            y = rows["memory"] + offsets["mc_exh_dy"]

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
            # Grupo 0: sigs ao nível dos v42 (~y=370), distribuídas em x
            # Grupos seguintes: descem junto com as pl-grp
            if g_idx == 0:
                # sigs de extensão: ficam entre os cilindros, nível v42
                x = cyl_first_x + e_idx * (cyl_group_w // max(1, 2))
                y = rows["v42_ps_exh"] - 10
            else:
                # sigs de grupos seguintes: ao nível da memória / btn
                x = memory_x + (e_idx - 1) * (cyl_group_w // 2) + 330
                y = rows["memory"] + g_idx * 185

        elif role.startswith("exhaust:sig-"):
            # "exhaust:sig-{code}"  onde code = g_idx*100 + e_idx
            # Posiciona ao lado da sig correspondente (mesma lógica de signal_valve)
            try:
                code  = int(role.split("exhaust:sig-", 1)[1])
                g_idx = code // 100
                e_idx = code % 100
                if g_idx == 0:
                    sx = cyl_first_x + e_idx * (cyl_group_w // max(1, 2))
                    sy = rows["v42_ps_exh"] - 10
                else:
                    sx = memory_x + (e_idx - 1) * (cyl_group_w // 2) + 330
                    sy = rows["memory"] + g_idx * 185
                x = sx + offsets["sig_exh_dx"]
                y = sy + offsets["sig_exh_dy"]
            except (ValueError, IndexError):
                parent_pos = node.pop("_parent_pos", None)
                if parent_pos:
                    x = parent_pos["x"] + offsets["sig_exh_dx"]
                    y = parent_pos["y"] + offsets["sig_exh_dy"]

        # ── Legacy exhaust genérico (com _parent_pos) ─────────────────────────
        elif role.startswith("exhaust:"):
            parent_pos = node.pop("_parent_pos", None)
            if parent_pos:
                x = parent_pos["x"] + offsets["exhaust_dx"]
                y = parent_pos["y"] + offsets["exhaust_dy"]

        # ── Elétrico (legacy) ─────────────────────────────────────────────────
        elif role.startswith("step_module:"):
            i = int(role.split(":", 1)[1])
            x = i * step_mod_w
            y = rows["steps"]

        elif role.startswith("signal_valve:"):
            i = int(role.split(":", 1)[1])
            x = i * step_mod_w
            y = rows["signals"]

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
            x = offsets["ground_dx"]
            y = rows["electric"]

        node["position"] = {"x": x, "y": y}
        node.pop("_role", None)

    return data
