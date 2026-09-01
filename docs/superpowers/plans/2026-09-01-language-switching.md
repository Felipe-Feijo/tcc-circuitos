# Language Switching (EN / PT-BR) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a runtime-switchable English / Portuguese (Brazil) language option to the CircuitEditor PyQt6 desktop app, replacing today's inconsistent mix of hardcoded EN/PT strings.

**Architecture:** Qt Linguist (`tr()` + `.ts`/`.qm`), English as the `tr()` source language, a small `LanguageManager` (mirrors the existing `main_window/settings.py` persistence pattern) that installs a `QTranslator` and emits a `language_changed` signal. Only long-lived widgets (menus, toolbars, actions, docks, palette) implement `retranslate_ui()` hooks wired to that signal; transient dialogs pick up the active language automatically because they're rebuilt from scratch on every open.

**Tech Stack:** Python 3.12, PyQt6 6.10, `pylupdate6` (bundled with PyQt6) for string extraction, `pyside6-lrelease` (PySide6, dev-only dependency) for `.ts`→`.qm` compilation, pytest (existing convention: no pytest-qt, each test file does `QApplication.instance() or QApplication([])` at module level).

**Spec:** [docs/superpowers/specs/2026-09-01-language-switching-design.md](../specs/2026-09-01-language-switching-design.md)

## Global Constraints

- Source language for every `tr(...)` call is English. Strings currently in Portuguese are rewritten to English in the code; the original Portuguese text becomes the ready-made `pt_BR.ts` translation (no extra translation effort for those).
- Strings that are already English still need a Portuguese translation written into `pt_BR.ts` (Task 10).
- Never wrap a string in `tr()` at module scope, in a mutable default parameter value, or anywhere else evaluated once at import/definition time — always inside the method/function body that runs per-call. (`PropertiesDialog`/`DefectDialog` default titles need a `None`-sentinel fix for this — Task 8.)
- `QObject`/`QWidget`/`QGraphicsObject` subclasses use `self.tr("...")`. Plain classes and module-level functions (`SceneFileSession`, `resolve_report`, `main_window/settings.py`'s module functions) use `QCoreApplication.translate("Context", "...")`.
- The two language-picker labels ("English" / "Português (Brasil)") are never wrapped in `tr()` — a language switcher conventionally shows each language's own name, not a translation of it.
- Any existing test that asserts on an exact string being migrated must be updated in the same task, to the new English text.
- Out of scope for this plan (documented, not silently dropped — see Task 12): the per-node-type property-dialog field labels and `palette_meta(name=...)` display strings scattered across `graphics/items/base/nodes/**` (dozens of files). Task 12 produces a tracked inventory for a follow-up sweep instead of migrating them here, per the spec's non-goal on 100% v1 coverage.

---

## Task 1: i18n toolchain and resource scaffold

**Files:**
- Create: `resources/i18n/` (empty dir, holds `.ts`/`.qm` later)
- Create: `scripts/compile_translations.py`
- Create: `requirements-dev.in`, `requirements-dev.txt`
- Test: `tests/test_compile_translations.py`

**Interfaces:**
- Produces: `scripts/compile_translations.py` exposes `compile_all(i18n_dir: Path) -> list[Path]` (compiles every `.ts` in `i18n_dir` to a sibling `.qm`, returns the list of `.qm` paths written) and is runnable as `python scripts/compile_translations.py`.

`pylupdate6` (extracts `.ts` from `tr()` calls) is already in the venv (`venv/Scripts/pylupdate6.exe`), but the venv has no `lrelease` (`.ts`→`.qm` compiler — not bundled with the `PyQt6` pip wheel). `PySide6` wheels reliably bundle Qt's official `lrelease` as a console script (`pyside6-lrelease`), so it's added as a **dev-only** dependency, used solely by this build script — never imported by the app itself, and not part of `requirements.txt`/`requirements.in` (which stay PyQt6-only) or the PyInstaller bundle.

- [ ] **Step 1: Add the dev-only requirements files**

`requirements-dev.in`:
```
# Dev-only tools, not shipped in the packaged app.
# PySide6 is installed solely for its bundled `pyside6-lrelease` binary,
# used by scripts/compile_translations.py to compile .ts -> .qm.
-r requirements.in
pyside6
```

Run: `pip-compile requirements-dev.in` (from the project venv) to produce `requirements-dev.txt`, then `pip install -r requirements-dev.txt`.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_compile_translations.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
from scripts.compile_translations import compile_all

_SAMPLE_TS = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="pt_BR">
<context>
    <name>Sample</name>
    <message>
        <source>Hello</source>
        <translation>Olá</translation>
    </message>
</context>
</TS>
"""


def test_compile_all_produces_one_qm_per_ts():
    with tempfile.TemporaryDirectory() as tmp:
        i18n_dir = Path(tmp)
        (i18n_dir / "sample_pt_BR.ts").write_text(_SAMPLE_TS, encoding="utf-8")

        produced = compile_all(i18n_dir)

        assert produced == [i18n_dir / "sample_pt_BR.qm"]
        assert (i18n_dir / "sample_pt_BR.qm").exists()
        assert (i18n_dir / "sample_pt_BR.qm").stat().st_size > 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_compile_translations.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'` (or `scripts.compile_translations`)

- [ ] **Step 4: Implement `scripts/compile_translations.py`**

```python
"""Compiles every Qt Linguist .ts source file under resources/i18n into a
sibling .qm binary catalog, via the pyside6-lrelease console script.

Dev-only tool: requires requirements-dev.txt (PySide6) to be installed.
Not used by the packaged app, which only ever reads the committed .qm files.
"""

import shutil
import subprocess
import sys
from pathlib import Path

_I18N_DIR = Path(__file__).resolve().parent.parent / "resources" / "i18n"


def _lrelease_executable() -> str:
    exe = shutil.which("pyside6-lrelease")
    if not exe:
        raise FileNotFoundError(
            "pyside6-lrelease not found on PATH. Install dev dependencies: "
            "pip install -r requirements-dev.txt"
        )
    return exe


def compile_all(i18n_dir: Path = _I18N_DIR) -> list[Path]:
    """Compiles every *.ts file in i18n_dir to a sibling *.qm. Returns the
    list of .qm paths written, in the same order as the .ts files found."""
    lrelease = _lrelease_executable()
    produced = []
    for ts_path in sorted(i18n_dir.glob("*.ts")):
        qm_path = ts_path.with_suffix(".qm")
        subprocess.run(
            [lrelease, str(ts_path), "-qm", str(qm_path)],
            check=True,
            capture_output=True,
        )
        produced.append(qm_path)
    return produced


if __name__ == "__main__":
    written = compile_all()
    for path in written:
        print(f"compiled {path}")
    sys.exit(0)
```

Create `scripts/__init__.py` (empty) so `scripts.compile_translations` is importable from tests.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_compile_translations.py -v`
Expected: PASS (requires `pip install -r requirements-dev.txt` first, per Step 1)

- [ ] **Step 6: Create the empty resource directory and commit**

```bash
mkdir -p resources/i18n
touch resources/i18n/.gitkeep
git add scripts/compile_translations.py scripts/__init__.py tests/test_compile_translations.py requirements-dev.in requirements-dev.txt resources/i18n/.gitkeep
git commit -m "build: add Qt Linguist compile-translations dev tool"
```

---

## Task 2: LanguageManager module

**Files:**
- Create: `main_window/language.py`
- Test: `tests/test_language_manager.py`

**Interfaces:**
- Consumes: nothing new (uses `PyQt6.QtCore.{QObject, QLocale, QSettings, QTranslator, pyqtSignal}`, `PyQt6.QtWidgets.QApplication`)
- Produces: `SUPPORTED_LANGUAGES: tuple[str, ...]` = `("en", "pt_BR")`, `DEFAULT_LANGUAGE: str` = `"en"`, `detect_system_language() -> str`, `get_language(settings: QSettings | None = None) -> str`, `class LanguageManager(QObject)` with signal `language_changed(str)` and method `apply_language(self, app: QApplication, code: str, settings: QSettings | None = None) -> None`, module-level singleton `language_manager: LanguageManager`, and convenience function `apply_language(app, code, settings=None) -> None` that delegates to it. Later tasks import `from main_window.language import language_manager, apply_language, get_language`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_language_manager.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from unittest.mock import patch
from PyQt6.QtCore import QSettings
from main_window.language import (
    LanguageManager, get_language, detect_system_language, DEFAULT_LANGUAGE,
)


def _fresh_settings() -> QSettings:
    s = QSettings("tcc-circuitos-tests", "LanguageManagerTests")
    s.clear()
    return s


def test_detect_system_language_recognizes_pt_br():
    with patch("main_window.language.QLocale") as mock_locale:
        mock_locale.system.return_value.name.return_value = "pt_BR"
        assert detect_system_language() == "pt_BR"


def test_detect_system_language_falls_back_to_english():
    with patch("main_window.language.QLocale") as mock_locale:
        mock_locale.system.return_value.name.return_value = "fr_FR"
        assert detect_system_language() == DEFAULT_LANGUAGE


def test_get_language_uses_system_detection_when_unset():
    settings = _fresh_settings()
    with patch("main_window.language.detect_system_language", return_value="pt_BR"):
        assert get_language(settings) == "pt_BR"


def test_get_language_prefers_persisted_value_over_system_detection():
    settings = _fresh_settings()
    settings.setValue("ui/language", "pt_BR")
    with patch("main_window.language.detect_system_language", return_value="en"):
        assert get_language(settings) == "pt_BR"


def test_apply_language_persists_choice_and_emits_signal():
    settings = _fresh_settings()
    manager = LanguageManager()
    received = []
    manager.language_changed.connect(received.append)

    with patch("main_window.language.QTranslator") as mock_translator_cls:
        mock_translator_cls.return_value.load.return_value = True
        manager.apply_language(app, "pt_BR", settings)

    assert settings.value("ui/language") == "pt_BR"
    assert received == ["pt_BR"]


def test_apply_language_english_needs_no_qm_file():
    settings = _fresh_settings()
    manager = LanguageManager()
    manager.apply_language(app, "en", settings)  # must not try to load a .qm
    assert settings.value("ui/language") == "en"


def test_apply_language_rejects_unsupported_code():
    settings = _fresh_settings()
    manager = LanguageManager()
    try:
        manager.apply_language(app, "fr", settings)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_apply_language_removes_previous_translator_before_installing_new_one():
    settings = _fresh_settings()
    manager = LanguageManager()

    with patch("main_window.language.QTranslator") as mock_translator_cls:
        mock_translator_cls.return_value.load.return_value = True
        manager.apply_language(app, "pt_BR", settings)
        first_translator = manager._translator
        manager.apply_language(app, "en", settings)

    assert manager._translator is None
    # can't easily assert app.removeTranslator was called on a real
    # QApplication without a live translator; behavioral coverage for the
    # swap itself is exercised in Task 3's end-to-end MainWindow test.
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_language_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'main_window.language'`

- [ ] **Step 3: Implement `main_window/language.py`**

```python
"""Runtime language switching (English / Portuguese-Brazil) via Qt Linguist.

Mirrors the persistence pattern already used by main_window/settings.py
(QSettings-backed, module-level get/apply functions).
"""

from pathlib import Path

from PyQt6.QtCore import QLocale, QObject, QSettings, QTranslator, pyqtSignal
from PyQt6.QtWidgets import QApplication

SUPPORTED_LANGUAGES = ("en", "pt_BR")
DEFAULT_LANGUAGE = "en"

_LANGUAGE_KEY = "ui/language"
_I18N_DIR = Path(__file__).resolve().parent.parent / "resources" / "i18n"


def _default_settings() -> QSettings:
    return QSettings("tcc-circuitos", "CircuitEditor")


def detect_system_language() -> str:
    """Returns "pt_BR" if the OS locale is Portuguese-Brazil, else "en"."""
    system_name = QLocale.system().name()  # e.g. "pt_BR", "en_US"
    return "pt_BR" if system_name.startswith("pt_BR") else DEFAULT_LANGUAGE


def get_language(settings: QSettings | None = None) -> str:
    """Returns the persisted language, or an OS-derived default if unset."""
    s = settings or _default_settings()
    stored = s.value(_LANGUAGE_KEY, None)
    if stored in SUPPORTED_LANGUAGES:
        return str(stored)
    return detect_system_language()


class LanguageManager(QObject):
    """Holds the currently installed QTranslator and notifies listeners
    (persistent widgets' retranslate_ui()) after a language switch."""

    language_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._translator: QTranslator | None = None

    def apply_language(
        self, app: QApplication, code: str, settings: QSettings | None = None
    ) -> None:
        if code not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language code: {code!r}")

        if self._translator is not None:
            app.removeTranslator(self._translator)
            self._translator = None

        # English needs no .qm: its tr() text IS the source text already.
        if code != DEFAULT_LANGUAGE:
            translator = QTranslator()
            qm_path = _I18N_DIR / f"circuiteditor_{code}.qm"
            if not translator.load(str(qm_path)):
                raise FileNotFoundError(
                    f"Translation file not found or invalid: {qm_path}"
                )
            app.installTranslator(translator)
            self._translator = translator

        s = settings or _default_settings()
        s.setValue(_LANGUAGE_KEY, code)

        self.language_changed.emit(code)


language_manager = LanguageManager()


def apply_language(
    app: QApplication, code: str, settings: QSettings | None = None
) -> None:
    """Convenience wrapper around the shared LanguageManager singleton."""
    language_manager.apply_language(app, code, settings)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_language_manager.py -v`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Commit**

```bash
git add main_window/language.py tests/test_language_manager.py
git commit -m "feat: add LanguageManager for runtime EN/PT-BR switching"
```

---

## Task 3: Wire LanguageManager into app startup, MainWindow, and a Language menu

**Files:**
- Modify: `app.py`
- Modify: `main_window/main_window.py`
- Modify: `main_window/ui/menus.py`
- Modify: `main_window/actions/__init__.py`
- Create: `main_window/actions/language_actions.py`
- Test: `tests/test_language_actions.py`
- Test: `tests/test_main_window_retranslate_wiring.py`

**Interfaces:**
- Consumes: `main_window.language.{language_manager, apply_language, get_language}` (Task 2)
- Produces: `create_language_actions(main_window) -> dict` with keys `"language_en"`, `"language_pt_br"` (both `QAction`, checkable, mutually exclusive via a `QActionGroup`); `MainWindow.retranslate_ui(self) -> None` (empty body for now — later tasks add to it) connected to `language_manager.language_changed`; `create_menus(main_window, actions) -> dict[str, QMenu]` (changed return type — was `None`) with keys `"file"`, `"edit"`, `"view"`, `"help"`, `"language"`, stored as `main_window.menus`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_language_actions.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from unittest.mock import Mock, patch
from main_window.actions.language_actions import create_language_actions


def test_creates_checkable_mutually_exclusive_language_actions():
    fake_main_window = Mock()
    with patch("main_window.language.get_language", return_value="en"):
        actions = create_language_actions(fake_main_window)

    assert set(actions) == {"language_en", "language_pt_br"}
    assert actions["language_en"].text() == "English"
    assert actions["language_pt_br"].text() == "Português (Brasil)"
    assert actions["language_en"].isCheckable()
    assert actions["language_en"].isChecked()
    assert not actions["language_pt_br"].isChecked()


def test_triggering_pt_br_action_applies_pt_br_language():
    fake_main_window = Mock()
    with patch("main_window.language.get_language", return_value="en"):
        actions = create_language_actions(fake_main_window)

    with patch("main_window.actions.language_actions.apply_language") as mock_apply:
        actions["language_pt_br"].trigger()
        mock_apply.assert_called_once()
        assert mock_apply.call_args.args[1] == "pt_BR"
```

```python
# tests/test_main_window_retranslate_wiring.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from unittest.mock import patch
from main_window.main_window import MainWindow
from main_window.language import language_manager


def test_language_change_triggers_main_window_retranslate():
    window = MainWindow()
    try:
        with patch.object(window, "retranslate_ui") as mock_retranslate:
            language_manager.language_changed.emit("en")
            mock_retranslate.assert_called_once()
    finally:
        window.close()


def test_main_window_exposes_menus_dict():
    window = MainWindow()
    try:
        assert set(window.menus) == {"file", "edit", "view", "help", "language"}
    finally:
        window.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_language_actions.py tests/test_main_window_retranslate_wiring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'main_window.actions.language_actions'`, and `AttributeError: 'MainWindow' object has no attribute 'menus'`

- [ ] **Step 3: Implement `main_window/actions/language_actions.py`**

```python
"""Language switch actions: English / Português (Brasil), mutually
exclusive. Deliberately NOT wrapped in tr() -- a language picker shows
each language's own name, not a translation of it, so the user can
always find their language regardless of the currently active one."""

from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QApplication

from main_window.language import apply_language, get_language


def create_language_actions(main_window) -> dict:
    actions = {}

    group = QActionGroup(main_window)
    group.setExclusive(True)

    current = get_language()

    actions["language_en"] = QAction("English", main_window)
    actions["language_en"].setCheckable(True)
    actions["language_en"].setChecked(current == "en")
    actions["language_en"].triggered.connect(
        lambda: apply_language(QApplication.instance(), "en")
    )
    group.addAction(actions["language_en"])

    actions["language_pt_br"] = QAction("Português (Brasil)", main_window)
    actions["language_pt_br"].setCheckable(True)
    actions["language_pt_br"].setChecked(current == "pt_BR")
    actions["language_pt_br"].triggered.connect(
        lambda: apply_language(QApplication.instance(), "pt_BR")
    )
    group.addAction(actions["language_pt_br"])

    return actions
```

- [ ] **Step 4: Register it in the actions aggregator**

Edit `main_window/actions/__init__.py`:

```python
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
```

- [ ] **Step 5: Change `create_menus` to return the menu dict, and add the Language submenu**

Edit `main_window/ui/menus.py`:

```python
"""Builds the main window menu bar from the created actions."""


def create_menus(main_window, actions) -> dict:
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
    edit_menu.addAction(actions["undo"])
    edit_menu.addAction(actions["redo"])
    edit_menu.addSeparator()
    edit_menu.addAction(actions["delete"])
    edit_menu.addAction(actions["copy"])
    edit_menu.addAction(actions["paste"])

    view_menu = menubar.addMenu("View")
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

    help_menu = menubar.addMenu("Help")
    help_menu.addAction(actions["about"])

    return {
        "file": file_menu,
        "edit": edit_menu,
        "view": view_menu,
        "help": help_menu,
        "language": lang_menu,
    }
```

(The four top-level titles — `"File"`, `"Edit"`, `"View"`, `"Help"` — are wrapped in `tr()` together with `toolbars.py` and the rest of `main_window.py` in Task 5, which is also where `MainWindow.retranslate_ui()` gets the logic to re-apply them; this task only needs the dict of menu references to exist so that later wiring has something to call `.setTitle()` on.)

- [ ] **Step 6: Apply the language before `MainWindow` is constructed**

Edit `app.py`:

```python
from PyQt6.QtWidgets import QApplication
from main_window.main_window import MainWindow
from main_window import settings
from main_window import language

faulthandler.enable()

app = QApplication(sys.argv)
settings.apply_font_from_settings(app)
language.apply_language(app, language.get_language())

window = MainWindow()
window.resize(800, 600)
window.show()

sys.exit(app.exec())
```

(Language must be applied **before** `MainWindow()` is constructed, so every `tr()` call made during `__init__` already resolves through the installed translator — no retranslation needed for the very first paint.)

- [ ] **Step 7: Wire `MainWindow`: store `self.menus`, add the (currently empty) `retranslate_ui()`, subscribe to the signal**

In `main_window/main_window.py`, add the import:

```python
from main_window.language import language_manager
```

Change `_init_actions_ui`:

```python
    def _init_actions_ui(self):
        self.actions = create_actions(self)
        self.menus = create_menus(self, self.actions)
        create_toolbars(self, self.actions)

        # Registers every action on the window so ApplicationShortcut
        # shortcuts work even outside menus (required on Windows)
        for action in self.actions.values():
            self.addAction(action)

        # explicit initial state
        self.actions["mode_select"].setChecked(True)

        language_manager.language_changed.connect(self.retranslate_ui)
```

Add the method (empty for now; Tasks 4-6 fill it in):

```python
    def retranslate_ui(self) -> None:
        """Re-applies tr() text to every persistent widget after a language
        change. Transient dialogs need no hook here -- they're rebuilt from
        scratch on every open and pick up the active language automatically."""
        pass
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_language_actions.py tests/test_main_window_retranslate_wiring.py -v`
Expected: PASS (4 tests)

- [ ] **Step 9: Run the full existing test suite to check for regressions**

Run: `pytest tests/ -v`
Expected: PASS (no test currently asserts on `create_menus`'s return value or `MainWindow.menus`, so nothing else should be affected)

- [ ] **Step 10: Commit**

```bash
git add app.py main_window/main_window.py main_window/ui/menus.py main_window/actions/__init__.py main_window/actions/language_actions.py tests/test_language_actions.py tests/test_main_window_retranslate_wiring.py
git commit -m "feat: wire LanguageManager into app startup and add Language menu"
```

---

## Task 4: Migrate `main_window/actions/*.py` to `tr()` and implement stateful retranslation

**Files:**
- Modify: `main_window/actions/file_actions.py`
- Modify: `main_window/actions/view_actions.py`
- Modify: `main_window/actions/edit_actions.py`
- Modify: `main_window/actions/mode_actions.py`
- Modify: `main_window/actions/help_actions.py`
- Modify: `main_window/actions/simulation_actions.py`
- Modify: `main_window/actions/generator_actions.py`
- Modify: `main_window/actions/__init__.py`
- Modify: `main_window/main_window.py`
- Test: `tests/test_actions_text_is_english.py`

**Interfaces:**
- Produces: `retranslate_actions(actions: dict, main_window) -> None` exported from `main_window/actions/__init__.py`, called from `MainWindow.retranslate_ui()`.

Every `QAction("<literal>", main_window)` becomes `QAction(main_window.tr("<literal>"), main_window)`, using the English text below (Portuguese source strings translated; already-English ones left as-is so `tr()` has something well-formed to extract). Table of changes:

| File | Old (as in source today) | New `tr()` source (English) |
|---|---|---|
| `file_actions.py` | `"New"`, `"Open"`, `"Save"`, `"Save As"`, `"Exit"` | unchanged text, now `tr()`-wrapped |
| `view_actions.py` | `"Zoom In"`, `"Zoom Out"`, `"Fit to Contents"`, `"Light Theme"`, `"Font Size..."` | unchanged text, now `tr()`-wrapped |
| `edit_actions.py` | `"Delete"`, `"Copy"`, `"Paste"`, `"Add"`, `"Undo"`, `"Redo"`, `"Rotate 90°"` + tooltip `"Rotate selected component 90° clockwise (R)"` | unchanged text, now `tr()`-wrapped |
| `edit_actions.py` (inline `_do_paste`) | `"Simulação em execução"` / `"Pare a simulação para editar o diagrama."` | `"Simulation running"` / `"Stop the simulation to edit the diagram."` |
| `mode_actions.py` | `"Select"`, `"Connect"`, `"Simulate"` | unchanged text, now `tr()`-wrapped |
| `help_actions.py` | `"About"` | unchanged text, now `tr()`-wrapped |
| `simulation_actions.py` | `"Run"`, `"Step Back"`, `"Step Forward"`, `"dt: 0.100s"`, `"1x"` | `"Run"`, `"Step Back"`, `"Step Forward"` `tr()`-wrapped; `"dt: 0.100s"` / `"1x"` are initial display-only values, replaced by `retranslate_actions`'s stateful formatting at every language switch (see below), so they stay as plain (untranslated, numeric) literals here |
| `generator_actions.py` | `"Novo a partir de Sequência..."` | `"New from Sequence..."` |

- [ ] **Step 1: Write the failing test**

```python
# tests/test_actions_text_is_english.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from unittest.mock import Mock
from main_window.actions import create_actions, retranslate_actions


def _build_actions():
    fake_main_window = Mock()
    fake_main_window.tr = lambda s: s  # identity translation, no .qm installed
    return create_actions(fake_main_window), fake_main_window


def test_action_texts_are_english_source_strings():
    actions, _ = _build_actions()

    assert actions["new"].text() == "New"
    assert actions["open"].text() == "Open"
    assert actions["save"].text() == "Save"
    assert actions["save_as"].text() == "Save As"
    assert actions["exit"].text() == "Exit"
    assert actions["zoom_in"].text() == "Zoom In"
    assert actions["zoom_out"].text() == "Zoom Out"
    assert actions["zoom_fit"].text() == "Fit to Contents"
    assert actions["toggle_theme"].text() == "Light Theme"
    assert actions["font_size"].text() == "Font Size..."
    assert actions["delete"].text() == "Delete"
    assert actions["copy"].text() == "Copy"
    assert actions["paste"].text() == "Paste"
    assert actions["open_palette"].text() == "Add"
    assert actions["undo"].text() == "Undo"
    assert actions["redo"].text() == "Redo"
    assert actions["rotate"].text() == "Rotate 90°"
    assert actions["mode_select"].text() == "Select"
    assert actions["mode_connect"].text() == "Connect"
    assert actions["mode_simulate"].text() == "Simulate"
    assert actions["about"].text() == "About"
    assert actions["run"].text() == "Run"
    assert actions["step_back"].text() == "Step Back"
    assert actions["step_forward"].text() == "Step Forward"
    assert actions["new_from_sequence"].text() == "New from Sequence..."


def test_retranslate_actions_reapplies_static_text():
    actions, fake_main_window = _build_actions()
    actions["new"].setText("stale")

    retranslate_actions(actions, fake_main_window)

    assert actions["new"].text() == "New"


def test_retranslate_actions_reformats_dt_from_current_simulation_state():
    actions, fake_main_window = _build_actions()
    fake_main_window.simulation = Mock(dt=0.25)

    retranslate_actions(actions, fake_main_window)

    assert actions["dt"].text() == "dt: 0.250s"


def test_retranslate_actions_reapplies_toggle_theme_text_from_current_state():
    actions, fake_main_window = _build_actions()
    fake_main_window.use_light_theme = True

    retranslate_actions(actions, fake_main_window)

    assert actions["toggle_theme"].text() == "Dark Theme"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_actions_text_is_english.py -v`
Expected: FAIL — several assertions fail (e.g. `actions["new_from_sequence"].text() == "New from Sequence..."` fails, current text is `"Novo a partir de Sequência..."`), and `ImportError: cannot import name 'retranslate_actions'`

- [ ] **Step 3: Migrate each action factory to `tr()`**

`main_window/actions/file_actions.py`:
```python
"""File actions: new, open, save and save as."""

from PyQt6.QtGui import QAction

def create_file_actions(main_window):
    actions = {}

    actions["new"] = QAction(main_window.tr("New"), main_window)
    actions["new"].setShortcut("Ctrl+N")
    actions["new"].triggered.connect(main_window.new_scene)

    actions["open"] = QAction(main_window.tr("Open"), main_window)
    actions["open"].setShortcut("Ctrl+O")
    actions["open"].triggered.connect(main_window.open_scene)

    actions["save"] = QAction(main_window.tr("Save"), main_window)
    actions["save"].setShortcut("Ctrl+S")
    actions["save"].triggered.connect(main_window.save_scene)

    actions["save_as"] = QAction(main_window.tr("Save As"), main_window)
    actions["save_as"].setShortcut("F12")
    actions["save_as"].triggered.connect(main_window.save_scene_as)

    actions["exit"] = QAction(main_window.tr("Exit"), main_window)
    actions["exit"].setShortcut("Ctrl+Q")
    actions["exit"].triggered.connect(main_window.close)

    return actions
```

`main_window/actions/view_actions.py`:
```python
"""View actions: zoom in/out and fit to screen."""

from PyQt6.QtGui import QAction

def create_view_actions(main_window):

    actions = {}

    actions["zoom_in"] = QAction(main_window.tr("Zoom In"))
    actions["zoom_in"].setShortcut("Ctrl++")
    actions["zoom_in"].triggered.connect(main_window.zoom_in)

    actions["zoom_out"] = QAction(main_window.tr("Zoom Out"))
    actions["zoom_out"].setShortcut("Ctrl+-")
    actions["zoom_out"].triggered.connect(main_window.zoom_out)

    actions["zoom_fit"] = QAction(main_window.tr("Fit to Contents"))
    actions["zoom_fit"].setShortcut("Ctrl+0")
    actions["zoom_fit"].triggered.connect(main_window.zoom_to_contents)


    actions["toggle_theme"] = QAction(main_window.tr("Light Theme"))
    actions["toggle_theme"].setCheckable(True)
    actions["toggle_theme"].triggered.connect(main_window.set_light_theme)

    actions["font_size"] = QAction(main_window.tr("Font Size..."))
    actions["font_size"].triggered.connect(main_window.on_change_font_size)

    return actions
```

`main_window/actions/edit_actions.py` (full file, note the tooltip and the `_do_paste` message box):
```python
"""Edit actions: delete, copy, paste, undo, redo, and rotate."""

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtCore import Qt

def create_edit_actions(main_window):
    actions = {}

    actions["delete"] = QAction(main_window.tr("Delete"), main_window)
    actions["delete"].setShortcut(QKeySequence.StandardKey.Delete)
    actions["delete"].setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    actions["delete"].triggered.connect(
        main_window.delete_selected_items
    )

    actions["copy"] = QAction(main_window.tr("Copy"), main_window)
    actions["copy"].setShortcut(QKeySequence.StandardKey.Copy)  # Ctrl+C
    actions["copy"].setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    actions["copy"].triggered.connect(
        lambda: main_window.clipboard_manager.copy(main_window.scene)
    )

    actions["paste"] = QAction(main_window.tr("Paste"), main_window)
    actions["paste"].setShortcut(QKeySequence.StandardKey.Paste)  # Ctrl+V
    actions["paste"].setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)

    def _do_paste():
        from PyQt6.QtWidgets import QMessageBox
        from editor.mode import EditorMode
        if main_window.state.mode == EditorMode.SIMULATE:
            QMessageBox.information(
                main_window,
                main_window.tr("Simulation running"),
                main_window.tr("Stop the simulation to edit the diagram."),
            )
            return
        main_window.clipboard_manager.paste(main_window.scene, main_window.state)
        main_window.cancel_current_mode()

    actions["paste"].triggered.connect(_do_paste)

    actions["open_palette"] = QAction(main_window.tr("Add"), main_window)
    actions["open_palette"].setCheckable(True)
    actions["open_palette"].toggled.connect(
        main_window.palette_dock.setVisible
    )

    # ── Undo / Redo ──────────────────────────────────────────────────────────
    # Note: Ctrl+Z is used by the simulation (step_back) when SIMULATE mode
    # is active. These actions are enabled only outside simulation;
    # the toggle logic is handled in MainWindow.update_simulation_actions().

    actions["undo"] = QAction(main_window.tr("Undo"), main_window)
    actions["undo"].setShortcut(QKeySequence.StandardKey.Undo)  # Ctrl+Z
    actions["undo"].setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    actions["undo"].triggered.connect(
        lambda: main_window.state.undo_stack.undo()
    )

    actions["redo"] = QAction(main_window.tr("Redo"), main_window)
    actions["redo"].setShortcut(QKeySequence.StandardKey.Redo)  # Ctrl+Shift+Z
    actions["redo"].setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    actions["redo"].triggered.connect(
        lambda: main_window.state.undo_stack.redo()
    )

    # ── Rotate ───────────────────────────────────────────────────────────────
    actions["rotate"] = QAction(main_window.tr("Rotate 90°"), main_window)
    actions["rotate"].setShortcut(QKeySequence("R"))
    actions["rotate"].setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    actions["rotate"].setToolTip(
        main_window.tr("Rotate selected component 90° clockwise (R)")
    )

    def _do_rotate():
        from editor.mode import EditorMode
        from graphics.items.base.nodes.node_item import NodeItem

        if main_window.state.mode == EditorMode.SIMULATE:
            return

        scene = main_window.scene
        selected_nodes = [
            item for item in scene.selectedItems()
            if isinstance(item, NodeItem)
        ]
        if not selected_nodes:
            return

        undo_stack = main_window.state.undo_stack
        before = undo_stack.snapshot(scene)

        for node in selected_nodes:
            node.rotate(90)

        undo_stack.push_snapshot(
            scene, main_window.state, before, main_window.tr("Rotate component")
        )

    actions["rotate"].triggered.connect(_do_rotate)

    return actions
```

`main_window/actions/mode_actions.py`:
```python
"""Editor mode actions with an exclusive QActionGroup."""

from PyQt6.QtGui import QAction, QActionGroup
from editor.mode import EditorMode

def create_mode_actions(main_window):
    actions = {}

    group = QActionGroup(main_window)
    group.setExclusive(True)
    main_window.mode_group = group

    actions["mode_select"] = QAction(main_window.tr("Select"), main_window)
    actions["mode_select"].setCheckable(True)
    actions["mode_select"].setData(EditorMode.SELECT)
    actions["mode_select"].toggled.connect(lambda checked: checked and main_window.set_mode(EditorMode.SELECT))
    group.addAction(actions["mode_select"])

    actions["mode_connect"] = QAction(main_window.tr("Connect"), main_window)
    actions["mode_connect"].setCheckable(True)
    actions["mode_connect"].setData(EditorMode.CONNECT)
    actions["mode_connect"].toggled.connect(lambda checked: checked and main_window.set_mode(EditorMode.CONNECT))
    group.addAction(actions["mode_connect"])

    actions["mode_simulate"] = QAction(main_window.tr("Simulate"), main_window)
    actions["mode_simulate"].setCheckable(True)
    actions["mode_simulate"].setData(EditorMode.SIMULATE)
    actions["mode_simulate"].setShortcut("Ctrl+G")
    actions["mode_simulate"].toggled.connect(lambda checked: checked and main_window.set_mode(EditorMode.SIMULATE if checked else EditorMode.SELECT))
    group.addAction(actions["mode_simulate"])

    return actions
```

`main_window/actions/help_actions.py`:
```python
"""Help actions: about and documentation."""

from PyQt6.QtGui import QAction

def create_help_actions(main_window):

    actions = {}

    actions["about"] = QAction(main_window.tr("About"), main_window)
    actions["about"].triggered.connect(main_window.show_about)

    return actions
```

`main_window/actions/simulation_actions.py` (note: `"dt"` / `"speed"` keep a plain initial literal — `retranslate_actions` owns their live formatting):
```python
"""Simulation actions: play, pause, step forward/back and speed control."""

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QLabel, QWidget, QHBoxLayout

SPEED_STEPS = [1, 2, 4, 8]

def create_simulation_actions(main_window):
    actions = {}

    actions["run"] = QAction(main_window.tr("Run"), main_window)
    actions["run"].setShortcut("Space")
    actions["run"].setEnabled(False)
    actions["run"].triggered.connect(main_window.toggle_play)

    actions["step_back"] = QAction(main_window.tr("Step Back"), main_window)
    # Ctrl+Z is reserved for Undo -- step_back uses Ctrl+Left in the simulation
    actions["step_back"].setShortcut("Ctrl+Left")
    actions["step_back"].setEnabled(False)
    actions["step_back"].triggered.connect(main_window.on_step_back)

    actions["step_forward"] = QAction(main_window.tr("Step Forward"), main_window)
    actions["step_forward"].setShortcut("Ctrl+Right")
    actions["step_forward"].setEnabled(False)
    actions["step_forward"].triggered.connect(main_window.on_step_forward)

    actions["dt"] = QAction("dt: 0.100s", main_window)
    actions["dt"].triggered.connect(main_window.on_dt_clicked)

    actions["speed"] = QAction("1x", main_window)
    actions["speed"].triggered.connect(main_window.on_cycle_speed)

    return actions
```

`main_window/actions/generator_actions.py`:
```python
"""Action that opens the automatic circuit generation dialog."""

from PyQt6.QtGui import QAction
from main_window.ui.circuit_generator_dialog import CircuitGeneratorDialog
from circuit_generator.circuit_generator import generate_and_load
from editor.mode import EditorMode


def create_generator_actions(main_window) -> dict:
    actions = {}

    act = QAction(main_window.tr("New from Sequence..."), main_window)
    act.setShortcut("Ctrl+G")
    act.triggered.connect(lambda: _open_dialog(main_window))
    actions["new_from_sequence"] = act

    return actions


def _open_dialog(main_window):
    dialog = CircuitGeneratorDialog(main_window)
    if dialog.exec():
        generate_and_load(
            dialog.sequence,
            dialog.method,
            dialog.sub_type,
            main_window.scene,
            main_window.state,
        )
        main_window.set_mode(EditorMode.SELECT)
        main_window.zoom_to_contents()
```

- [ ] **Step 4: Add `retranslate_actions` and export it**

Append to `main_window/actions/__init__.py`:

```python
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
```

Note the inverted logic vs. the current codebase: today `toggle_theme`'s label shows the theme you'd *switch to* ("Light Theme" while dark is active). Preserved exactly here — `use_light_theme=False` (dark active) → shows `"Light Theme"`.

- [ ] **Step 5: Call it from `MainWindow.retranslate_ui`**

Edit `main_window/main_window.py`:

```python
    def retranslate_ui(self) -> None:
        """Re-applies tr() text to every persistent widget after a language
        change. Transient dialogs need no hook here -- they're rebuilt from
        scratch on every open and pick up the active language automatically."""
        from main_window.actions import retranslate_actions
        retranslate_actions(self.actions, self)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_actions_text_is_english.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Run the full test suite and fix any regressions**

Run: `pytest tests/ -v`
Expected: `tests/test_view_actions_font_size.py::test_font_size_action_exists_and_triggers_handler` still passes (asserts `actions["font_size"].text() == "Font Size..."`, unchanged text — `tr()` with no translator installed returns the source text as-is). No other test currently asserts on these action texts.

- [ ] **Step 8: Commit**

```bash
git add main_window/actions/ main_window/main_window.py tests/test_actions_text_is_english.py
git commit -m "feat: migrate action labels to tr(), add stateful retranslation"
```

---

## Task 5: Migrate `menus.py`, `toolbars.py`, and `main_window.py`'s own strings; finish `retranslate_ui`

**Files:**
- Modify: `main_window/ui/menus.py`
- Modify: `main_window/ui/toolbars.py`
- Modify: `main_window/main_window.py`
- Test: `tests/test_menus_and_window_title.py`

**Interfaces:**
- Consumes: `main_window.menus` dict (Task 3), `retranslate_actions` (Task 4)
- Produces: `create_toolbars(main_window, actions) -> QToolBar` (changed — was returning `None`implicitly), stored as `main_window.toolbar`; `MainWindow.retranslate_ui()` now also re-applies menu titles, toolbar title, and window title.

Strings changed: window title `"Simulador – Editor Gráfico"` → `"Circuit Editor"` (both occurrences: `__init__` and `new_scene`); About dialog title `"About"` (already English, `tr()`-wrapped) and body `"Simulador – Editor Gráfico\nPneumatic and Hydraulic Systems\n\nBuilt with PyQt6"` → `"Circuit Editor\nPneumatic and Hydraulic Systems\n\nBuilt with PyQt6"`; `QInputDialog.getDouble` labels `"Step size"` / `"dt (s):"` stay (already English, `tr()`-wrapped); menu titles `"File"`, `"Edit"`, `"View"`, `"Help"`; toolbar title `"Tools"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_menus_and_window_title.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from main_window.main_window import MainWindow


def test_menu_titles_are_english():
    window = MainWindow()
    try:
        assert window.menus["file"].title() == "File"
        assert window.menus["edit"].title() == "Edit"
        assert window.menus["view"].title() == "View"
        assert window.menus["help"].title() == "Help"
    finally:
        window.close()


def test_window_title_is_english():
    window = MainWindow()
    try:
        assert window.windowTitle() == "Circuit Editor"
    finally:
        window.close()


def test_toolbar_title_is_english():
    window = MainWindow()
    try:
        assert window.toolbar.windowTitle() == "Tools"
    finally:
        window.close()


def test_retranslate_ui_reapplies_menu_and_window_titles():
    window = MainWindow()
    try:
        window.menus["file"].setTitle("stale")
        window.setWindowTitle("stale")
        window.toolbar.setWindowTitle("stale")

        window.retranslate_ui()

        assert window.menus["file"].title() == "File"
        assert window.windowTitle() == "Circuit Editor"
        assert window.toolbar.windowTitle() == "Tools"
    finally:
        window.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_menus_and_window_title.py -v`
Expected: FAIL — `window.menus["file"].title() == "File"` fails (still literal, but this specific assertion actually already passes since menus.py's `addMenu("File")` sets an untranslated but already-English literal; the real failures are `test_window_title_is_english` — actual is `"Simulador – Editor Gráfico"` — and `AttributeError: 'MainWindow' object has no attribute 'toolbar'`)

- [ ] **Step 3: Wrap menu titles in `tr()`**

Edit `main_window/ui/menus.py` — replace the four literal `addMenu` calls:

```python
    file_menu = menubar.addMenu(main_window.tr("File"))
    ...
    edit_menu = menubar.addMenu(main_window.tr("Edit"))
    ...
    view_menu = menubar.addMenu(main_window.tr("View"))
    ...
    help_menu = menubar.addMenu(main_window.tr("Help"))
```

(leave everything else in the file as Task 3 left it)

- [ ] **Step 4: Wrap the toolbar title and return the toolbar**

Edit `main_window/ui/toolbars.py`:

```python
"""Builds the main window toolbars from the created actions."""

from PyQt6.QtWidgets import QToolBar

def create_toolbars(main_window, actions):
    toolbar = QToolBar(main_window.tr("Tools"), main_window)
    toolbar.setMovable(False)

    toolbar.addAction(actions["open_palette"])
    toolbar.addAction(actions["delete"])
    toolbar.addAction(actions["mode_select"])
    toolbar.addAction(actions["mode_connect"])

    toolbar.addSeparator()

    toolbar.addAction(actions["zoom_in"])
    toolbar.addAction(actions["zoom_out"])
    toolbar.addAction(actions["zoom_fit"])

    toolbar.addSeparator()

    toolbar.addAction(actions["mode_simulate"])
    toolbar.addAction(actions["run"])
    toolbar.addAction(actions["step_back"])
    toolbar.addAction(actions["step_forward"])

    toolbar.addSeparator()
    toolbar.addAction(actions["speed"])
    toolbar.addAction(actions["dt"])

    main_window.addToolBar(toolbar)

    return toolbar
```

- [ ] **Step 5: Update `main_window.py`: store `self.toolbar`, wrap remaining literals, finish `retranslate_ui`**

```python
    def _init_actions_ui(self):
        self.actions = create_actions(self)
        self.menus = create_menus(self, self.actions)
        self.toolbar = create_toolbars(self, self.actions)

        for action in self.actions.values():
            self.addAction(action)

        self.actions["mode_select"].setChecked(True)

        language_manager.language_changed.connect(self.retranslate_ui)
```

Replace both window-title literals:

```python
        self.setWindowTitle(self.tr("Circuit Editor"))   # __init__, was "Simulador – Editor Gráfico"
```
```python
        self.setWindowTitle(self.tr("Circuit Editor"))   # new_scene, was "Simulador – Editor Gráfico"
```

Replace the About dialog:

```python
    def show_about(self):
        QMessageBox.about(
            self,
            self.tr("About"),
            self.tr(
                "Circuit Editor\n"
                "Pneumatic and Hydraulic Systems\n\n"
                "Built with PyQt6"
            )
        )
```

Replace the `QInputDialog.getDouble` call:

```python
    def on_dt_clicked(self):
        from PyQt6.QtWidgets import QInputDialog
        value, ok = QInputDialog.getDouble(
            self, self.tr("Step size"), self.tr("dt (s):"),
            self.simulation.dt,  # reads from the session
            0.001, 1.0, 3
        )
        if ok:
            self.simulation.set_dt(value)
            self.actions["dt"].setText(self.tr("dt: {0:.3f}s").format(value))
```

Replace the undo-snapshot label in `add_node_at` (was `"Adicionar nó"`):

```python
        self.state.undo_stack.push_snapshot(self.scene, self.state, before, self.tr("Add node"))
```

Fill in `retranslate_ui`:

```python
    def retranslate_ui(self) -> None:
        """Re-applies tr() text to every persistent widget after a language
        change. Transient dialogs need no hook here -- they're rebuilt from
        scratch on every open and pick up the active language automatically."""
        from main_window.actions import retranslate_actions
        retranslate_actions(self.actions, self)

        self.menus["file"].setTitle(self.tr("File"))
        self.menus["edit"].setTitle(self.tr("Edit"))
        self.menus["view"].setTitle(self.tr("View"))
        self.menus["help"].setTitle(self.tr("Help"))
        self.menus["language"].setTitle(self.tr("Language"))

        self.toolbar.setWindowTitle(self.tr("Tools"))

        self.setWindowTitle(self.tr("Circuit Editor"))
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_menus_and_window_title.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS. (No existing test asserts on the old `"Simulador – Editor Gráfico"` window title or `"Adicionar nó"` undo label.)

- [ ] **Step 8: Commit**

```bash
git add main_window/ui/menus.py main_window/ui/toolbars.py main_window/main_window.py tests/test_menus_and_window_title.py
git commit -m "feat: migrate menu/toolbar/window-title strings, finish MainWindow retranslate_ui"
```

---

## Task 6: Migrate the node palette (dock, sections, tier labels) with correct domain-key handling

**Files:**
- Modify: `main_window/ui/docks/node_palette_dock.py`
- Modify: `main_window/ui/palette/node_palette.py`
- Modify: `main_window/ui/palette/palette_section.py`
- Modify: `main_window/ui/palette/node_palette_item.py`
- Modify: `main_window/main_window.py`
- Test: `tests/test_palette_retranslate.py`

**Interfaces:**
- Produces: `NodePalette.add_section(self, key: str, title: str | None = None)` (signature change — `title` now optional and separate from the internal dict key, so translating the *displayed* title never breaks the untranslated *lookup* key used by `node_registry.py`'s `section_key = domain.capitalize()`), `PaletteSection.retranslate_ui(self, title: str) -> None`, `NodePalette.retranslate_ui(self) -> None`, `create_node_palette(main_window) -> tuple[NodePalette, QDockWidget]` (unchanged signature, dock title now translated + retranslatable). `MainWindow.retranslate_ui()` gains a call into `self.node_palette.retranslate_ui()` and `self.palette_dock.setWindowTitle(...)`.

This is the one subtle piece in the whole migration: `NodePalette.sections` is keyed by the **canonical domain name** (`"Pneumatic"`, `"Electric"`, `"Hydraulic"` — always English, matching `domain.capitalize()` in `node_registry.py`). If the displayed section title were translated *in place* of that key, `node_registry.py`'s `if section_key not in palette.sections: continue` would silently stop finding the section once Portuguese was active, and no nodes would ever get registered into it. So the key and the displayed title must be kept as two separate values from here on.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_palette_retranslate.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from main_window.ui.palette.node_palette import NodePalette


def test_add_section_keeps_canonical_key_separate_from_translated_title():
    palette = NodePalette()
    palette.add_section("Pneumatic", "Pneumático")

    assert "Pneumatic" in palette.sections          # lookup key unchanged
    assert palette.sections["Pneumatic"].header.text() == "▾ Pneumático"  # displayed title translated


def test_add_section_defaults_title_to_key_when_not_given():
    palette = NodePalette()
    palette.add_section("Electric")

    assert palette.sections["Electric"].header.text() == "▾ Electric"


def test_retranslate_updates_section_titles_and_tier_tooltips():
    palette = NodePalette()
    palette.add_section("Hydraulic", "Hydraulic")

    palette.retranslate_ui({"Hydraulic": "Hidráulico"})

    assert palette.sections["Hydraulic"].header.text() == "▾ Hidráulico"
    assert palette.tier_buttons["small"].toolTip() == "Small"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_palette_retranslate.py -v`
Expected: FAIL — `TypeError: add_section() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: Update `palette_section.py`: `tr()`-wrap, separate `retranslate_ui`, extract the shared header-formatting helper**

```python
"""Palette grouping section (e.g. "Pneumatic", "Electric")."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout
from PyQt6.QtCore import Qt

from main_window.ui.palette.node_palette_item import NodePaletteItem


class PaletteSection(QWidget):
    def __init__(self, title: str, num_columns=2, parent=None):
        super().__init__(parent)

        self.title = title
        self.num_columns = num_columns
        self._collapsed = False
        self._items: list[NodePaletteItem] = []

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(20)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Clickable header
        self.header = QLabel()
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setStyleSheet("font-weight: bold;")
        self.header.mousePressEvent = self.toggle
        self._refresh_header_text()

        self.main_layout.addWidget(self.header)

        # Grid container
        self.content = QWidget()
        self.grid_layout = QGridLayout(self.content)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.main_layout.addWidget(self.content)

    def _refresh_header_text(self):
        arrow = "▸" if self._collapsed else "▾"
        self.header.setText(f"{arrow} {self.title}")

    def toggle(self, event=None):
        self._collapsed = not self._collapsed
        self.content.setVisible(not self._collapsed)
        self._refresh_header_text()

    def retranslate_ui(self, title: str):
        """Updates the displayed title (called after a language change;
        title is already translated by the caller)."""
        self.title = title
        self._refresh_header_text()

    def add_node(self, name: str, icon_path: str, callback):
        item = NodePaletteItem(name, icon_path)
        self._items.append(item)
        self._place_item(item, len(self._items) - 1)

        item.mouseReleaseEvent = lambda e: callback()
        return item

    def _place_item(self, item: NodePaletteItem, index: int):
        row = index // self.num_columns
        col = index % self.num_columns
        self.grid_layout.addWidget(item, row, col)

    def set_num_columns(self, cols: int):
        if cols == self.num_columns or cols < 1:
            return
        self.num_columns = cols

        while self.grid_layout.count():
            self.grid_layout.takeAt(0)

        for index, item in enumerate(self._items):
            self._place_item(item, index)

    def apply_item_size(self, pixmap_wh: tuple[int, int], item_width: int, font_delta: int):
        for item in self._items:
            item.apply_size(pixmap_wh, item_width, font_delta)

    def set_light_theme(self, is_light: bool):
        for item in self._items:
            item.set_light_theme(is_light)
```

- [ ] **Step 4: Update `node_palette.py`: split key/title in `add_section`, `tr()`-wrap tier labels, add `retranslate_ui`**

```python
    TIER_LABELS = {"small": "S", "medium": "M", "large": "L"}
```

(was `{"small": "P", "medium": "M", "large": "G"}` — the Portuguese initials for Pequeno/Médio/Grande; English initials for Small/Medium/Large. `TIER_TOOLTIPS` moves from a plain dict to `tr()` calls made at use-time, since a module-level dict is evaluated once at import and would freeze whichever language was active then.)

Replace the `TIER_LABELS`/`TIER_TOOLTIPS` class attributes and the loop that builds tier buttons:

```python
class NodePalette(QWidget):
    SIZE_TIERS = {
        "small":  {"pixmap": (60, 40),  "item_width": 100, "font_delta": 0},
        "medium": {"pixmap": (84, 56),  "item_width": 130, "font_delta": 1},
        "large":  {"pixmap": (112, 76), "item_width": 160, "font_delta": 2},
    }
    TIER_LABELS = {"small": "S", "medium": "M", "large": "L"}

    def _tier_tooltip(self, tier: str) -> str:
        return {
            "small": self.tr("Small"),
            "medium": self.tr("Medium"),
            "large": self.tr("Large"),
        }[tier]
```

```python
        for tier in ("small", "medium", "large"):
            btn = QPushButton(self.TIER_LABELS[tier])
            btn.setObjectName("sizeTierButton")
            btn.setCheckable(True)
            btn.setToolTip(self._tier_tooltip(tier))
            btn.clicked.connect(lambda checked, t=tier: self.set_size_tier(t))
            self._tier_group.addButton(btn)
            self.tier_buttons[tier] = btn
            tier_row.addWidget(btn)
```

Replace the "Nodes" title:

```python
        title = QLabel(self.tr("Nodes"))
```

Replace `add_section` and add `retranslate_ui`:

```python
    def add_section(self, key: str, title: str | None = None):
        if key in self.sections:
            return self.sections[key]

        section = PaletteSection(title or key, num_columns=1)
        section.set_light_theme(self.use_light_theme)
        self.sections[key] = section
        self.container_layout.addWidget(section)
        return section

    def retranslate_ui(self, section_titles: dict[str, str]):
        """section_titles maps each canonical section key ("Pneumatic",
        "Electric", "Hydraulic") to its already-translated display title."""
        for key, title in section_titles.items():
            if key in self.sections:
                self.sections[key].retranslate_ui(title)

        for tier, btn in self.tier_buttons.items():
            btn.setToolTip(self._tier_tooltip(tier))
```

- [ ] **Step 5: Wrap the palette item's own text and dock title**

`node_palette_item.py`'s `text_label = QLabel(name)` receives a component display name from `node_registry.py` (out of scope per Task 12) — no change needed here; it already just displays whatever string it's given.

Edit `main_window/ui/docks/node_palette_dock.py`:

```python
"""Creates the floating QDockWidget that holds the node palette."""

from editor.mode import EditorMode
from PyQt6.QtWidgets import QDockWidget
from PyQt6.QtCore import Qt
from main_window.ui.palette.node_palette import NodePalette
from main_window.ui.registry.node_registry import register_nodes
from main_window import settings


def create_node_palette(main_window):
    palette = NodePalette()
    palette.set_size_tier(settings.get_palette_tier(), persist=False)

    palette.add_section("Pneumatic", main_window.tr("Pneumatic"))
    palette.add_section("Electric", main_window.tr("Electric"))
    palette.add_section("Hydraulic", main_window.tr("Hydraulic"))

    dock = QDockWidget(main_window.tr("Nodes"), main_window)
    dock.setMinimumWidth(180)
    dock.setMaximumWidth(700)
    dock.setWidget(palette)
    dock.setAllowedAreas(
        Qt.DockWidgetArea.LeftDockWidgetArea |
        Qt.DockWidgetArea.RightDockWidgetArea
    )

    main_window.addDockWidget(
        Qt.DockWidgetArea.LeftDockWidgetArea,
        dock
    )

    dock.hide()

    register_nodes(palette, lambda node_desc: main_window.set_mode(EditorMode.ADD, node_desc=node_desc))
    palette.set_size_tier(palette.current_tier, persist=False)

    if hasattr(main_window, "state"):
        main_window.state.theme_changed.connect(palette.set_light_theme)

    return palette, dock
```

- [ ] **Step 6: Wire it into `MainWindow.retranslate_ui`**

```python
    def retranslate_ui(self) -> None:
        """Re-applies tr() text to every persistent widget after a language
        change. Transient dialogs need no hook here -- they're rebuilt from
        scratch on every open and pick up the active language automatically."""
        from main_window.actions import retranslate_actions
        retranslate_actions(self.actions, self)

        self.menus["file"].setTitle(self.tr("File"))
        self.menus["edit"].setTitle(self.tr("Edit"))
        self.menus["view"].setTitle(self.tr("View"))
        self.menus["help"].setTitle(self.tr("Help"))
        self.menus["language"].setTitle(self.tr("Language"))

        self.toolbar.setWindowTitle(self.tr("Tools"))

        self.setWindowTitle(self.tr("Circuit Editor"))

        self.palette_dock.setWindowTitle(self.tr("Nodes"))
        self.node_palette.retranslate_ui({
            "Pneumatic": self.tr("Pneumatic"),
            "Electric": self.tr("Electric"),
            "Hydraulic": self.tr("Hydraulic"),
        })
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_palette_retranslate.py -v`
Expected: PASS (3 tests)

- [ ] **Step 8: Run the full test suite and fix any regressions**

Run: `pytest tests/ -v`
Expected: check specifically for tests referencing `TIER_LABELS` values `"P"`/`"M"`/`"G"` or calling `add_section` with the old single-argument signature; update any found to the new `"S"/"M"/"L"` labels or two-argument call. (None were found in the grep sweep in Task planning, but re-verify — palette tier buttons and `add_section` are simple enough that a codebase-wide `grep -rn "add_section\|TIER_LABELS" tests/` before this step is the authoritative check.)

- [ ] **Step 9: Commit**

```bash
git add main_window/ui/docks/node_palette_dock.py main_window/ui/palette/ main_window/main_window.py tests/test_palette_retranslate.py
git commit -m "feat: migrate node palette strings, keep domain keys stable across languages"
```

---

## Task 7: Migrate `persistence/file_session.py` and `main_window/report_resolution.py`

**Files:**
- Modify: `persistence/file_session.py`
- Modify: `main_window/report_resolution.py`
- Test: `tests/test_file_session_messages.py`
- Test: `tests/test_report_resolution_messages.py`

**Interfaces:**
- No signature changes. Both files hold plain classes/functions (not `QObject` subclasses), so they use `QCoreApplication.translate("Context", "...")` instead of `self.tr(...)`. Both are transient (dialogs/messages built fresh on every call) — no retranslate hook needed, per the spec's persistent/transient split.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_file_session_messages.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from unittest.mock import Mock, patch
from persistence.file_session import SceneFileSession


def test_open_shows_english_error_title_on_failure():
    parent = Mock()
    session = SceneFileSession(scene=Mock(), parent_window=parent, editor_state=Mock())

    with patch("persistence.file_session.QFileDialog.getOpenFileName", return_value=("bad.json", "")):
        with patch("persistence.serializer.load_from_file", side_effect=ValueError("boom")):
            with patch("persistence.file_session.QMessageBox.critical") as mock_critical:
                session.open()

    assert mock_critical.call_args.args[1] == "Error opening file"


def test_window_title_uses_english_prefix_after_save():
    parent = Mock()
    session = SceneFileSession(scene=Mock(), parent_window=parent, editor_state=Mock())

    with patch("persistence.serializer.save_to_file"):
        session._save_to_path("some/path/circuit.json")

    parent.setWindowTitle.assert_called_once_with("Circuit Editor – circuit.json")
```

```python
# tests/test_report_resolution_messages.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from unittest.mock import Mock, patch
from PyQt6.QtWidgets import QMessageBox
from main_window.report_resolution import resolve_report


def test_asks_english_question_and_discards_on_no():
    with patch("main_window.report_resolution.QMessageBox.question", return_value=QMessageBox.StandardButton.No) as mock_question:
        with patch("main_window.report_resolution.shutil.rmtree") as mock_rmtree:
            resolve_report(parent=None, report_dir="/tmp/report", circuit_name="circuit")

    assert mock_question.call_args.args[1] == "Simulation report"
    mock_rmtree.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_file_session_messages.py tests/test_report_resolution_messages.py -v`
Expected: FAIL — `mock_critical.call_args.args[1] == "Erro ao abrir"` (actual) vs `"Error opening file"` (expected); `mock_question.call_args.args[1] == "Relatório de simulação"` (actual) vs `"Simulation report"` (expected)

- [ ] **Step 3: Migrate `persistence/file_session.py`**

```python
"""Manages the open file session: current path, dialogs and window title."""

from pathlib import Path
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QFileDialog, QMessageBox


class SceneFileSession:
    """Controls the lifecycle of the open scene file.

    Responsibilities:
    - Open a file via dialog and load the scene.
    - Save to the current file or open a "save as" dialog.
    - Update the window title with the file name.

    UI-aware (uses QFileDialog and QMessageBox), but agnostic to the
    persistence format -- delegates reading/writing to the serializer module.

    Args:
        scene: QGraphicsScene managed by the session.
        parent_window: Main window used as parent for the Qt dialogs.
        editor_state: EditorState passed to the deserializer; if None,
            tries to read parent_window.state.
    """

    def __init__(self, scene, parent_window, editor_state=None):
        self.scene = scene
        self.parent = parent_window
        self.editor_state = editor_state or getattr(parent_window, "state", None)
        self.current_file: str | None = None

    # Public API

    def save(self) -> None:
        """Saves to the current file, or opens a dialog if no file is open."""
        if not self.current_file:
            return self.save_as()
        self._save_to_path(self.current_file)

    def save_as(self) -> None:
        """Opens the "save as" dialog and writes the scene to the chosen path."""
        path, _ = QFileDialog.getSaveFileName(
            self.parent,
            QCoreApplication.translate("SceneFileSession", "Save scene"),
            "",
            "Scene Files (*.json)",
        )
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        self._save_to_path(path)

    def open(self) -> None:
        """Opens the file dialog and loads the scene from the chosen JSON."""
        path, _ = QFileDialog.getOpenFileName(
            self.parent,
            QCoreApplication.translate("SceneFileSession", "Open scene"),
            "",
            "Scene Files (*.json)",
        )
        if not path:
            return
        try:
            from persistence.serializer import load_from_file
            load_from_file(self.scene, path, self.editor_state)
            self.current_file = path
            self._update_window_title()
        except Exception as e:
            QMessageBox.critical(
                self.parent,
                QCoreApplication.translate("SceneFileSession", "Error opening file"),
                str(e),
            )

    # Internal methods

    def _save_to_path(self, path: str) -> None:
        """Writes the scene to the given path and updates the window title.

        Args:
            path: Absolute path of the destination file.
        """
        try:
            from persistence.serializer import save_to_file
            save_to_file(self.scene, path)
            self.current_file = path
            self._update_window_title()
        except Exception as e:
            QMessageBox.critical(
                self.parent,
                QCoreApplication.translate("SceneFileSession", "Error saving file"),
                str(e),
            )

    def _update_window_title(self) -> None:
        """Updates the main window title with the current file name."""
        name = Path(self.current_file).name
        self.parent.setWindowTitle(
            QCoreApplication.translate("SceneFileSession", "Circuit Editor – {0}").format(name)
        )
```

- [ ] **Step 4: Migrate `main_window/report_resolution.py`**

```python
"""Resolves the final destination of the simulation report: keep, move or discard."""

import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QFileDialog, QMessageBox


def resolve_report(parent, report_dir: str, circuit_name: str) -> None:
    """Decides the fate of a report already assembled in a temporary directory.

    Asks the user via a popup whether to keep the report. If the answer
    is to keep it, opens a dialog to choose the destination folder and
    moves the files there. In any other case (user declines the popup,
    or cancels the folder dialog), deletes the temporary directory.

    Args:
        parent: Parent widget for the Qt dialogs (can be None in tests).
        report_dir: Temporary directory with the report, charts, and,
            if generated, video.mp4.
        circuit_name: Used to suggest the destination folder name.
    """
    answer = QMessageBox.question(
        parent,
        QCoreApplication.translate("ReportResolution", "Simulation report"),
        QCoreApplication.translate("ReportResolution", "Save this simulation's report?"),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        shutil.rmtree(report_dir, ignore_errors=True)
        return

    dest_parent = QFileDialog.getExistingDirectory(
        parent, QCoreApplication.translate("ReportResolution", "Save report to")
    )
    if not dest_parent:
        shutil.rmtree(report_dir, ignore_errors=True)
        return

    folder_name = f"report_{circuit_name}_{datetime.now():%Y%m%d_%H%M%S}"
    dest = str(Path(dest_parent) / folder_name)
    shutil.move(report_dir, dest)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_file_session_messages.py tests/test_report_resolution_messages.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS. `stop_simulation`'s fallback circuit name in `main_window.py` (`else "circuito"`) also needs updating — check Step 7.

- [ ] **Step 7: Fix the fallback circuit name in `main_window.py`**

`main_window.py`'s `stop_simulation` passes `"circuito"` as the default `circuit_name` when no file is open — English-ize it for consistency with the rest of the report flow:

```python
    def stop_simulation(self):
        result = self.simulation.stop()
        if result is None:
            return
        circuit_name = (
            Path(self.file_session.current_file).stem
            if self.file_session.current_file else self.tr("circuit")
        )
        resolve_report(self, result.report_dir, circuit_name)
```

- [ ] **Step 8: Commit**

```bash
git add persistence/file_session.py main_window/report_resolution.py main_window/main_window.py tests/test_file_session_messages.py tests/test_report_resolution_messages.py
git commit -m "feat: migrate file-session and report-resolution dialog strings"
```

---

## Task 8: Migrate `circuit_generator_dialog.py`, `properties_dialog.py`, `defect_dialog.py`

**Files:**
- Modify: `main_window/ui/circuit_generator_dialog.py`
- Modify: `graphics/utils/properties_dialog.py`
- Modify: `graphics/utils/defect_dialog.py`
- Test: `tests/test_circuit_generator_dialog_text.py`
- Test: `tests/test_properties_dialog_text.py`

**Interfaces:**
- `PropertiesDialog.__init__(self, title: str | None = None, parent=None)` (signature change: default becomes `None`, resolved to `self.tr("Properties")` inside `__init__` — a string literal default is evaluated once at function-definition time, so it can never safely hold a `tr()` call).
- `DefectDialog.__init__(self, title: str | None = None, parent=None)` (same fix; default resolves to `self.tr("Simulate defect")`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_circuit_generator_dialog_text.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from main_window.ui.circuit_generator_dialog import CircuitGeneratorDialog


def test_dialog_labels_are_english():
    dialog = CircuitGeneratorDialog()
    try:
        assert dialog.windowTitle() == "New from Sequence"
        assert dialog._btn_cancel.text() == "Cancel"
        assert dialog._btn_generate.text() == "Generate"
        assert dialog._rb_cascade.text() == "Cascade"
        assert dialog._rb_step.text() == "Step by Step"
        assert dialog._rb_pneumatic.text() == "Pneumatic"
        assert dialog._rb_electric.text() == "Electric"
    finally:
        dialog.close()


def test_empty_sequence_error_is_english():
    dialog = CircuitGeneratorDialog()
    try:
        assert dialog._validate_sequence("") == "Enter a sequence."
    finally:
        dialog.close()
```

```python
# tests/test_properties_dialog_text.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from graphics.utils.properties_dialog import PropertiesDialog
from graphics.utils.defect_dialog import DefectDialog


def test_default_title_is_translated_at_construction_not_at_import():
    dialog = PropertiesDialog()
    try:
        assert dialog.windowTitle() == "Properties"
    finally:
        dialog.close()

    custom = PropertiesDialog(title="Custom Title")
    try:
        assert custom.windowTitle() == "Custom Title"
    finally:
        custom.close()


def test_dialog_buttons_are_english():
    dialog = PropertiesDialog()
    try:
        assert dialog._cancel_btn.text() == "Cancel"
        assert dialog._ok_btn.text() == "OK"
    finally:
        dialog.close()


def test_defect_dialog_default_title_and_buttons_are_english():
    dialog = DefectDialog()
    try:
        assert dialog.windowTitle() == "Simulate defect"
        assert dialog._ok_btn.text() == "Apply"
        assert dialog._restore_btn.text() == "Restore"
    finally:
        dialog.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_circuit_generator_dialog_text.py tests/test_properties_dialog_text.py -v`
Expected: FAIL — all text assertions fail against the current Portuguese/default literals

- [ ] **Step 3: Migrate `main_window/ui/circuit_generator_dialog.py`**

```python
"""Modal dialog for configuring and triggering the automatic circuit generator."""

import re
from circuit_generator.sequence_parser import parse as _parse_sequence, validate_cylinder_states
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QButtonGroup, QGroupBox, QWidget,
)
from PyQt6.QtCore import Qt

_SEQUENCE_RE = re.compile(r'^([A-Z][a-z]*)([+-])([A-Z][a-z]*[+-])*$')


class CircuitGeneratorDialog(QDialog):
    """
    Modal dialog for configuring the circuit generator.

    Public attributes after exec() == QDialog.Accepted:
        sequence : str        e.g. "A+B+A-B-"
        method   : str        "cascade" | "step_by_step"
        sub_type : str | None "pneumatic" | "electric" | None
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("New from Sequence"))
        self.setMinimumWidth(420)

        self.sequence: str = ""
        self.method: str = "cascade"
        self.sub_type: str | None = None

        self._build_ui()
        self._update_state()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(16)

        # -- Sequence --
        seq_box = QGroupBox(self.tr("Sequence"))
        seq_layout = QVBoxLayout(seq_box)

        hint = QLabel(self.tr("E.g.: A+B+A-B-   (uppercase letters followed by + or -)"))
        hint.setStyleSheet("color: gray; font-size: 13px;")
        seq_layout.addWidget(hint)

        self._seq_edit = QLineEdit()
        self._seq_edit.setPlaceholderText("A+B+A-B-")
        self._seq_edit.textChanged.connect(self._on_sequence_changed)
        seq_layout.addWidget(self._seq_edit)

        self._seq_error = QLabel("")
        self._seq_error.setWordWrap(True)
        self._seq_error.setMinimumHeight(32)
        self._seq_error.setStyleSheet("color: red; font-size: 13px;")
        seq_layout.addWidget(self._seq_error)

        root.addWidget(seq_box)

        # -- Method --
        method_box = QGroupBox(self.tr("Method"))
        method_layout = QVBoxLayout(method_box)

        self._rb_cascade   = QRadioButton(self.tr("Cascade"))
        self._rb_step      = QRadioButton(self.tr("Step by Step"))
        self._rb_cascade.setChecked(True)

        self._method_group = QButtonGroup(self)
        self._method_group.addButton(self._rb_cascade)
        self._method_group.addButton(self._rb_step)
        self._method_group.buttonClicked.connect(self._on_method_changed)

        method_layout.addWidget(self._rb_cascade)
        method_layout.addWidget(self._rb_step)

        # Sub-type (visible only for Step by Step)
        self._subtype_widget = QWidget()
        sub_layout = QHBoxLayout(self._subtype_widget)
        sub_layout.setContentsMargins(20, 0, 0, 0)

        sub_label = QLabel(self.tr("Sub-type:"))
        self._rb_pneumatic = QRadioButton(self.tr("Pneumatic"))
        self._rb_electric  = QRadioButton(self.tr("Electric"))
        self._rb_pneumatic.setChecked(True)

        self._subtype_group = QButtonGroup(self)
        self._subtype_group.addButton(self._rb_pneumatic)
        self._subtype_group.addButton(self._rb_electric)

        sub_layout.addWidget(sub_label)
        sub_layout.addWidget(self._rb_pneumatic)
        sub_layout.addWidget(self._rb_electric)
        sub_layout.addStretch()

        method_layout.addWidget(self._subtype_widget)
        root.addWidget(method_box)

        # -- Buttons --
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_cancel = QPushButton(self.tr("Cancel"))
        self._btn_cancel.clicked.connect(self.reject)

        self._btn_generate = QPushButton(self.tr("Generate"))
        self._btn_generate.setDefault(True)
        self._btn_generate.clicked.connect(self._on_generate)

        btn_row.addWidget(self._btn_cancel)
        btn_row.addWidget(self._btn_generate)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # State logic
    # ------------------------------------------------------------------

    def _on_sequence_changed(self, text: str):
        self._update_state()

    def _on_method_changed(self):
        self._update_state()

    def _update_state(self):
        text = self._seq_edit.text().strip()
        is_step = self._rb_step.isChecked()

        # Sub-type visibility
        self._subtype_widget.setVisible(is_step)

        # Sequence validation
        error_msg = self._validate_sequence(text)
        valid = error_msg is None
        self._btn_generate.setEnabled(valid)

        # Red/normal border on the field
        if text and not valid:
            self._seq_edit.setStyleSheet("border: 1px solid red;")
            self._seq_error.setText(error_msg)
        else:
            self._seq_edit.setStyleSheet("")
            self._seq_error.setText("")

    def _validate_sequence(self, text: str) -> "str | None":
        """Returns None if valid, or the error message."""
        if not text:
            return self.tr("Enter a sequence.")
        try:
            _parse_sequence(text.replace(" ", ""))
            return None
        except ValueError as e:
            return str(e)

    def _on_generate(self):
        text = self._seq_edit.text().strip()
        if self._validate_sequence(text) is not None:
            return

        self.sequence = text

        if self._rb_cascade.isChecked():
            self.method   = "cascade"
            self.sub_type = None
        else:
            self.method = "step_by_step"
            self.sub_type = "pneumatic" if self._rb_pneumatic.isChecked() else "electric"

        self.accept()
```

- [ ] **Step 4: Migrate `graphics/utils/properties_dialog.py`, fixing the default-argument pitfall**

```python
"""Generic dialog for editing diagram components' properties."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt


class PropertiesDialog(QDialog):
    def __init__(self, title: str | None = None, parent=None):
        super().__init__(parent)
        if title is None:
            title = self.tr("Properties")
        self.setWindowTitle(title)
        self.setMinimumWidth(320)
        self.setModal(True)

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setSpacing(12)
        self._main_layout.setContentsMargins(16, 16, 16, 16)

        # internal title
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self._main_layout.addWidget(title_label)

        # separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        self._main_layout.addWidget(line)

        # field area (populated by add_field)
        self._form_layout = QFormLayout()
        self._form_layout.setSpacing(8)
        self._form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._main_layout.addLayout(self._form_layout)

        self._main_layout.addStretch()

        # buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._cancel_btn = QPushButton(self.tr("Cancel"))
        self._cancel_btn.clicked.connect(self.reject)

        self._ok_btn = QPushButton(self.tr("OK"))
        self._ok_btn.setDefault(True)
        self._ok_btn.clicked.connect(self._validate_and_accept)

        btn_layout.addWidget(self._cancel_btn)
        btn_layout.addWidget(self._ok_btn)
        self._main_layout.addLayout(btn_layout)

        # Exposed for subclasses (e.g. DefectDialog) that need to insert
        # extra buttons between Cancel and OK/Apply.
        self._btn_layout = btn_layout

    def add_text_field(self, label: str, placeholder: str = "", value: str = "") -> QLineEdit:
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setText(value)
        self._form_layout.addRow(label, field)
        return field

    def add_combo_field(self, label: str, options: list[str], current: str = "") -> QComboBox:
        combo = QComboBox()
        combo.addItems(options)
        if current in options:
            combo.setCurrentText(current)
        self._form_layout.addRow(label, combo)
        return combo

    def add_bool_field(self, label: str, value: bool = False) -> QCheckBox:
        field = QCheckBox()
        field.setChecked(value)
        self._form_layout.addRow(label, field)
        return field

    def add_no_properties_message(self):
        msg = QLabel(self.tr("This node has no editable properties."))
        msg.setStyleSheet("color: gray; font-style: italic;")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_layout.insertWidget(2, msg)  # after the separator
        self._ok_btn.setEnabled(False)

    def add_number_field(
        self,
        label: str,
        placeholder: str = "",
        value: float | None = None,
        required: bool = False,
        min_value: float | None = None,
    ) -> QLineEdit:
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        if value is not None:
            field.setText(str(value))

        field._is_number_field = True
        field._is_required = required
        field._min_value = min_value

        field.textChanged.connect(self._refresh_ok_button)

        def on_edit_finished():
            self._validate_field(field)

        field.editingFinished.connect(on_edit_finished)
        self._form_layout.addRow(label, field)

        # validates initial state (a required empty field already starts with a border)
        self._validate_field(field)
        self._refresh_ok_button()

        return field

    def _validate_field(self, field: QLineEdit) -> bool:
        """Validates a single field. Returns True if ok."""
        text = field.text().strip()
        required = getattr(field, "_is_required", False)

        if not text:
            if required:
                field.setStyleSheet("border: 1px solid red;")
                return False
            field.setStyleSheet("")
            return True

        try:
            parsed = float(text)
        except ValueError:
            field.setStyleSheet("border: 1px solid red;")
            return False

        min_value = getattr(field, "_min_value", None)
        if min_value is not None and parsed <= min_value:
            field.setStyleSheet("border: 1px solid red;")
            return False

        field.setStyleSheet("")
        return True

    def _refresh_ok_button(self):
        """Enables OK only when every required field is filled and valid."""
        for i in range(self._form_layout.rowCount()):
            item = self._form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if not item:
                continue
            widget = item.widget()
            if not isinstance(widget, QLineEdit):
                continue
            if not getattr(widget, "_is_number_field", False):
                continue
            if not self._validate_field(widget):
                self._ok_btn.setEnabled(False)
                return
        self._ok_btn.setEnabled(True)

    def _validate_and_accept(self):
        # second line of defense: validates everything before closing
        for i in range(self._form_layout.rowCount()):
            item = self._form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if not item:
                continue
            widget = item.widget()
            if isinstance(widget, QLineEdit) and getattr(widget, "_is_number_field", False):
                if not self._validate_field(widget):
                    return  # doesn't close
        self.accept()
```

- [ ] **Step 5: Migrate `graphics/utils/defect_dialog.py`, same default-argument fix**

`self.tr(...)` is unsafe to call before `super().__init__()` has run (the underlying `QObject` isn't constructed yet), which rules out resolving `DefectDialog`'s own default title inline the way `PropertiesDialog` does. Instead, a module-level helper built on `QCoreApplication.translate` (no `self`/instance dependency, safe to call before any widget exists) resolves the default *before* `super().__init__()` runs, and is passed down as an already-resolved `title` — so `PropertiesDialog` never sees a `None` it would otherwise default to `"Properties"`:

```python
"""Dialog for injecting/removing a defect on a component, during simulation.

Unlike PropertiesDialog (which edits the NodeItem's self.properties, a
project configuration persisted to the saved file), this dialog never
touches self.properties -- it only generates commands sent to the domain
node via NodeItem.command, and the defect lives only as long as the
current simulation is running.
"""

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QDialog, QPushButton

from graphics.utils.properties_dialog import PropertiesDialog


def _default_defect_title() -> str:
    return QCoreApplication.translate("DefectDialog", "Simulate defect")


class DefectDialog(PropertiesDialog):
    """PropertiesDialog with a third button: Cancel / Restore / Apply.

    Restore closes the dialog and signals restore_requested=True, bypassing
    the normal numeric validation (Restore always returns the component to
    its default condition -- there's no field to validate).
    """

    def __init__(self, title: str | None = None, parent=None):
        super().__init__(title=title if title is not None else _default_defect_title(), parent=parent)
        self.restore_requested = False

        self._ok_btn.setText(self.tr("Apply"))

        self._restore_btn = QPushButton(self.tr("Restore"))
        self._restore_btn.clicked.connect(self._on_restore_clicked)
        # btn_layout, before this insertion: [stretch(0), Cancel(1), OK(2)].
        # Inserting at 2 positions Restore between Cancel and Apply (pushes
        # Apply to 3): [stretch, Cancel, Restore, Apply].
        self._btn_layout.insertWidget(2, self._restore_btn)

    def _on_restore_clicked(self) -> None:
        self.restore_requested = True
        QDialog.accept(self)
```

`_default_defect_title()` is re-evaluated on every `DefectDialog()` construction (it's a function call inside `__init__`, not a default parameter value), so it always reflects the currently active language — satisfying the same rule `PropertiesDialog` follows.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_circuit_generator_dialog_text.py tests/test_properties_dialog_text.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Run the full test suite and fix regressions**

Run: `pytest tests/ -v`
Expected: check `tests/test_defect_dialog.py` (asserts `dialog._ok_btn.text() == "Aplicar"` and `labels == ["Cancelar", "Restaurar", "Aplicar"]`) and every other test constructing `PropertiesDialog`/`DefectDialog` with a default title or asserting on `"Cancelar"`/`"OK"`/`"Aplicar"`/`"Restaurar"` — update to `"Cancel"`/`"OK"`/`"Apply"`/`"Restore"`. Grep first: `grep -rn "Cancelar\|Restaurar\|Aplicar" tests/`.

- [ ] **Step 8: Commit**

```bash
git add main_window/ui/circuit_generator_dialog.py graphics/utils/properties_dialog.py graphics/utils/defect_dialog.py tests/test_circuit_generator_dialog_text.py tests/test_properties_dialog_text.py
git commit -m "feat: migrate circuit-generator, properties and defect dialog strings"
```

---

## Task 9: Migrate node context-menu strings and update dependent tests

**Files:**
- Modify: `graphics/items/base/nodes/node_item.py`
- Modify: `graphics/items/base/nodes/cylinder/cylinder_item.py`
- Modify: `graphics/items/base/nodes/coil/coil_item.py`
- Modify: `graphics/items/base/nodes/switch/contact.py`
- Modify: `graphics/items/base/nodes/directional_valve/directional_valve_item.py`
- Modify: `graphics/items/base/connections/connection_item.py`
- Modify: `tests/test_context_menu_simulate_mode.py`
- Modify: `tests/test_node_item_defect_hooks.py`
- Modify: `tests/test_contact_button_mode.py`
- Modify: `tests/test_directional_valve_button_actuator_mode.py`
- Modify: `tests/test_directional_valve_item_defect_dialog_shared.py`
- Modify: `tests/test_directional_valve_item_three_position.py`
- Modify: `tests/test_valve_3_2_ways_defect_dialog.py`
- Modify: `tests/test_valve_4_2_ways_defect_dialog.py`
- Modify: `tests/test_valve_4_3_ways_item.py`
- Modify: `tests/test_defect_dialog.py`

All these classes extend `DiagramItemBase(QGraphicsObject)`, so `self.tr(...)` is available directly.

String changes:

| Old | New |
|---|---|
| `"Simular defeito..."` | `"Simulate defect..."` |
| `"Propriedades..."` | `"Properties..."` |
| `"Adicionar label"` | `"Add label"` |
| `"Tipo de contato"` | `"Contact type"` |
| `"Retido"` | `"Latched"` |
| `"Momentâneo"` | `"Momentary"` |
| `"Atuador esquerdo"` | `"Left actuator"` |
| `"Atuador direito"` | `"Right actuator"` |
| `"Posição padrão"` | `"Default position"` |
| `"Direita (0)"` / `"Direita (1)"` | `"Right (0)"` / `"Right (1)"` |
| `"Centro (1)"` | `"Center (1)"` |
| `"Esquerda (1)"` / `"Esquerda (2)"` | `"Left (1)"` / `"Left (2)"` |
| `"Sensor retraído"` | `"Retracted sensor"` |
| `"Sensor estendido"` | `"Extended sensor"` |
| `"Estado inicial"` | `"Initial state"` |
| `"Retraído"` | `"Retracted"` |
| `"Estendido"` | `"Extended"` |
| `"Erro ao renomear sensor"` | `"Error renaming sensor"` |
| `"Erro ao renomear"` | `"Error renaming"` |
| `"Já existe um sensor com o nome '{new_name}'."` | `"A sensor named '{0}' already exists."` |
| `"Já existe um sinal com o nome '{new_name}'."` | `"A signal named '{0}' already exists."` |
| `"Deletar waypoint"` | `"Delete waypoint"` |

("Button" and "None" are already English literals and stay unchanged, `tr()`-wrapped for consistency.)

- [ ] **Step 1: Write the failing tests (update existing test assertions to the new English text)**

Edit `tests/test_context_menu_simulate_mode.py` — replace every quoted string per the table above (lines 118, 195-198, 210-212, 225-231, 242, 253, 264-266, 277-279 per the current grep; also the two docstring mentions at lines 3 and 183 for accuracy). Representative diff for the block at 195-198:

```python
    assert "Simulate defect..." in labels
    assert "Properties..." not in labels
    ...
    assert "Add label" not in labels
```

and 264-266 / 277-279:

```python
    assert "Retracted sensor" not in submenu_titles
    assert "Extended sensor" not in submenu_titles
    assert "Initial state" not in submenu_titles
    ...
    assert "Retracted sensor" in submenu_titles
    assert "Extended sensor" in submenu_titles
    assert "Initial state" in submenu_titles
```

Edit `tests/test_node_item_defect_hooks.py` lines 42-62: `"Propriedades..."` → `"Properties..."`, `"Simular defeito..."` → `"Simulate defect..."`.

Edit `tests/test_contact_button_mode.py` lines 173, 185, 196, 208, 217: `"Retido"` → `"Latched"`, `"Momentâneo"` → `"Momentary"`.

Edit `tests/test_directional_valve_button_actuator_mode.py` lines 156, 167, 178, 188: same `"Retido"`/`"Momentâneo"` → `"Latched"`/`"Momentary"`.

Edit `tests/test_directional_valve_item_defect_dialog_shared.py` lines 3, 88-89: `"Simular defeito..."` → `"Simulate defect..."`, `"Propriedades..."` → `"Properties..."`.

Edit `tests/test_directional_valve_item_three_position.py` lines 46, 49, 51, 65, 67, 69:
```python
    assert "Default position" in submenu_titles
    ...
    rest_menu = next(a.menu() for a in full_menu.actions() if a.text() == "Default position")
    ...
    assert option_labels == ["Right (0)", "Left (1)"]
    ...
    assert option_labels == ["Right (0)", "Center (1)", "Left (2)"]
```

Edit `tests/test_valve_3_2_ways_defect_dialog.py` lines 145-147: `"Simular defeito..."` → `"Simulate defect..."`, `"Propriedades..."` → `"Properties..."`, `"Atuador esquerdo"` → `"Left actuator"`.

Edit `tests/test_valve_4_2_ways_defect_dialog.py` (same pattern — grep to confirm exact lines, apply same substitutions).

Edit `tests/test_valve_4_3_ways_item.py` lines 71, 74, 76:
```python
    assert "Default position" in submenu_titles
    ...
    rest_menu = next(a.menu() for a in menu.actions() if a.text() == "Default position")
    ...
    assert option_labels == ["Right (0)", "Center (1)", "Left (2)"]
```

Edit `tests/test_defect_dialog.py` line 14: `assert dialog._ok_btn.text() == "Apply"` (this string was already covered by Task 8's `"Aplicar"` → `"Apply"` change; if Task 8 was completed first this file is already correct — verify with `grep -n "Aplicar\|Restaurar\|Cancelar" tests/test_defect_dialog.py` and fix any stragglers, e.g. `labels == ["Cancel", "Restore", "Apply"]`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_context_menu_simulate_mode.py tests/test_node_item_defect_hooks.py tests/test_contact_button_mode.py tests/test_directional_valve_button_actuator_mode.py tests/test_directional_valve_item_defect_dialog_shared.py tests/test_directional_valve_item_three_position.py tests/test_valve_3_2_ways_defect_dialog.py tests/test_valve_4_2_ways_defect_dialog.py tests/test_valve_4_3_ways_item.py tests/test_defect_dialog.py -v`
Expected: FAIL — every updated assertion fails against the still-Portuguese source strings

- [ ] **Step 3: Migrate `node_item.py`'s context menu**

```python
    def extend_context_menu(self, menu: QMenu) -> None:
        if self.simulation_mode:
            defect_dialog = self.build_defect_dialog()
            if defect_dialog is not None:
                defect_action = menu.addAction(self.tr("Simulate defect..."))
                defect_action.triggered.connect(lambda: self._open_defect_dialog(defect_dialog))
            super().extend_context_menu(menu)
            return

        props_action = menu.addAction(self.tr("Properties..."))
        props_action.triggered.connect(self._open_properties_dialog)
        menu.addSeparator()

        rotate_action = menu.addAction(self.tr("Rotate 90°"))
        rotate_action.setShortcut("R")

        def _rotate():
            undo_stack = getattr(getattr(self, "editor", None), "undo_stack", None)
            scene = self.scene()
            before = undo_stack.snapshot(scene) if (undo_stack and scene) else None
            self.rotate(90)
            if before is not None:
                undo_stack.push_snapshot(scene, self.editor, before, self.tr("Rotate component"))

        rotate_action.triggered.connect(_rotate)
        menu.addSeparator()

        add_label_action = menu.addAction(self.tr("Add label"))
        # ... rest unchanged
```

- [ ] **Step 4: Migrate `contact.py`'s context menu (and the rename-error message elsewhere in the same file)**

```python
    def extend_context_menu(self, menu: QMenu):
        if self.simulation_mode:
            super().extend_context_menu(menu)
            return

        menu.addSeparator()

        contact_menu = menu.addMenu(self.tr("Contact type"))
        for t in ("NO", "NC"):
            action = QAction(t, menu, checkable=True)
            action.setChecked(self.properties.get("contact_type") == t)
            action.triggered.connect(lambda _, x=t: self.set_contact_type(x))
            contact_menu.addAction(action)

        super().extend_context_menu(menu)

        menu.addSeparator()
        self._add_button_actuator_menu(menu)

        actuator_signals = self._available_actuator_signals()
        for sensor_name in actuator_signals:
            action = QAction(sensor_name, menu, checkable=True)

            is_checked = (
                getattr(self, "current_relay", None) == sensor_name
            )
            action.setChecked(is_checked)

            action.triggered.connect(
                lambda _, n=sensor_name: self.set_actuator_sensor(n)
            )
            menu.addAction(action)

    def _add_button_actuator_menu(self, menu: QMenu):
        """"Button" gets a submenu instead of a flat action, so the user
        can pick latch (toggle) or momentary (active while held)."""
        button_menu = menu.addMenu(self.tr("Button"))
        current_mode = (
            self.properties.get("button_mode", DEFAULT_BUTTON_MODE)
            if self.properties.get("actuator_sensor") == BUTTON_SENSOR
            else None
        )

        for mode, label in (("latch", self.tr("Latched")), ("momentary", self.tr("Momentary"))):
            action = QAction(label, button_menu, checkable=True)
            action.setChecked(current_mode == mode)
            action.triggered.connect(lambda _, m=mode: self.set_button_actuator(m))
            button_menu.addAction(action)
```

`("NO", "NC")` are already-English electrical-contact standard abbreviations, correctly left as bare literals.

- [ ] **Step 5: Migrate `directional_valve_item.py`'s context menu**

```python
    def extend_context_menu(self, menu: QMenu):
        super().extend_context_menu(menu)
        if self.simulation_mode:
            return
        menu.addSeparator()

        left_menu = menu.addMenu(self.tr("Left actuator"))
        right_menu = menu.addMenu(self.tr("Right actuator"))

        self._populate_actuator_menu(left_menu, side="left")
        self._populate_actuator_menu(right_menu, side="right")

        menu.addSeparator()
        rest_menu = menu.addMenu(self.tr("Default position"))
        if self.THREE_POSITION:
            rest_options = [
                ("right", self.tr("Right (0)")),
                ("center", self.tr("Center (1)")),
                ("left", self.tr("Left (2)")),
            ]
            current_default = self.properties.get("default_side", "center")
        else:
            rest_options = [
                ("right", self.tr("Right (0)")),
                ("left", self.tr("Left (1)")),
            ]
            current_default = self.properties.get("default_side", "right")
        for opt, label in rest_options:
            action = QAction(label, menu, checkable=True)
            action.setChecked(current_default == opt)
            action.triggered.connect(lambda _, o=opt: self._set_default_side(o))
            rest_menu.addAction(action)

    def _populate_actuator_menu(self, menu: QMenu, side: str):
        current = self.actuators.get(side)

        action_none = QAction(self.tr("None"), menu, checkable=True)
        action_none.setChecked(current is None)
        action_none.triggered.connect(
            lambda _, s=side: self.set_actuator(s, None)
        )
        menu.addAction(action_none)
        menu.addSeparator()

        for name, desc in ACTUATOR_DICT.items():
            if not desc.get("menu", True):
                continue
            if self.THREE_POSITION and name == "spring":
                continue
            if name == "button":
                self._add_button_actuator_menu(menu, side, desc, current)
                continue
            action = QAction(desc["label"], menu, checkable=True)
            action.setChecked(current is not None and current.get("type") == name)
            action.triggered.connect(
                lambda _, s=side, n=name: self.set_actuator(s, n)
            )
            menu.addAction(action)

        if self.sensor_registry:
            cylinder_signals = self.sensor_registry.list_names(sensor_type="cylinder_end")
            if cylinder_signals:
                menu.addSeparator()
                for sensor_name in cylinder_signals:
                    action = QAction(sensor_name, menu, checkable=True)
                    is_checked = (
                        current is not None
                        and current.get("type") == "limit_switch"
                        and current.get("sensor_name") == sensor_name
                    )
                    action.setChecked(is_checked)
                    action.triggered.connect(
                        lambda _, s=side, n=sensor_name: self.set_actuator(s, "limit_switch", n)
                    )
                    menu.addAction(action)

            electric_signals = self.sensor_registry.list_names(sensor_type="solenoid_coil")
            if electric_signals:
                menu.addSeparator()
                for sensor_name in electric_signals:
                    action = QAction(sensor_name, menu, checkable=True)
                    is_checked = (
                        current is not None
                        and current.get("type") == "solenoid"
                        and current.get("sensor_name") == sensor_name
                    )
                    action.setChecked(is_checked)
                    action.triggered.connect(
                        lambda _, s=side, n=sensor_name: self.set_actuator(s, "solenoid", n)
                    )
                    menu.addAction(action)

    def _add_button_actuator_menu(self, menu: QMenu, side: str, desc: dict, current: dict | None):
        """"Button" gets a submenu instead of a flat action, so the user
        can pick latch (toggle) or momentary (active while held)."""
        button_menu = menu.addMenu(desc["label"])
        current_mode = current.get("mode", DEFAULT_BUTTON_MODE) if current and current.get("type") == "button" else None

        for mode, label in (("latch", self.tr("Latched")), ("momentary", self.tr("Momentary"))):
            action = QAction(label, button_menu, checkable=True)
            action.setChecked(current_mode == mode)
            action.triggered.connect(
                lambda _, s=side, m=mode: self.set_actuator(s, "button", mode=m)
            )
            button_menu.addAction(action)
```

Note `desc["label"]` (from `ACTUATOR_DICT`) is out of scope here — it's the same kind of scattered per-descriptor string as the `palette_meta()` names, tracked in Task 12.

- [ ] **Step 6: Migrate `cylinder_item.py`'s context menu and rename-error message**

```python
        if not ok:
            sensor["name"] = old_name
            if label:
                label.set_text(old_name)
            QMessageBox.warning(
                None,
                self.tr("Error renaming sensor"),
                self.tr("A sensor named '{0}' already exists.").format(new_name),
            )
            return

        sensor["name"] = new_name
        if label:
            label.set_text(new_name)

    def extend_context_menu(self, menu):
        super().extend_context_menu(menu)
        if self.simulation_mode:
            return
        menu.addSeparator()

        r_menu = menu.addMenu(self.tr("Retracted sensor"))
        e_menu = menu.addMenu(self.tr("Extended sensor"))

        self._populate_sensor_menu(r_menu, "retracted")
        self._populate_sensor_menu(e_menu, "extended")

        menu.addSeparator()
        state_menu = menu.addMenu(self.tr("Initial state"))
        for opt, label in [("retracted", self.tr("Retracted")), ("extended", self.tr("Extended"))]:
            action = QAction(label, menu, checkable=True)
            action.setChecked(self.properties.get("default_state", "retracted") == opt)
            action.triggered.connect(lambda _, o=opt: self._set_default_state(o))
            state_menu.addAction(action)

    # ... _set_default_state unchanged ...

    def _populate_sensor_menu(self, menu, position):
        sensor = self.properties["sensors"][position]
        current = sensor.get("type")

        action_none = QAction(self.tr("None"), menu, checkable=True)
        action_none.setChecked(current is None)
        action_none.triggered.connect(
            lambda _, p=position: self.set_sensor(p, None)
        )
        menu.addAction(action_none)

        menu.addSeparator()

        for name, desc in SENSOR_DICT.items():
            action = QAction(desc["label"], menu, checkable=True)
            action.setChecked(current == name)
            action.triggered.connect(
                lambda _, p=position, n=name: self.set_sensor(p, n)
            )
            menu.addAction(action)
```

(`SENSOR_DICT`'s `desc["label"]` — same Task 12 deferral as `ACTUATOR_DICT`.)

- [ ] **Step 7: Migrate `coil_item.py`'s rename-error message**

```python
        if not ok:
            if label:
                label.set_text(old_name)
            QMessageBox.warning(
                None,
                self.tr("Error renaming"),
                self.tr("A signal named '{0}' already exists.").format(new_name),
            )
            return
```

- [ ] **Step 8: Migrate `connection_item.py`'s waypoint context menu**

```python
    def _show_wp_context_menu(self, wp_idx: int, event):
        menu   = QMenu()
        action = QAction(self.tr("Delete waypoint"), menu)
        action.triggered.connect(lambda: self._delete_waypoint(wp_idx))
        menu.addAction(action)
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        pos  = view.mapToGlobal(view.mapFromScene(event.scenePos())) if view else event.screenPos().toPoint()
        menu.exec(pos)
```

- [ ] **Step 9: Run the updated test files to verify they pass**

Run: `pytest tests/test_context_menu_simulate_mode.py tests/test_node_item_defect_hooks.py tests/test_contact_button_mode.py tests/test_directional_valve_button_actuator_mode.py tests/test_directional_valve_item_defect_dialog_shared.py tests/test_directional_valve_item_three_position.py tests/test_valve_3_2_ways_defect_dialog.py tests/test_valve_4_2_ways_defect_dialog.py tests/test_valve_4_3_ways_item.py tests/test_defect_dialog.py -v`
Expected: PASS

- [ ] **Step 10: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS. Also grep for any remaining hits the earlier sweep might have missed: `grep -rn "Deletar\|Erro ao renomear\|Já existe um" tests/ graphics/ main_window/ persistence/` — fix anything found.

- [ ] **Step 11: Commit**

```bash
git add graphics/items/base/nodes/ graphics/items/base/connections/connection_item.py tests/test_context_menu_simulate_mode.py tests/test_node_item_defect_hooks.py tests/test_contact_button_mode.py tests/test_directional_valve_button_actuator_mode.py tests/test_directional_valve_item_defect_dialog_shared.py tests/test_directional_valve_item_three_position.py tests/test_valve_3_2_ways_defect_dialog.py tests/test_valve_4_2_ways_defect_dialog.py tests/test_valve_4_3_ways_item.py tests/test_defect_dialog.py
git commit -m "feat: migrate node context-menu strings, update dependent test assertions"
```

---

## Task 10: Generate and populate the translation catalogs

**Files:**
- Create: `resources/i18n/circuiteditor_en.ts` (generated, not hand-edited)
- Create: `resources/i18n/circuiteditor_pt_BR.ts` (generated, then hand-populated)
- Create: `resources/i18n/circuiteditor_en.qm` (compiled)
- Create: `resources/i18n/circuiteditor_pt_BR.qm` (compiled)
- Test: `tests/test_pt_br_translation_loads.py`

**Interfaces:**
- No new code interfaces — this task produces the data files `LanguageManager.apply_language` (Task 2) already expects at `resources/i18n/circuiteditor_pt_BR.qm`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pt_br_translation_loads.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from main_window.language import language_manager
from main_window.main_window import MainWindow


def test_switching_to_pt_br_translates_a_known_menu_title():
    window = MainWindow()
    try:
        language_manager.apply_language(app, "pt_BR")
        window.retranslate_ui()
        assert window.menus["file"].title() == "Arquivo"
    finally:
        language_manager.apply_language(app, "en")
        window.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pt_br_translation_loads.py -v`
Expected: FAIL — `FileNotFoundError: Translation file not found or invalid: .../resources/i18n/circuiteditor_pt_BR.qm`

- [ ] **Step 3: Generate the `.ts` files with `pylupdate6`**

Run from the project root:
```bash
venv/Scripts/pylupdate6.exe app.py $(find main_window graphics persistence editor circuit_generator simulation -name '*.py') -ts resources/i18n/circuiteditor_en.ts resources/i18n/circuiteditor_pt_BR.ts
```

(On Windows PowerShell, expand the file list first: `$files = Get-ChildItem -Recurse -Include *.py main_window,graphics,persistence,editor,circuit_generator,simulation | Select-Object -ExpandProperty FullName; venv\Scripts\pylupdate6.exe app.py $files -ts resources\i18n\circuiteditor_en.ts resources\i18n\circuiteditor_pt_BR.ts`)

This scans every `tr()` / `QCoreApplication.translate()` call across the migrated files and writes two `.ts` files with the same set of extracted `<source>` entries (one per file, since two target languages were passed).

- [ ] **Step 4: Leave `circuiteditor_en.ts` translations empty (source IS English)**

No edits needed — `pylupdate6` already leaves every `<translation type="unfinished"></translation>` empty, and English needs no `.qm` at all per `LanguageManager` (only `pt_BR` loads a translator). `circuiteditor_en.ts` is generated for completeness/tooling parity but is not compiled or shipped.

- [ ] **Step 5: Populate `circuiteditor_pt_BR.ts`**

Open `resources/i18n/circuiteditor_pt_BR.ts` and fill in every `<translation>` element. For strings that were Portuguese in the original source (the large majority — see the tables in Tasks 4-9), the translation is simply the original Portuguese text, e.g.:

```xml
<context>
    <name>NodeItem</name>
    <message>
        <source>Simulate defect...</source>
        <translation>Simular defeito...</translation>
    </message>
    <message>
        <source>Properties...</source>
        <translation>Propriedades...</translation>
    </message>
    <message>
        <source>Add label</source>
        <translation>Adicionar label</translation>
    </message>
</context>
```

For strings that were already English in the source (e.g. `"New"`, `"Open"`, `"Save"`, `"Delete"`, `"Copy"`, `"Paste"`, `"Undo"`, `"Redo"`, `"About"`, `"Run"`, `"Step Back"`, `"Step Forward"`, `"Select"`, `"Connect"`, `"Simulate"`, `"Zoom In"`, `"Zoom Out"`, `"Fit to Contents"`, `"Font Size..."`), write a real Portuguese translation, e.g. `"New"` → `"Novo"`, `"Open"` → `"Abrir"`, `"Save"` → `"Salvar"`, `"Delete"` → `"Excluir"`, `"Copy"` → `"Copiar"`, `"Paste"` → `"Colar"`, `"Undo"` → `"Desfazer"`, `"Redo"` → `"Refazer"`, `"About"` → `"Sobre"`, `"Select"` → `"Selecionar"`, `"Connect"` → `"Conectar"`, `"Simulate"` → `"Simular"`.

Cross-check every `<source>` against the tables already spelled out in Tasks 4-9 (they list the exact English text and, where applicable, the exact original Portuguese text) rather than re-translating from scratch — the mapping is already fully specified there.

- [ ] **Step 6: Compile to `.qm`**

Run: `python scripts/compile_translations.py`
Expected output: `compiled resources/i18n/circuiteditor_en.qm` and `compiled resources/i18n/circuiteditor_pt_BR.qm`

(`circuiteditor_en.qm` is a byproduct of compiling every `.ts` in the directory; harmless, `LanguageManager` never loads it since English needs no translator.)

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_pt_br_translation_loads.py -v`
Expected: PASS

- [ ] **Step 8: Manually smoke-test live switching**

Run: `python app.py`, open View → Language → Português (Brasil), confirm the menu bar, toolbar, palette, and action texts visibly update with no restart; switch back to English and confirm they revert.

- [ ] **Step 9: Commit**

```bash
git add resources/i18n/ tests/test_pt_br_translation_loads.py
git commit -m "feat: generate and populate EN/PT-BR translation catalogs"
```

---

## Task 11: Packaging verification and settings-persistence integration test

**Files:**
- Modify: `CircuitEditor.spec` (comment only, if anything)
- Modify: `CircuitEditor-onefile.spec` (comment only, if anything)
- Test: `tests/test_language_persists_across_sessions.py`

**Interfaces:** none new — this task verifies existing behavior end-to-end.

- [ ] **Step 1: Confirm the PyInstaller spec already bundles `resources/i18n/`**

Both `CircuitEditor.spec` and `CircuitEditor-onefile.spec` already declare `datas=[('resources', 'resources'), ...]` (whole-directory bundling), so `resources/i18n/*.qm` is picked up automatically — no `datas` change needed. Confirm by reading both spec files: `grep -n "resources" CircuitEditor.spec CircuitEditor-onefile.spec`.

- [ ] **Step 2: Add a one-line clarifying comment to both spec files**

Edit `CircuitEditor.spec` (and identically in `CircuitEditor-onefile.spec`), just above the `datas=[` block:

```python
# `resources` also carries resources/i18n/*.qm (Qt Linguist translation
# catalogs) -- bundled automatically as part of the whole-directory copy,
# no separate datas entry needed.
```

- [ ] **Step 3: Write the persistence integration test**

```python
# tests/test_language_persists_across_sessions.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from PyQt6.QtCore import QSettings
from main_window.language import apply_language, get_language, DEFAULT_LANGUAGE


def test_language_choice_survives_a_new_settings_read():
    settings = QSettings("tcc-circuitos-tests", "PersistenceIntegrationTest")
    settings.clear()

    apply_language(app, "pt_BR", settings)

    # Simulate a fresh app start reading the same underlying QSettings scope.
    reread = QSettings("tcc-circuitos-tests", "PersistenceIntegrationTest")
    assert get_language(reread) == "pt_BR"

    apply_language(app, DEFAULT_LANGUAGE, settings)  # leave state clean
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_language_persists_across_sessions.py -v`
Expected: PASS (this exercises real `QSettings`/`QTranslator` code paths already built in Task 2 — no new production code needed, so no red step is expected here; if it fails, it's a genuine regression to fix, not a missing-feature red)

- [ ] **Step 5: Run a real PyInstaller build and confirm the `.qm` is present**

Run: `pyinstaller CircuitEditor.spec` then check the output directory: `ls dist/CircuitEditor/resources/i18n/` (or the onedir path the spec produces) — confirm `circuiteditor_pt_BR.qm` is there. Launch the built executable, switch to Português (Brasil), confirm it works identically to the dev run in Task 10 Step 8.

- [ ] **Step 6: Manual QA checklist (run once, by hand, not automatable)**

- [ ] Switch language with the palette dock, a menu open, and the toolbar visible — confirm every visible piece of text updates live, no restart.
- [ ] Open the Circuit Generator dialog (`Ctrl+G` / File → New from Sequence) in English, switch language, close it, reopen it — confirm it now shows Portuguese.
- [ ] Trigger a defect dialog (right-click a component during simulation) in both languages — confirm "Simulate defect" / "Apply" / "Restore" / "Cancel" are correctly localized.
- [ ] Save/open a file, trigger a save error (e.g. read-only destination) in both languages — confirm the error dialog title/body localize.
- [ ] Confirm the two language-picker labels ("English" / "Português (Brasil)") never themselves change when switching languages.
- [ ] Restart the app after choosing Português (Brasil) — confirm it launches directly in Portuguese (persistence).
- [ ] On a machine/VM with the OS locale set to a non-PT-BR, non-EN language (e.g. French), delete any persisted `ui/language` setting and confirm first launch defaults to English.

- [ ] **Step 7: Commit**

```bash
git add CircuitEditor.spec CircuitEditor-onefile.spec tests/test_language_persists_across_sessions.py
git commit -m "test: verify language persistence and PyInstaller packaging"
```

---

## Task 12: Deferred-work inventory for per-node-type strings

**Files:**
- Create: `docs/superpowers/plans/2026-09-01-language-switching-followup-inventory.md`

**Interfaces:** none — this is a documentation task producing a concrete, actionable checklist for a follow-up sweep, per the spec's explicit non-goal on 100% v1 string coverage.

Per the spec (`docs/superpowers/specs/2026-09-01-language-switching-design.md`, Non-goals section), full coverage isn't a v1 gate. What's left after Tasks 1-11: the property-dialog field labels and `palette_meta(name=...)` display names defined individually inside each node-type file under `graphics/items/base/nodes/**` (e.g. `fixed_displacement_motor.py`'s `"Limite P_max (Pa) — opcional"` field label, `ACTUATOR_DICT`/`SENSOR_DICT` entry `"label"` values referenced in Task 9). These follow the exact same mechanical pattern demonstrated in Tasks 4-9 (`self.tr("...")`, rewrite PT→EN, add the PT text as the `pt_BR.ts` translation) — there's just a lot of them, scattered one or two per file across dozens of node types.

- [ ] **Step 1: Generate the inventory**

Run:
```bash
grep -rn 'add_number_field(\|add_text_field(\|add_combo_field(\|add_bool_field(\|palette_meta(' graphics/items/base/nodes/ --include=*.py | grep -v __pycache__ > /tmp/followup_raw.txt
```

(or the PowerShell equivalent: `Select-String -Path graphics\items\base\nodes\*.py,graphics\items\base\nodes\**\*.py -Pattern 'add_number_field\(|add_text_field\(|add_combo_field\(|add_bool_field\(|palette_meta\('`)

- [ ] **Step 2: Write the checklist file**

```markdown
# Follow-up: per-node-type string migration inventory

Generated 2026-09-01 as a tracked follow-up to
[2026-09-01-language-switching.md](2026-09-01-language-switching.md)
(Task 12) -- not migrated in that plan per the spec's non-goal on 100%
v1 string coverage.

## Pattern

Identical to Tasks 4-9 of the parent plan: wrap each literal in
`self.tr("...")`, rewrite Portuguese source text to English, add the
original Portuguese text as the `pt_BR.ts` translation for that string
(re-run `pylupdate6` per Task 10 Step 3 to pick up the new `tr()` calls,
then fill in `circuiteditor_pt_BR.ts` and recompile via
`scripts/compile_translations.py`).

## Inventory

[paste the grep output from Step 1 here, one file:line per row]

## Suggested batching

Group by node file (each file's fields/labels form one self-contained
task, same shape as Task 9's per-file steps) rather than by string type
-- a reviewer can approve/reject one node type's migration independently
of another's.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-09-01-language-switching-followup-inventory.md
git commit -m "docs: inventory remaining per-node-type strings for a follow-up sweep"
```

---

## Final verification (after Task 12)

Run: `pytest tests/ -v`
Expected: full suite PASS.

Run: `python app.py`, exercise the manual QA checklist from Task 11 Step 6 once more end-to-end.
