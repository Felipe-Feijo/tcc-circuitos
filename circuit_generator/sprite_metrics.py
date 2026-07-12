"""
sprite_metrics.py
-----------------
Fonte única de verdade para dimensões de sprites e constantes de layout
derivadas do código gráfico.

Tudo aqui é lido automaticamente:
  - Dimensões de sprites  → PIL (leitura dos PNGs em resources/)
  - PL spacing            → parse do expandable_item.py (self.spacing = <N>)
  - Anchor ratios         → hardcoded como frações (ex: 254/300), mas calculados
                            sobre a largura real do sprite, então mudar o PNG
                            atualiza o valor automaticamente.

Uso:
    from circuit_generator.sprite_metrics import METRICS
    pl_pix_w   = METRICS.pl_pix_w       # largura do terminal da PressureLine
    pl_spacing = METRICS.pl_spacing      # espaçamento entre anchors
    cyl_width  = METRICS.cyl_width       # largura do DoubleActingCylinder
    ...
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path


_ROOT = Path(__file__).parent.parent  # raiz do projeto


# ── Leitura de sprite ─────────────────────────────────────────────────────────

def _sprite_size(relative_path: str) -> tuple[int, int]:
    """Retorna (width, height) do PNG, sem depender de PyQt."""
    from PIL import Image
    path = _ROOT / relative_path
    with Image.open(path) as img:
        return img.width, img.height


# ── Leitura do spacing do expandable_item.py ─────────────────────────────────

def _read_expandable_spacing() -> int:
    """
    Faz parse de 'self.spacing = <N>' no expandable_item.py.
    Lança ValueError se não encontrar.
    """
    src = _ROOT / "graphics/items/base/nodes/expandable/expandable_item.py"
    text = src.read_text(encoding="utf-8")
    m = re.search(r"self\.spacing\s*=\s*(\d+)", text)
    if not m:
        raise ValueError(f"Não foi possível ler 'self.spacing' em {src}")
    return int(m.group(1))


def _read_body_state1_offset_x(src_path: str) -> float:
    """
    Lê o x de BODY_VISUALS[1]["offset"] = QPointF(<N>, 0) -- o deslocamento
    visual do corpo da válvula direcional no estado comutado ("ativo").
    """
    src = Path(_ROOT / src_path).read_text(encoding="utf-8")
    m = re.search(r'1:\s*\{.*?"offset":\s*QPointF\(([\d.]+)\s*,', src, re.DOTALL)
    if not m:
        raise ValueError(f"Não foi possível ler BODY_VISUALS[1]['offset'] em {src_path}")
    return float(m.group(1))


# ── Dataclass com todas as métricas ──────────────────────────────────────────

@dataclass(frozen=True)
class SpriteMetrics:
    # PressureLine
    pl_pix_w:   int    # largura do terminal sprite
    pl_pix_h:   int    # altura do terminal sprite
    pl_spacing: int    # espaçamento entre anchors (expandable_item.py)

    # DoubleActingCylinder
    cyl_width:  int
    cyl_height: int

    # Valve_4_2_Ways
    v42_width:  int
    v42_height: int

    # Valve_5_2_Ways
    v52_width:  int
    v52_height: int

    # Valve_3_2_Ways
    v32_width:  int
    v32_height: int

    # Pilot actuator
    pilot_w:    int  # largura do sprite de pilot (usado nos anchors PL/PR)

    # Exhaust
    exh_width:  int
    exh_height: int

    # PressureSource
    ps_width:   int
    ps_height:  int

    # OrValve
    or_width:   int
    or_height:  int

    # Anchors locais calculados a partir das dimensões reais dos sprites.
    # Cada entrada: tipo → { porta → (local_x, local_y) }
    anchor_local: dict = field(default_factory=dict)

    # Derivados da PressureLine (calculados no __post_init__)
    v52_sprite_cx: float = field(init=False)
    mc_chain_offset: float = field(init=False)  # V52_A_X - V52_P_X
    mc_x_step: int = field(init=False)           # A.x - P.x (alinha A[i+1] com P[i])

    # Espaçamento mínimo entre anchors A de duas válvulas 3/2 adjacentes.
    #
    # As sigs que pilotam uma 4/2 são organizadas em uma grid 2D relativa ao pilot:
    #
    #   Colunas = sinais em paralelo (OR - condições alternativas que ativam o
    #             mesmo pilot). Espaçadas por sig_spacing em X.
    #   Linhas  = sinais em série dentro de uma coluna (AND - condições conjuntas).
    #             Empilhadas verticalmente na mesma coluna.
    #
    #   Ordem: colunas mais próximas da 4/2 = acionamentos mais tardios na
    #   sequência; colunas externas = acionamentos mais antecipados.
    #
    # sig_spacing garante não-sobreposição entre colunas adjacentes:
    #   fp_left  = A_x + pilot_w              (sprite + atuador esquerdo)
    #   fp_right = (v32_w - A_x) + pilot_w + comutation_shift
    #
    sig_fp_left:  int = field(init=False)  # px a esquerda do anchor A
    sig_fp_right: int = field(init=False)  # px a direita do anchor A (com shift)
    sig_spacing:  int = field(init=False)  # sig_fp_left + sig_fp_right

    # Deslocamento horizontal do corpo/pilots no estado comutado ("ativo")
    # de cada válvula direcional -- lido de BODY_VISUALS[1]["offset"] em
    # cada arquivo gráfico. Chave = node_type. É sempre >= 0 (comutar só
    # empurra o pilot PR pra direita, nunca pra esquerda) -- ver
    # docs/superpowers/specs/2026-07-11-directional-valve-pilot-anchor-offset-design.md.
    pilot_side_offset_x: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "v52_sprite_cx", self.v52_width / 2)
        v52_P_x = self.v52_width * 338/450
        v52_A_x = self.v52_width * 270/450
        chain = v52_A_x - v52_P_x
        object.__setattr__(self, "mc_chain_offset", chain)
        object.__setattr__(self, "mc_x_step", int(abs(chain)))

        v32_A_x  = self.anchor_local.get("Valve_3_2_Ways", {}).get("A", (254, 0))[0]
        fp_left  = int(v32_A_x + self.pilot_w)
        fp_right = int((self.v32_width - v32_A_x) + self.pilot_w + self.pilot_side_offset_x.get("Valve_3_2_Ways", 147.0))
        object.__setattr__(self, "sig_fp_left",  fp_left)
        object.__setattr__(self, "sig_fp_right", fp_right)
        object.__setattr__(self, "sig_spacing",  fp_left + fp_right)


def _ratio_from_expr(expr: str, axis: str) -> float:
    """
    Extrai a fração de 'self.<axis>' numa expressão de coordenada de anchor.
    Cobre os três formatos usados nos componentes gráficos:
      "self.<axis>"                -> 1.0
      "self.<axis>*NUM/DEN" / "*F" -> NUM/DEN ou F
      literal (ex: "0")            -> 0.0
    """
    expr = expr.strip()
    if expr == f"self.{axis}":
        return 1.0
    m = re.search(rf'self\.{axis}\s*\*\s*([\d./]+)', expr)
    if m:
        return eval(m.group(1))
    return 0.0


def _parse_anchor_ratios(src_path: str) -> dict[str, tuple[float, float]]:
    """
    Extrai frações de anchor do initialize_anchors() de um arquivo fonte.
    Lê expressões do tipo:
      AnchorItem("NAME", QPointF(self.width*NUM/DEN, self.height_or_0), ...)
    Retorna { name: (x_ratio, y_ratio) } — frações de width/height. Cobre
    "self.<eixo>" (1.0), "self.<eixo>*fração" e literal (0.0).
    """
    src = Path(_ROOT / src_path).read_text(encoding="utf-8")
    pat = re.compile(
        r'AnchorItem\(\s*["\'](\w+)["\'\]],\s*QPointF\(([^,]+),\s*([^)]+)\)',
    )
    result = {}
    for m in pat.finditer(src):
        name   = m.group(1)
        x_expr = m.group(2).strip()
        y_expr = m.group(3).strip()
        result[name] = (_ratio_from_expr(x_expr, "width"),
                         _ratio_from_expr(y_expr, "height"))
    return result


def _read_pilot_y_ratio() -> float:
    """Lê self.height * <ratio> do directional_valve_item.py."""
    import re
    src = Path(_ROOT / "graphics/items/base/nodes/directional_valve/directional_valve_item.py").read_text(encoding="utf-8")
    m = re.search(r'self\.height\s*\*\s*([\d.]+)\s*[,)]', src)
    if not m:
        raise ValueError("Não foi possível ler pilot_y_ratio em directional_valve_item.py")
    return float(m.group(1))


def _build_anchor_local(m: "SpriteMetrics") -> dict:
    """
    Calcula _ANCHOR_LOCAL parseando as frações diretamente dos arquivos fonte
    de cada componente gráfico — sem hardcode de frações aqui.
    """
    pilot_y = _read_pilot_y_ratio()
    pilot_w = m.pilot_w

    def _resolve(ratios: dict, width: int, height: int,
                 extra: dict | None = None) -> dict:
        """Converte { name: (x_ratio, y_ratio) } em { name: (x, y) }."""
        result = {}
        for name, (xr, yr) in ratios.items():
            result[name] = (width * xr, height * yr)
        if extra:
            result.update(extra)
        return result

    v32 = _parse_anchor_ratios("graphics/items/base/nodes/directional_valve/valve_3_2_ways.py")
    v42 = _parse_anchor_ratios("graphics/items/base/nodes/directional_valve/valve_4_2_ways.py")
    v52 = _parse_anchor_ratios("graphics/items/base/nodes/directional_valve/valve_5_2_ways.py")
    cyl = _parse_anchor_ratios("graphics/items/base/nodes/cylinder/double_acting_cylinder.py")
    exh = _parse_anchor_ratios("graphics/items/base/nodes/exhaust.py")
    ps  = _parse_anchor_ratios("graphics/items/base/nodes/pressure_source.py")
    or_ = _parse_anchor_ratios("graphics/items/base/nodes/logic_valve/or_valve.py")

    return {
        "DoubleActingCylinder": _resolve(cyl, m.cyl_width,  m.cyl_height),
        "Exhaust":              _resolve(exh, m.exh_width,  m.exh_height),
        "PressureSource":       _resolve(ps,  m.ps_width,   m.ps_height),
        "Valve_3_2_Ways":       _resolve(v32, m.v32_width,  m.v32_height, extra={
            "PL": (-pilot_w,              m.v32_height * pilot_y),
            "PR": (m.v32_width + pilot_w, m.v32_height * pilot_y),
        }),
        "Valve_4_2_Ways":       _resolve(v42, m.v42_width,  m.v42_height, extra={
            "PL": (-pilot_w,              m.v42_height * pilot_y),
            "PR": (m.v42_width + pilot_w, m.v42_height * pilot_y),
        }),
        "Valve_5_2_Ways":       _resolve(v52, m.v52_width,  m.v52_height, extra={
            "PL": (-pilot_w,              m.v52_height * pilot_y),
            "PR": (m.v52_width + pilot_w, m.v52_height * pilot_y),
        }),
        "OrValve":              _resolve(or_, m.or_width,   m.or_height),
    }


def _load() -> SpriteMetrics:
    pl_w, pl_h   = _sprite_size("resources/nodes/pressure_line/pressure_line_terminal.png")
    cyl_w, cyl_h = _sprite_size("resources/nodes/double_acting_cylinder/double_acting_cylinder_body.png")
    v42_w, v42_h = _sprite_size("resources/nodes/valve_4_2_ways/valve_4_2_body_left.png")
    v52_w, v52_h = _sprite_size("resources/nodes/valve_5_2_ways/valve_5_2_body_left.png")
    v32_w, v32_h = _sprite_size("resources/nodes/valve_3_2_ways/valve_3_2_body_left.png")
    exh_w, exh_h = _sprite_size("resources/nodes/exhaust/exhaust.png")
    ps_w,  ps_h  = _sprite_size("resources/nodes/pressure_source/pressure_source.png")
    or_w,  or_h  = _sprite_size("resources/nodes/or_valve/or_valve_x_side.png")
    spacing      = _read_expandable_spacing()

    pilot_w, _    = _sprite_size("resources/actuators/pilot/pilot.png")

    pilot_side_offset_x = {
        "Valve_3_2_Ways": _read_body_state1_offset_x(
            "graphics/items/base/nodes/directional_valve/valve_3_2_ways.py"),
        "Valve_4_2_Ways": _read_body_state1_offset_x(
            "graphics/items/base/nodes/directional_valve/valve_4_2_ways.py"),
        "Valve_5_2_Ways": _read_body_state1_offset_x(
            "graphics/items/base/nodes/directional_valve/valve_5_2_ways.py"),
    }

    m = SpriteMetrics(
        pl_pix_w=pl_w,   pl_pix_h=pl_h,   pl_spacing=spacing,
        cyl_width=cyl_w, cyl_height=cyl_h,
        v42_width=v42_w, v42_height=v42_h,
        v52_width=v52_w, v52_height=v52_h,
        v32_width=v32_w, v32_height=v32_h,
        exh_width=exh_w, exh_height=exh_h,
        ps_width=ps_w,   ps_height=ps_h,
        or_width=or_w,   or_height=or_h,
        pilot_w=pilot_w,
        anchor_local={},
        pilot_side_offset_x=pilot_side_offset_x,
    )
    # anchor_local é frozen, então populamos via object.__setattr__
    object.__setattr__(m, "anchor_local", _build_anchor_local(m))
    return m


# Singleton — carregado uma vez na importação
METRICS: SpriteMetrics = _load()


def anchor_local_for_routing(node_type: str, anchor_name: str) -> tuple[float, float] | None:
    """
    Como METRICS.anchor_local[node_type][anchor_name], mas para PR soma
    sempre o deslocamento de comutação -- o pior caso (mais à direita)
    que o pilot pode ocupar em QUALQUER estado, já que comutar só empurra
    pra direita, nunca pra esquerda. PL não precisa de ajuste (seu pior
    caso, mais à esquerda, já é o valor sem deslocamento). Ver
    docs/superpowers/specs/2026-07-11-directional-valve-pilot-anchor-offset-design.md.
    """
    base = METRICS.anchor_local.get(node_type, {}).get(anchor_name)
    if base is None:
        return None
    if anchor_name == "PR":
        return (base[0] + METRICS.pilot_side_offset_x.get(node_type, 0.0), base[1])
    return base


if __name__ == "__main__":
    m = METRICS
    print(f"PressureLine terminal : {m.pl_pix_w} x {m.pl_pix_h}  spacing={m.pl_spacing}")
    print(f"DoubleActingCylinder  : {m.cyl_width} x {m.cyl_height}")
    print(f"Valve_4_2_Ways        : {m.v42_width} x {m.v42_height}")
    print(f"Valve_5_2_Ways        : {m.v52_width} x {m.v52_height}")
    print(f"Valve_3_2_Ways        : {m.v32_width} x {m.v32_height}")
    print(f"Exhaust               : {m.exh_width} x {m.exh_height}")
    print(f"PressureSource        : {m.ps_width} x {m.ps_height}")
    print(f"v52_sprite_cx         : {m.v52_sprite_cx}")
    print(f"mc_chain_offset       : {m.mc_chain_offset}")
    print(f"mc_x_step             : {m.mc_x_step}")
    print()
    print("Anchor local:")
    for node_type, anchors in m.anchor_local.items():
        print(f"  {node_type}:")
        for port, pos in anchors.items():
            print(f"    {port}: ({pos[0]:.2f}, {pos[1]:.2f})")