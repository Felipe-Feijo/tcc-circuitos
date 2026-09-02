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
from graphics.items.base.nodes.coil.relay_coil import RelayCoil
from graphics.sensor_registry.sensor_registry import SensorRegistry
from graphics.utils.defect_dialog import DefectDialog
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.utils.properties_dialog import PropertiesDialog
import graphics.items.base.nodes.cylinder.cylinder_item as cylinder_item_module
import graphics.items.base.nodes.coil.coil_item as coil_item_module


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


def _find_submenu(menu, title):
    """Finds a submenu by its title among a QMenu's top-level actions."""
    for action in menu.actions():
        submenu = action.menu()
        if submenu is not None and submenu.title() == title:
            return submenu
    return None


def test_cylinder_item_context_menu_translates_when_inherited():
    """Regression test for the same inheritance-context bug Task 11 fixed
    for NodeItem/PropertiesDialog, found by the final whole-branch review
    still present in CylinderItem -- a base class never instantiated
    directly (only concrete subclasses like DoubleActingCylinder are).
    self.tr(...) calls written in CylinderItem's own methods
    (extend_context_menu) resolved their Qt translation context to the
    subclass's runtime class at runtime instead of "CylinderItem", so the
    pt_BR catalog (which pylupdate6 attributed to "CylinderItem") was
    never found and the strings silently stayed in English. Fixed by
    routing these calls through QCoreApplication.translate("CylinderItem", ...)."""
    language_manager.apply_language(app, "pt_BR")
    try:
        item = DoubleActingCylinder(domain="hydraulic")
        menu = QMenu()
        item.extend_context_menu(menu)

        assert _find_submenu(menu, "Sensor retraído") is not None
        assert _find_submenu(menu, "Sensor estendido") is not None

        state_menu = _find_submenu(menu, "Estado inicial")
        assert state_menu is not None
        labels = [a.text() for a in state_menu.actions()]
        assert "Retraído" in labels
        assert "Estendido" in labels
    finally:
        language_manager.apply_language(app, "en")


def test_cylinder_item_rename_error_dialog_translates_when_inherited(monkeypatch):
    """Same inheritance-context bug as above, for CylinderItem's
    rename-conflict QMessageBox.warning strings -- the only other
    self.tr() call sites in the class."""
    language_manager.apply_language(app, "pt_BR")
    try:
        registry = SensorRegistry()
        item = DoubleActingCylinder(domain="hydraulic", sensor_registry=registry)
        item.set_sensor("retracted", "reed")
        item.set_sensor("extended", "reed")

        captured = {}

        def fake_warning(parent, title, text):
            captured["title"] = title
            captured["text"] = text

        monkeypatch.setattr(cylinder_item_module.QMessageBox, "warning", fake_warning)

        conflicting_name = item.properties["sensors"]["extended"]["name"]
        item._set_sensor_name("retracted", conflicting_name)

        assert captured["title"] == "Erro ao renomear sensor"
        assert captured["text"] == f"Já existe um sensor com o nome '{conflicting_name}'."
    finally:
        language_manager.apply_language(app, "en")


def test_directional_valve_item_context_menu_translates_when_inherited():
    """Same inheritance-context bug as above, for DirectionalValveItem -- a
    base class never instantiated directly (only concrete subclasses like
    Valve_3_2_Ways are)."""
    language_manager.apply_language(app, "pt_BR")
    try:
        item = Valve_3_2_Ways(domain="hydraulic")
        menu = QMenu()
        item.extend_context_menu(menu)

        assert _find_submenu(menu, "Atuador esquerdo") is not None
        assert _find_submenu(menu, "Atuador direito") is not None

        rest_menu = _find_submenu(menu, "Posição padrão")
        assert rest_menu is not None
        labels = [a.text() for a in rest_menu.actions()]
        assert "Direita (0)" in labels
        assert "Esquerda (1)" in labels
    finally:
        language_manager.apply_language(app, "en")


def _form_label_texts(dialog):
    """Reads the QFormLayout label texts of a PropertiesDialog/DefectDialog."""
    from PyQt6.QtWidgets import QFormLayout
    labels = []
    for i in range(dialog._form_layout.rowCount()):
        item = dialog._form_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
        if item and item.widget():
            labels.append(item.widget().text())
    return labels


def test_directional_valve_item_defect_dialog_translates():
    """Finding 2: build_defect_dialog() had raw, un-migrated Portuguese
    literals (dialog title + 2 field labels) that never went through
    tr()/translate() at all -- so they stayed in Portuguese even while the
    app language was English. Fixed by wrapping them in
    QCoreApplication.translate("DirectionalValveItem", ...), consistent
    with Finding 1's fix for this same class."""
    item = Valve_3_2_Ways(domain="hydraulic")

    language_manager.apply_language(app, "en")
    dialog_en = item.build_defect_dialog()
    try:
        assert dialog_en.windowTitle() == "Simulate defect — Valve 3/2 Ways"
        labels = _form_label_texts(dialog_en)
        assert "Conductance k (m³/s/√Pa)" in labels
        assert "Valve stuck (won't switch)" in labels
    finally:
        dialog_en.close()

    language_manager.apply_language(app, "pt_BR")
    try:
        dialog_pt = item.build_defect_dialog()
        try:
            assert dialog_pt.windowTitle() == "Simular defeito — Válvula 3/2 Vias"
            labels = _form_label_texts(dialog_pt)
            assert "Condutância k (m³/s/√Pa)" in labels
            assert "Válvula travada (não comuta)" in labels
        finally:
            dialog_pt.close()
    finally:
        language_manager.apply_language(app, "en")


def test_coil_item_rename_error_dialog_translates_when_inherited(monkeypatch):
    """Same inheritance-context bug as above, for CoilItem -- a base class
    never instantiated directly (only concrete subclasses like RelayCoil
    and SolenoidCoil are). The rename-conflict QMessageBox.warning strings
    are the only self.tr() call sites in the class."""
    language_manager.apply_language(app, "pt_BR")
    try:
        registry = SensorRegistry()
        coil1 = RelayCoil(domain="electric", sensor_registry=registry)
        coil2 = RelayCoil(domain="electric", sensor_registry=registry)
        coil1.register_sensors()
        coil2.register_sensors()

        captured = {}

        def fake_warning(parent, title, text):
            captured["title"] = title
            captured["text"] = text

        monkeypatch.setattr(coil_item_module.QMessageBox, "warning", fake_warning)

        conflicting_name = coil2.sensors["coil"]["name"]
        coil1._set_sensor_name(conflicting_name)

        assert captured["title"] == "Erro ao renomear"
        assert captured["text"] == f"Já existe um sinal com o nome '{conflicting_name}'."
    finally:
        language_manager.apply_language(app, "en")
