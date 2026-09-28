"""Tests the shared _init_hydraulic_k() helper (DirectionalValve base) and
that all 5 concrete directional valves restore k via DefectMixin."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from simulation.nodes.directional_valve.valve_2_2_ways import Valve_2_2_Ways
from simulation.nodes.directional_valve.valve_3_2_ways import Valve_3_2_Ways
from simulation.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways
from simulation.nodes.directional_valve.valve_4_3_ways import Valve_4_3_Ways
from simulation.nodes.directional_valve.valve_5_2_ways import Valve_5_2_Ways

ALL_HYDRAULIC_VALVE_CLASSES = [
    Valve_2_2_Ways, Valve_3_2_Ways, Valve_4_2_Ways, Valve_4_3_Ways, Valve_5_2_Ways,
]


@pytest.mark.parametrize("cls", ALL_HYDRAULIC_VALVE_CLASSES)
def test_missing_k_raises_value_error_naming_the_class(cls):
    with pytest.raises(ValueError, match=cls.__name__):
        cls(cls.__name__, domain="hydraulic", properties={})


@pytest.mark.parametrize("cls", ALL_HYDRAULIC_VALVE_CLASSES)
def test_k_set_on_construction_and_no_defect_active(cls):
    valve = cls("v", domain="hydraulic", properties={"k": 1e-7})
    assert valve.k == 1e-7
    assert valve.defect_active is False


@pytest.mark.parametrize("cls", ALL_HYDRAULIC_VALVE_CLASSES)
def test_set_defect_then_clear_defect_restores_k(cls):
    valve = cls("v", domain="hydraulic", properties={"k": 1e-7})
    valve.handle_command({"action": "set_defect", "k": 5e-8, "stuck": False})
    assert valve.k == 5e-8
    assert valve.defect_active is True

    valve.handle_command({"action": "clear_defect"})
    assert valve.k == 1e-7
    assert valve.defect_active is False


@pytest.mark.parametrize("cls", ALL_HYDRAULIC_VALVE_CLASSES)
def test_pneumatic_domain_never_sets_k(cls):
    valve = cls("v", domain="pneumatic", properties={})
    assert not hasattr(valve, "k")
