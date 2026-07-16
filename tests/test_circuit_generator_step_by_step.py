"""Testes de integração: circuit_generator.generate_and_load despacha
pro motor de layout certo por (method, sub_type) -- ver
docs/superpowers/specs/2026-07-11-step-by-step-positioning-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.circuit_generator import LAYOUT_MAP
from circuit_generator import cascade_layout, step_by_step_layout


class TestLayoutDispatch:
    def test_cascade_maps_to_the_grid_based_cascade_layout(self):
        # Migrated in Task 7 of the cascade-grid-layout plan: cascade now
        # routes through circuit_generator.cascade_layout.apply instead of
        # the legacy layout_engine.apply. layout_engine.py itself is left
        # untouched in the repo (kept for easy rollback), it's just no
        # longer referenced by LAYOUT_MAP for the cascade method.
        assert LAYOUT_MAP[("cascade", None)] is cascade_layout.apply

    def test_step_by_step_pneumatic_maps_to_new_layout(self):
        assert LAYOUT_MAP[("step_by_step", "pneumatic")] is step_by_step_layout.apply
