"""
sprite_metrics.py
-----------------
Single source of truth for sprite dimensions and layout constants
derived from the graphics code.

Everything here is read automatically:
  - Sprite dimensions -> PIL (reads the PNGs under resources/)
  - PL spacing        -> hardcoded constant (60 pixels, from ExpandableItem)
  - Anchor ratios     -> hardcoded as fractions (e.g. 254/300), but computed
                         against the sprite's real width, so changing the
                         PNG updates the value automatically.

Usage:
    from circuit_generator.sprite_metrics import METRICS
    pl_pix_w   = METRICS.pl_pix_w       # PressureLine terminal width
    pl_spacing = METRICS.pl_spacing      # spacing between anchors
    cyl_width  = METRICS.cyl_width       # DoubleActingCylinder width
    ...
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path

from paths import get_base_dir

_ROOT = get_base_dir()  # project root


# -- Sprite reading -------------------------------------------------------------

def _sprite_size(relative_path: str) -> tuple[int, int]:
    """Returns the PNG's (width, height), without depending on PyQt."""
    from PIL import Image
    path = _ROOT / relative_path
    with Image.open(path) as img:
        return img.width, img.height


# -- PressureLine spacing constant -----------------------------------------------
# Previously read dynamically from expandable_item.py, now hardcoded after
# ExpandableItem was replaced by PairedTerminalItem (Task 6).

def _read_expandable_spacing() -> int:
    """
    Returns the PressureLine spacing constant (60 pixels).
    Hardcoded after ExpandableItem was replaced by PairedTerminalItem.
    """
    return 60


def _read_body_state1_offset_x(src_path: str) -> float:
    """
    Reads the x from BODY_VISUALS[1]["offset"] = QPointF(<N>, 0) -- the
    directional valve body's visual shift in the commutated ("active")
    state.
    """
    src = Path(_ROOT / src_path).read_text(encoding="utf-8")
    m = re.search(r'1:\s*\{.*?"offset":\s*QPointF\(([\d.]+)\s*,', src, re.DOTALL)
    if not m:
        raise ValueError(f"Could not read BODY_VISUALS[1]['offset'] in {src_path}")
    return float(m.group(1))


# -- Dataclass holding all the metrics -------------------------------------------

@dataclass(frozen=True)
class SpriteMetrics:
    # PressureLine
    pl_pix_w:   int    # terminal sprite width
    pl_pix_h:   int    # terminal sprite height
    pl_spacing: int    # spacing between anchors (60 pixels)

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
    pilot_w:    int  # pilot sprite width (used for the PL/PR anchors)

    # Cascade sigs' actuators (limit_switch on the left, spring on the
    # right -- see Valve_3_2_Ways.actuators in cascade.py)
    limit_switch_w: int
    spring_w:       int

    # Exhaust
    exh_width:  int
    exh_height: int

    # PressureSource
    ps_width:   int
    ps_height:  int

    # OrValve
    or_width:   int
    or_height:  int

    # Contact (NO/NC electric contact -- button, relay, solenoid or
    # limit-switch actuated; same body sprite regardless)
    contact_width:  int
    contact_height: int

    # SolenoidCoil
    solenoid_coil_width:  int
    solenoid_coil_height: int

    # RelayCoil
    relay_coil_width:  int
    relay_coil_height: int

    # VoltageSource / Ground (expandable bars -- do NOT go into
    # anchor_local, same treatment as PressureLine)
    vsource_pix_w: int
    vsource_pix_h: int
    ground_pix_w:  int
    ground_pix_h:  int

    # Local anchors computed from the sprites' real dimensions.
    # Each entry: type -> { port -> (local_x, local_y) }
    anchor_local: dict = field(default_factory=dict)

    # Derived from the PressureLine (computed in __post_init__)
    v52_sprite_cx: float = field(init=False)
    mc_chain_offset: float = field(init=False)  # V52_A_X - V52_P_X
    mc_x_step: int = field(init=False)           # A.x - P.x (aligns A[i+1] with P[i])

    # Minimum spacing between two adjacent 3/2 valves' A anchors.
    #
    # The sigs piloting a 4/2 valve are arranged in a 2D grid relative to the pilot:
    #
    #   Columns = parallel signals (OR -- alternative conditions triggering
    #             the same pilot). Spaced by sig_spacing in X.
    #   Rows    = signals in series within a column (AND -- joint
    #             conditions). Stacked vertically in the same column.
    #
    #   Order: columns closer to the 4/2 = later triggers in the sequence;
    #   outer columns = earlier triggers.
    #
    # sig_spacing guarantees no overlap between adjacent columns:
    #   fp_left  = A_x + pilot_w              (sprite + left actuator)
    #   fp_right = (v32_w - A_x) + pilot_w + comutation_shift
    #
    sig_fp_left:  int = field(init=False)  # px to the left of anchor A
    sig_fp_right: int = field(init=False)  # px to the right of anchor A (with shift)
    sig_spacing:  int = field(init=False)  # sig_fp_left + sig_fp_right

    # Minimum column pitch to place two cascade sigs (limit_switch + body +
    # spring) side by side without overlapping, in the worst case where
    # the left one is commutated (whole body shifted
    # +pilot_side_offset_x to the right, see BODY_VISUALS[1]) and the
    # right one isn't. Unlike sig_fp_right above (which uses pilot_w as
    # a generic approximation for the right actuator), uses the spring
    # sprite's REAL width -- found via live-UI testing: sig_spacing
    # (647px) came up 36px short of the pitch actually needed (683px),
    # exactly the difference between spring_w (136px) and pilot_w
    # (100px).
    sig_col_pitch: int = field(init=False)

    # Each directional valve's horizontal body/pilot shift in the
    # commutated ("active") state -- read from BODY_VISUALS[1]["offset"]
    # in each graphics file. Key = node_type. Always >= 0 (commutating
    # only pushes the PR pilot to the right, never left) -- see
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

        object.__setattr__(self, "sig_col_pitch", int(
            self.limit_switch_w + self.v32_width + self.spring_w
            + self.pilot_side_offset_x.get("Valve_3_2_Ways", 147.0)))


def _ratio_from_expr(expr: str, axis: str) -> float:
    """
    Extracts the 'self.<axis>' fraction from an anchor coordinate
    expression. Covers the three formats used across graphics components:
      "self.<axis>"                -> 1.0
      "self.<axis>*NUM/DEN" / "*F" -> NUM/DEN or F
      literal (e.g. "0")           -> 0.0
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
    Extracts anchor fractions from a source file's initialize_anchors().
    Reads expressions like:
      AnchorItem("NAME", QPointF(self.width*NUM/DEN, self.height_or_0), ...)
    Returns { name: (x_ratio, y_ratio) } -- width/height fractions. Covers
    "self.<axis>" (1.0), "self.<axis>*fraction" and literal (0.0).
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
    """Reads self.height * <ratio> from directional_valve_item.py."""
    import re
    src = Path(_ROOT / "graphics/items/base/nodes/directional_valve/directional_valve_item.py").read_text(encoding="utf-8")
    m = re.search(r'self\.height\s*\*\s*([\d.]+)\s*[,)]', src)
    if not m:
        raise ValueError("Could not read pilot_y_ratio in directional_valve_item.py")
    return float(m.group(1))


def _build_anchor_local(m: "SpriteMetrics") -> dict:
    """
    Computes _ANCHOR_LOCAL by parsing the fractions directly from each
    graphics component's source file -- no hardcoded fractions here.
    """
    pilot_y = _read_pilot_y_ratio()
    pilot_w = m.pilot_w

    def _resolve(ratios: dict, width: int, height: int,
                 extra: dict | None = None) -> dict:
        """Converts { name: (x_ratio, y_ratio) } into { name: (x, y) }."""
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
    contact = _parse_anchor_ratios("graphics/items/base/nodes/switch/contact.py")

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
        "Contact":              _resolve(contact, m.contact_width, m.contact_height),
        "SolenoidCoil": {
            "T": (m.solenoid_coil_width / 2, 0.0),
            "B": (m.solenoid_coil_width / 2, float(m.solenoid_coil_height)),
        },
        "RelayCoil": {
            "T": (m.relay_coil_width / 2, 0.0),
            "B": (m.relay_coil_width / 2, float(m.relay_coil_height)),
        },
        # PairedTerminalItem bus taps (Task 6 rail.py migration). These
        # mirror the REAL graphics classes' anchor offsets exactly (see
        # PressureLine.initialize_own_anchor() -- QPointF(width/2, height)).
        # rail.py is responsible for translating between this local offset
        # and the node's stored (origin) "position" -- it must NOT be
        # compensated away here (see rail.py's _materialize_bus).
        "PressureLine": {
            "X1": (m.pl_pix_w / 2, float(m.pl_pix_h)),
        },
        # The far end of the bus is a real PressureLineTerminal node
        # (rail.py's node_b) -- same anchor offset as the bus's own X1
        # anchor (PressureLineTerminal.setup()'s QPointF(width/2, height)).
        "PressureLineTerminal": {
            "X1": (m.pl_pix_w / 2, float(m.pl_pix_h)),
        },
        # Plain junction dot for interior bus taps -- no offset from its
        # own position.
        "JunctionNodeItem": {
            "J": (0.0, 0.0),
        },
        # VoltageSource/Ground bus (Task 7 rail.py migration, step_by_step_
        # electric_layout.py). Reproduces VoltageSource.initialize_own_anchor()'s
        # QPointF(self.width, self.height*0.69) and
        # Ground.initialize_own_anchor()'s QPointF(self.width/2, 0) exactly --
        # rail.py (not this table) is responsible for translating between
        # this local offset and each node's stored origin position.
        "VoltageSource": {
            "X1": (float(m.vsource_pix_w), float(m.vsource_pix_h) * 0.69),
        },
        "Ground": {
            "X1": (float(m.ground_pix_w) / 2, 0.0),
        },
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
    contact_w, contact_h = _sprite_size("resources/nodes/contact/contact_no_open.png")
    solenoid_coil_w, solenoid_coil_h = _sprite_size("resources/nodes/solenoid_coil/solenoid_coil.png")
    relay_coil_w, relay_coil_h = _sprite_size("resources/nodes/relay_coil/relay_coil.png")
    vsource_w, vsource_h = _sprite_size("resources/nodes/voltage_source/voltage_source_terminal.png")
    ground_w,  ground_h  = _sprite_size("resources/nodes/ground/ground_terminal.png")
    spacing      = _read_expandable_spacing()

    pilot_w, _    = _sprite_size("resources/actuators/pilot/pilot.png")
    limit_switch_w, _ = _sprite_size("resources/actuators/limit_switch/limit_switch_active.png")
    spring_w, _       = _sprite_size("resources/actuators/spring/spring_active.png")

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
        contact_width=contact_w, contact_height=contact_h,
        solenoid_coil_width=solenoid_coil_w, solenoid_coil_height=solenoid_coil_h,
        relay_coil_width=relay_coil_w, relay_coil_height=relay_coil_h,
        vsource_pix_w=vsource_w, vsource_pix_h=vsource_h,
        ground_pix_w=ground_w, ground_pix_h=ground_h,
        pilot_w=pilot_w,
        limit_switch_w=limit_switch_w,
        spring_w=spring_w,
        anchor_local={},
        pilot_side_offset_x=pilot_side_offset_x,
    )
    # anchor_local is frozen, so we populate it via object.__setattr__
    object.__setattr__(m, "anchor_local", _build_anchor_local(m))
    return m


# Singleton -- loaded once at import time
METRICS: SpriteMetrics = _load()


def anchor_local_for_routing(node_type: str, anchor_name: str,
                             peer_type: str | None = None) -> tuple[float, float] | None:
    """
    Like METRICS.anchor_local[node_type][anchor_name], but for PR always
    adds the commutation shift -- the worst case (furthest right) the
    pilot can occupy in ANY state, since commutating only pushes right,
    never left. PL needs no adjustment (its worst case, furthest left,
    is already the value with no shift). See
    docs/superpowers/specs/2026-07-11-directional-valve-pilot-anchor-offset-design.md.

    Valve_3_2_Ways.P gets the SAME adjustment, but only when `peer_type`
    is `None` (the caller doesn't know/care who feeds P -- e.g. computing
    worst-case reserved space) or is explicitly `"PressureLine"` -- that's
    what feeds this P on confirmation signaling valves (cascade and
    step-by-step), and the offset compensates for the visual shift of
    BODY_VISUALS[1] (commutated) that the local anchor (a fixed fraction
    of self.width) doesn't bake in on its own.

    Important: the P anchor itself NEVER moves with body_state (only
    PL/PR follow the commutated body -- see directional_valve_item.py) --
    the offset in the PressureLine case doesn't describe where the
    anchor is drawn, it's kept for compatibility with the PL's anchor
    column choice (see _target_x in step_by_step_layout.py and the
    tests in tests/test_cascade_layout.py that depend on this
    right-side approximation to steer clear of the spring). Properly
    fixing this (making the route's final point land on the anchor's
    real position, keeping the right-side approximation as an explicit
    routing rule instead of baked into the coordinate) is a bigger,
    separate problem, out of scope for this fix.

    When `peer_type` is passed and is NOT `"PressureLine"` (e.g. another
    signaling valve feeding this P via a sig.A -> sig.P chain link), the
    offset does NOT apply -- P isn't receiving from a PressureLine, so
    the commutation shift is irrelevant there. Without this distinction,
    the router aimed 147px to the right of the anchor's real position on
    these links, producing a small spurious loop when the editor
    repaired the misaligned waypoint on loading the circuit (found while
    testing a circuit with C+(A+B+)C-A-B-, a chain of sigs stacked in
    the same column -- see docs/superpowers/specs/
    2026-08-12-sig-chain-p-anchor-offset-design.md).

    Doesn't extend to Valve_4_2_Ways.P/Valve_5_2_Ways.P: on those types,
    P is never fed by a PressureLine (it comes from a dedicated
    Exhaust/PressureSource -- see
    circuit_generator/methods/cascade.py), so the shift never matters
    there.
    """
    base = METRICS.anchor_local.get(node_type, {}).get(anchor_name)
    if base is None:
        return None
    if anchor_name == "PR":
        return (base[0] + METRICS.pilot_side_offset_x.get(node_type, 0.0), base[1])
    if anchor_name == "P" and node_type == "Valve_3_2_Ways":
        if peer_type is None or peer_type == "PressureLine":
            return (base[0] + METRICS.pilot_side_offset_x.get(node_type, 0.0), base[1])
        return base
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