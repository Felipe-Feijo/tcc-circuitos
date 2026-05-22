"""Constrói a barra de menus da janela principal a partir das ações criadas."""


def create_menus(main_window, actions):
    menubar = main_window.menuBar()

    file_menu = menubar.addMenu("File")
    file_menu.addAction(actions["new"])
    file_menu.addAction(actions["open"])
    file_menu.addAction(actions["save"])
    file_menu.addAction(actions["save_as"])
    file_menu.addSeparator()
    file_menu.addAction(actions["new_from_sequence"])
    file_menu.addSeparator()
    file_menu.addAction(actions["exit"])

    edit_menu = menubar.addMenu("Edit")
    edit_menu.addAction(actions["delete"])
    edit_menu.addAction(actions["copy"])
    edit_menu.addAction(actions["paste"])

    view_menu = menubar.addMenu("View")
    view_menu.addAction(actions["toggle_theme"])
    view_menu.addAction(actions["zoom_in"])
    view_menu.addAction(actions["zoom_out"])
    view_menu.addAction(actions["zoom_fit"])

    help_menu = menubar.addMenu("Help")
    help_menu.addAction(actions["about"])
