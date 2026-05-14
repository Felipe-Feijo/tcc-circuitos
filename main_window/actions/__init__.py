from .file_actions import create_file_actions
from .view_actions import create_view_actions
from .edit_actions import create_edit_actions
from .mode_actions import create_mode_actions
from .help_actions import create_help_actions
from .simulation_actions import create_simulation_actions
from .generator_actions import create_generator_actions

def create_actions(main_window):
    actions = {}

    actions.update(create_file_actions(main_window))
    actions.update(create_view_actions(main_window))
    actions.update(create_edit_actions(main_window))
    actions.update(create_mode_actions(main_window))
    actions.update(create_help_actions(main_window))
    actions.update(create_simulation_actions(main_window))
    actions.update(create_generator_actions(main_window))

    return actions
