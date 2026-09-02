import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from unittest.mock import Mock

from main_window.language import language_manager
from main_window.main_window import MainWindow
from editor.mode import EditorMode
from simulation.simulation_session import SimulationSession


def test_switching_to_pt_br_translates_a_known_menu_title():
    window = MainWindow()
    try:
        language_manager.apply_language(app, "pt_BR")
        window.retranslate_ui()
        assert window.menus["file"].title() == "Arquivo"
    finally:
        language_manager.apply_language(app, "en")
        window.close()


def test_toggle_theme_text_stays_translated_after_a_theme_change():
    """Regression test for a bug where set_light_theme() set the
    toggle_theme action's text via a hardcoded English literal instead of
    tr(...), so it silently reverted to English on every theme toggle
    while pt_BR was active, even though retranslate_ui() had just set it
    correctly."""
    window = MainWindow()
    try:
        language_manager.apply_language(app, "pt_BR")
        window.retranslate_ui()

        window.set_light_theme(True)
        assert window.actions["toggle_theme"].text() == "Tema Claro"

        window.set_light_theme(False)
        assert window.actions["toggle_theme"].text() == "Tema Escuro"
    finally:
        language_manager.apply_language(app, "en")
        window.close()


def test_run_action_text_stays_translated_after_a_simulation_state_change():
    """Regression test for a bug where update_simulation_actions() set the
    run action's text via hardcoded English literals ("Run"/"Pause")
    instead of tr(...), so it silently reverted to English on every
    simulation state change while pt_BR was active."""
    window = MainWindow()
    try:
        language_manager.apply_language(app, "pt_BR")
        window.retranslate_ui()

        # Not-in-simulation branch.
        window.update_simulation_actions()
        assert window.actions["run"].text() == "Executar"

        # In-simulation, playing branch.
        window.state.mode = EditorMode.SIMULATE
        window.simulation = Mock(
            active=True,
            dt=0.1,  # real float: retranslate_ui() formats this ("dt: {0:.3f}s")
            controller=Mock(playing=True, can_step_back=lambda: False),
        )
        window.update_simulation_actions()
        assert window.actions["run"].text() == "Pausar"

        # In-simulation, paused branch.
        window.simulation.controller.playing = False
        window.update_simulation_actions()
        assert window.actions["run"].text() == "Executar"
    finally:
        # window.simulation is a Mock at this point; apply_language() below
        # re-triggers retranslate_ui() via the language_changed signal, which
        # touches simulation.dt -- restore a real session first so that
        # formatting doesn't blow up during teardown.
        window.simulation = SimulationSession(window.scene)
        language_manager.apply_language(app, "en")
        window.close()
