# main_window/menus.py
def create_menus(main_window, actions):
    menubar = main_window.menuBar()

    file_menu = menubar.addMenu("File")
    file_menu.addAction(actions["new"])
    file_menu.addAction(actions["open"])
    file_menu.addAction(actions["save"])
    file_menu.addAction(actions["save_as"])
    file_menu.addSeparator()
    file_menu.addAction(actions["exit"])

    edit_menu = menubar.addMenu("Edit")
    edit_menu.addAction(actions["delete"])
    edit_menu.addAction(actions["copy"])
    edit_menu.addAction(actions["paste"])

    view_menu = menubar.addMenu("View")

    help_menu = menubar.addMenu("Help")
    help_menu.addAction(actions["about"])