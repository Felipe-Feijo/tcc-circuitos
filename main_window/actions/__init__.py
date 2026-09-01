"""Aggregates and exports the factory function for all main window actions."""

from .file_actions import create_file_actions
from .view_actions import create_view_actions
from .edit_actions import create_edit_actions
from .mode_actions import create_mode_actions
from .help_actions import create_help_actions
from .simulation_actions import create_simulation_actions
from .generator_actions import create_generator_actions
from .language_actions import create_language_actions

def create_actions(main_window):
    actions = {}

    actions.update(create_file_actions(main_window))
    actions.update(create_view_actions(main_window))
    actions.update(create_edit_actions(main_window))
    actions.update(create_mode_actions(main_window))
    actions.update(create_help_actions(main_window))
    actions.update(create_simulation_actions(main_window))
    actions.update(create_generator_actions(main_window))
    actions.update(create_language_actions(main_window))

    return actions


def retranslate_actions(actions: dict, main_window) -> None:
    """Re-applies tr() text to every action after a language change.

    Static labels are just re-set. A few actions carry state baked into
    their text (theme name, current dt, run/pause) -- those are recomputed
    from main_window's current state rather than reset to a fixed default.
    """
    actions["new"].setText(main_window.tr("New"))
    actions["open"].setText(main_window.tr("Open"))
    actions["save"].setText(main_window.tr("Save"))
    actions["save_as"].setText(main_window.tr("Save As"))
    actions["exit"].setText(main_window.tr("Exit"))

    actions["zoom_in"].setText(main_window.tr("Zoom In"))
    actions["zoom_out"].setText(main_window.tr("Zoom Out"))
    actions["zoom_fit"].setText(main_window.tr("Fit to Contents"))
    actions["font_size"].setText(main_window.tr("Font Size..."))

    actions["delete"].setText(main_window.tr("Delete"))
    actions["copy"].setText(main_window.tr("Copy"))
    actions["paste"].setText(main_window.tr("Paste"))
    actions["open_palette"].setText(main_window.tr("Add"))
    actions["undo"].setText(main_window.tr("Undo"))
    actions["redo"].setText(main_window.tr("Redo"))
    actions["rotate"].setText(main_window.tr("Rotate 90°"))
    actions["rotate"].setToolTip(
        main_window.tr("Rotate selected component 90° clockwise (R)")
    )

    actions["mode_select"].setText(main_window.tr("Select"))
    actions["mode_connect"].setText(main_window.tr("Connect"))
    actions["mode_simulate"].setText(main_window.tr("Simulate"))

    actions["about"].setText(main_window.tr("About"))

    actions["step_back"].setText(main_window.tr("Step Back"))
    actions["step_forward"].setText(main_window.tr("Step Forward"))

    actions["new_from_sequence"].setText(main_window.tr("New from Sequence..."))

    # -- Stateful text --
    use_light_theme = getattr(main_window, "use_light_theme", False)
    actions["toggle_theme"].setText(
        main_window.tr("Light Theme") if not use_light_theme else main_window.tr("Dark Theme")
    )

    simulation = getattr(main_window, "simulation", None)
    if simulation is not None:
        actions["dt"].setText(main_window.tr("dt: {0:.3f}s").format(simulation.dt))

    # "run"'s text/enabled state depends on simulation play state, which
    # update_simulation_actions() already fully recomputes -- avoid
    # duplicating that logic here.
    if hasattr(main_window, "update_simulation_actions"):
        main_window.update_simulation_actions()
