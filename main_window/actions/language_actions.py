"""Language switch actions: English / Português (Brasil), mutually
exclusive. Deliberately NOT wrapped in tr() -- a language picker shows
each language's own name, not a translation of it, so the user can
always find their language regardless of the currently active one."""

from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QApplication

from main_window import language as _language_module
from main_window.language import apply_language


def create_language_actions(main_window) -> dict:
    actions = {}

    # Not parented to main_window: every other action factory in this
    # package (e.g. view_actions.create_view_actions) creates QActions
    # unparented too -- MainWindow._init_actions_ui() registers them via
    # addAction() afterwards. Keeping the same convention here also lets
    # this factory accept a plain test double for main_window (used only
    # for signal wiring, never as a Qt parent).
    group = QActionGroup(None)
    group.setExclusive(True)

    # Looked up as a module attribute (not `from ... import get_language`)
    # so tests can patch "main_window.language.get_language" and have it
    # take effect here.
    current = _language_module.get_language()

    actions["language_en"] = QAction("English")
    actions["language_en"].setCheckable(True)
    actions["language_en"].setChecked(current == "en")
    actions["language_en"].triggered.connect(
        lambda: apply_language(QApplication.instance(), "en")
    )
    group.addAction(actions["language_en"])

    actions["language_pt_br"] = QAction("Português (Brasil)")
    actions["language_pt_br"].setCheckable(True)
    actions["language_pt_br"].setChecked(current == "pt_BR")
    actions["language_pt_br"].triggered.connect(
        lambda: apply_language(QApplication.instance(), "pt_BR")
    )
    group.addAction(actions["language_pt_br"])

    # Nothing else holds a Python reference to `group` once this function
    # returns -- without one, Qt's own object stays alive only as long as
    # something keeps it referenced, and once garbage collected the two
    # actions silently stop being mutually exclusive. Anchoring it to
    # main_window keeps it alive for the app's lifetime.
    main_window._language_action_group = group

    return actions
