"""Simulation start errors are shown translated, naming the component by
its (translated) type and user-given name instead of class name + uuid."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication, QGraphicsScene

app = QApplication.instance() or QApplication([])

from main_window.language import language_manager
from main_window.ui.simulation_error_text import format_simulation_error
from simulation.simulation_session import SimulationSession
from graphics.items.base.nodes.relief_valve import ReliefValve
from graphics.items.base.nodes.pumps.centrifugal_pump import CentrifugalPump
from graphics.items.base.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder


@pytest.fixture
def pt_br():
    language_manager.apply_language(app, "pt_BR")
    yield
    language_manager.apply_language(app, "en")


def _start_error(*items):
    scene = QGraphicsScene()
    for item in items:
        scene.addItem(item)
    error = SimulationSession(scene).start()
    assert error is not None
    return error, scene


def _relief_without_p_set(name=""):
    relief = ReliefValve(domain="hydraulic")
    relief.name = name
    return relief


def test_missing_property_en():
    error, scene = _start_error(_relief_without_p_set())
    assert format_simulation_error(error, scene) == \
        "Relief Valve (direct): required property 'p_set' is not set."


def test_missing_property_pt_br_uses_component_name(pt_br):
    error, scene = _start_error(_relief_without_p_set("Alívio 1"))
    assert format_simulation_error(error, scene) == \
        "Válvula de Alívio (direta) 'Alívio 1': a propriedade obrigatória 'p_set' não foi definida."


def test_unconnected_pilot_port_pt_br(pt_br):
    relief = ReliefValve(domain="hydraulic")
    relief.properties["p_set"] = 1.5e7
    relief.properties["piloted"] = True
    relief.apply_properties()
    error, scene = _start_error(relief)
    assert format_simulation_error(error, scene) == \
        "Válvula de Alívio (direta): a porta 'Y' não está conectada a nada."


def test_must_be_positive_pt_br(pt_br):
    pump = CentrifugalPump(domain="hydraulic")
    pump.properties.update({"H_shutoff": 2e6, "Q_max": 0.0})
    error, scene = _start_error(pump)
    assert format_simulation_error(error, scene) == \
        "Bomba Centrífuga: a propriedade 'Q_max' deve ser maior que 0 (valor: 0)."


def test_rod_not_smaller_than_bore_pt_br(pt_br):
    cyl = DoubleActingCylinder(domain="hydraulic")
    cyl.properties.update({"bore": 0.05, "rod_diameter": 0.05, "stroke": 0.5})
    error, scene = _start_error(cyl)
    assert format_simulation_error(error, scene) == \
        "Cilindro de Dupla Ação: o diâmetro da haste (0.05) deve ser menor que " \
        "o diâmetro do êmbolo (0.05)."


def test_multiple_errors_one_per_line(pt_br):
    error, scene = _start_error(_relief_without_p_set("R1"), _relief_without_p_set("R2"))
    lines = sorted(format_simulation_error(error, scene).split("\n"))
    assert lines == [
        "Válvula de Alívio (direta) 'R1': a propriedade obrigatória 'p_set' não foi definida.",
        "Válvula de Alívio (direta) 'R2': a propriedade obrigatória 'p_set' não foi definida.",
    ]


def test_start_simulation_warning_title_is_translated(pt_br):
    from main_window.main_window import MainWindow
    window = MainWindow()
    try:
        window.retranslate_ui()
        window.scene.addItem(_relief_without_p_set())
        with patch("main_window.main_window.QMessageBox.warning") as warning:
            window.start_simulation()
        _, title, text = warning.call_args.args
        assert title == "Propriedades incompletas"
        assert text == "Válvula de Alívio (direta): a propriedade obrigatória 'p_set' não foi definida."
    finally:
        window.close()


def test_start_simulation_warning_title_en():
    from main_window.main_window import MainWindow
    window = MainWindow()
    try:
        window.scene.addItem(_relief_without_p_set())
        with patch("main_window.main_window.QMessageBox.warning") as warning:
            window.start_simulation()
        _, title, _ = warning.call_args.args
        assert title == "Incomplete properties"
    finally:
        window.close()
