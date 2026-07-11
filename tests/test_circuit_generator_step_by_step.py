"""Testes de integração: circuit_generator.generate_and_load despacha
pro motor de layout certo por (method, sub_type) -- ver
docs/superpowers/specs/2026-07-11-step-by-step-positioning-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.circuit_generator import LAYOUT_MAP
from circuit_generator import layout_engine, step_by_step_layout


class TestLayoutDispatch:
    def test_cascade_still_maps_to_layout_engine(self):
        assert LAYOUT_MAP[("cascade", None)] is layout_engine.apply

    def test_step_by_step_pneumatic_maps_to_new_layout(self):
        assert LAYOUT_MAP[("step_by_step", "pneumatic")] is step_by_step_layout.apply
