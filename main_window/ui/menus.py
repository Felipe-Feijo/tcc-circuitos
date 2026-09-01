"""Builds the main window menu bar from the created actions."""


def create_menus(main_window, actions) -> dict:
    menubar = main_window.menuBar()

    file_menu = menubar.addMenu(main_window.tr("File"))
    file_menu.addAction(actions["new"])
    file_menu.addAction(actions["open"])
    file_menu.addAction(actions["save"])
    file_menu.addAction(actions["save_as"])
    file_menu.addSeparator()
    file_menu.addAction(actions["new_from_sequence"])
    file_menu.addSeparator()
    file_menu.addAction(actions["exit"])

    edit_menu = menubar.addMenu(main_window.tr("Edit"))
    edit_menu.addAction(actions["undo"])
    edit_menu.addAction(actions["redo"])
    edit_menu.addSeparator()
    edit_menu.addAction(actions["delete"])
    edit_menu.addAction(actions["copy"])
    edit_menu.addAction(actions["paste"])

    view_menu = menubar.addMenu(main_window.tr("View"))
    view_menu.addAction(actions["toggle_theme"])
    view_menu.addAction(actions["zoom_in"])
    view_menu.addAction(actions["zoom_out"])
    view_menu.addAction(actions["zoom_fit"])
    view_menu.addSeparator()
    view_menu.addAction(actions["font_size"])
    view_menu.addSeparator()
    lang_menu = view_menu.addMenu(main_window.tr("Language"))
    lang_menu.addAction(actions["language_en"])
    lang_menu.addAction(actions["language_pt_br"])

    help_menu = menubar.addMenu(main_window.tr("Help"))
    help_menu.addAction(actions["about"])

    return {
        "file": file_menu,
        "edit": edit_menu,
        "view": view_menu,
        "help": help_menu,
        "language": lang_menu,
    }
