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
from PyQt6.QtWidgets import QMenu
from graphics.items.base.nodes.switch.contact import Contact
from graphics.items.base.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder
from graphics.items.base.nodes.directional_valve.valve_3_2_ways import Valve_3_2_Ways
from graphics.utils.defect_dialog import DefectDialog
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.utils.properties_dialog import PropertiesDialog


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


def test_node_item_context_menu_translates_across_subclasses_of_different_depths():
    """Regression test for a bug where NodeItem.extend_context_menu()'s
    self.tr(...) calls -- written in the NodeItem base class but invoked
    with self bound to whichever concrete subclass constructed the item --
    resolved their Qt translation context to the *subclass's* runtime
    class (e.g. "Contact", "DoubleActingCylinder", "Valve_3_2_Ways") at
    runtime, while pylupdate6's static scan attributed the same call sites
    to context "NodeItem". Since the pt_BR catalog only had these strings
    under "NodeItem", the lookup silently fell back to the untranslated
    English source for every one of ~20 node subclasses -- essentially
    every component type in the app. Fixed by routing these calls through
    QCoreApplication.translate("NodeItem", ...) instead of self.tr(...),
    which pins the context regardless of which subclass calls it.

    Covers three different inheritance depths: Contact (NodeItem direct
    subclass), DoubleActingCylinder (NodeItem -> CylinderItem ->
    DoubleActingCylinder), Valve_3_2_Ways (NodeItem -> DirectionalValveItem
    -> Valve_3_2_Ways)."""
    language_manager.apply_language(app, "pt_BR")
    try:
        for cls, domain in (
            (Contact, "electric"),
            (DoubleActingCylinder, "hydraulic"),
            (Valve_3_2_Ways, "hydraulic"),
        ):
            item = cls(domain=domain)
            menu = QMenu()
            item.extend_context_menu(menu)
            labels = [a.text() for a in menu.actions() if a.text()]
            assert "Propriedades..." in labels, f"{cls.__name__}: {labels}"
            assert "Girar 90°" in labels, f"{cls.__name__}: {labels}"
            assert "Adicionar label" in labels, f"{cls.__name__}: {labels}"
    finally:
        language_manager.apply_language(app, "en")


def test_defect_dialog_cancel_button_translates_despite_being_inherited():
    """Regression test for a bug where DefectDialog's Cancel button --
    built by PropertiesDialog.__init__ via self.tr("Cancel"), inherited
    unmodified by DefectDialog(PropertiesDialog) -- resolved its Qt
    translation context to "DefectDialog" at runtime (self's actual
    class), while pylupdate6 attributed the call site to context
    "PropertiesDialog" (where it's textually written). The pt_BR catalog
    had no "Cancel" entry under "DefectDialog", so the button silently
    stayed in English. Fixed by routing PropertiesDialog's own tr() calls
    through QCoreApplication.translate("PropertiesDialog", ...)."""
    language_manager.apply_language(app, "pt_BR")
    try:
        dialog = DefectDialog()
        assert dialog._cancel_btn.text() == "Cancelar"
        # Apply/Restore/title are DefectDialog's own tr() calls -- were
        # never broken, kept here as a sanity check they still work.
        assert dialog._ok_btn.text() == "Aplicar"
        assert dialog._restore_btn.text() == "Restaurar"
        assert dialog.windowTitle() == "Simular defeito"
    finally:
        language_manager.apply_language(app, "en")


def test_no_editable_properties_dialog_title_translates(monkeypatch):
    """Regression test for a bug where NodeItem._open_properties_dialog()'s
    no-properties fallback path built its dialog as
    PropertiesDialog(title="Properties") -- a hardcoded, never-translated
    string literal -- bypassing Task 8's title=None -> tr("Properties")
    default resolution entirely. Fixed by dropping the explicit argument
    so the dialog resolves its title via QCoreApplication.translate(...)
    fresh at construction time, like every other PropertiesDialog.

    Drives the real _open_properties_dialog() fallback branch end-to-end
    (not a hand-rebuilt copy of it) -- QDialog.exec() is monkeypatched to
    avoid blocking on a real modal loop in this headless test."""
    language_manager.apply_language(app, "pt_BR")
    try:
        item = JunctionNodeItem(domain="electric")
        assert item.build_properties_dialog() is None  # exercises the fallback branch

        captured = {}

        def fake_exec(self):
            captured["title"] = self.windowTitle()
            return 0  # QDialog.Rejected -- skips apply_properties_from_dialog()

        monkeypatch.setattr(PropertiesDialog, "exec", fake_exec)
        item._open_properties_dialog()

        assert captured["title"] == "Propriedades"
    finally:
        language_manager.apply_language(app, "en")
