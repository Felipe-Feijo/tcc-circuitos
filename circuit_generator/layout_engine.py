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

    Roles suportados:
      "pressure_source"
      "pressure_line_main"
      "button"
      "and_start"
      "cylinder:{letter}"
      "main_valve:{letter}"
      "memory:{n}"           — n é o índice (0-based) da célula de memória
      "exhaust:{parent_id}"  — requer _parent_pos:{x,y} no nó
      "step_module:{i}"
      "signal_valve:{i}"
      "relay_coil:{i}"
      "relay_switch:{i}"
      "solenoid_coil:{id}"   — requer _cyl_col_x no nó
      "voltage_source"
      "ground"
    """
    cfg = _load_config()
    ox = cfg["origin"]["x"]
    oy = cfg["origin"]["y"]
    rows = cfg["rows"]
    cols = cfg["columns"]
    offsets = cfg["offsets"]

    cyl_group_w = cols["cylinder_group_width"]
    step_mod_w  = cols["step_module_width"]

    # Primeiro passo: montar mapa letter → coluna x para cylinders
    # (precisamos disso para main_valve e solenoid_coil)
    cyl_col: dict[str, int] = {}
    for node in data["nodes"]:
        role: str = node.get("_role", "")
        if role.startswith("cylinder:"):
            letter = role.split(":", 1)[1]
            idx = list(cyl_col.keys()).index(letter) if letter in cyl_col else len(cyl_col)
            if letter not in cyl_col:
                cyl_col[letter] = ox + idx * cyl_group_w

    # Segundo passo: atribuir posições
    for node in data["nodes"]:
        role: str = node.get("_role", "")

        if not role:
            node.pop("_role", None)
            continue

        x, y = ox, oy  # fallback

        if role == "pressure_source":
            x = ox
            y = oy + rows["infra"]

        elif role == "pressure_line_main":
            x = ox
            y = oy + rows["infra"]

        elif role == "button":
            x = ox + cols["infra_button_offset_x"]
            y = oy + rows["infra"]

        elif role == "and_start":
            x = ox + cols["infra_and_offset_x"]
            y = oy + rows["infra"]

        elif role.startswith("cylinder:"):
            letter = role.split(":", 1)[1]
            x = cyl_col.get(letter, ox)
            y = oy + rows["cylinder"]

        elif role.startswith("main_valve:"):
            letter = role.split(":", 1)[1]
            x = cyl_col.get(letter, ox)
            y = oy + rows["main_valve"]

        elif role.startswith("memory:"):
            n = int(role.split(":", 1)[1])
            x = ox + n * cyl_group_w
            y = oy + rows["memory"]

        elif role.startswith("pressure_line_group:"):
            n = int(role.split(":", 1)[1])
            x = ox + n * cyl_group_w
            y = oy + rows["memory"]

        elif role.startswith("exhaust:"):
            # Espera _parent_pos:{x, y} no nó
            parent_pos = node.pop("_parent_pos", None)
            if parent_pos:
                x = parent_pos["x"] + offsets["exhaust_dx"]
                y = parent_pos["y"] + offsets["exhaust_dy"]
            # se não tiver _parent_pos mantém fallback

        elif role.startswith("step_module:"):
            i = int(role.split(":", 1)[1])
            x = ox + i * step_mod_w
            y = oy + rows["steps"]

        elif role.startswith("signal_valve:"):
            i = int(role.split(":", 1)[1])
            x = ox + i * step_mod_w
            y = oy + rows["signals"]

        elif role.startswith("relay_coil:"):
            i = int(role.split(":", 1)[1])
            x = ox + i * step_mod_w
            y = oy + rows["steps"]

        elif role.startswith("relay_switch:"):
            i = int(role.split(":", 1)[1])
            x = ox + int((i + cols["relay_switch_half_offset"]) * step_mod_w)
            y = oy + rows["steps"]

        elif role.startswith("solenoid_coil:"):
            cyl_x = node.pop("_cyl_col_x", ox)
            x = cyl_x
            y = oy + rows["electric"]

        elif role == "voltage_source":
            x = ox
            y = oy + rows["electric"]

        elif role == "ground":
            x = ox + offsets["ground_dx"]
            y = oy + rows["electric"]

        node["position"] = {"x": x, "y": y}
        node.pop("_role", None)

    return data