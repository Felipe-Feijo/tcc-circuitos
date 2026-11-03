"""Generic dialog for editing diagram components' properties."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt, QCoreApplication


class PropertiesDialog(QDialog):
    def __init__(self, title: str | None = None, parent=None):
        super().__init__(parent)
        if title is None:
            # QCoreApplication.translate(...) with an explicit context,
            # not self.tr(...): a subclass (e.g. DefectDialog) invoking
            # this __init__ via super() has a *different* runtime class,
            # so self.tr() here would resolve to that subclass's Qt
            # context instead of "PropertiesDialog" -- see the module-level
            # gotcha note in main_window/actions/__init__.py.
            title = QCoreApplication.translate("PropertiesDialog", "Properties")
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

        # first validation problem, in words (empty = hidden)
        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: red;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self._main_layout.addWidget(self._error_label)

        # cross-field rules (see add_check)
        self._checks: list = []

        # buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._cancel_btn = QPushButton(QCoreApplication.translate("PropertiesDialog", "Cancel"))
        self._cancel_btn.clicked.connect(self.reject)

        self._ok_btn = QPushButton(QCoreApplication.translate("PropertiesDialog", "OK"))
        self._ok_btn.setDefault(True)
        self._ok_btn.clicked.connect(self._validate_and_accept)

        btn_layout.addWidget(self._cancel_btn)
        btn_layout.addWidget(self._ok_btn)
        self._main_layout.addLayout(btn_layout)

        # Exposed for subclasses (e.g. DefectDialog) that need to insert
        # extra buttons between Cancel and OK/Apply.
        self._btn_layout = btn_layout

    def add_text_field(self, label: str, placeholder: str = "", value: str = "",
                        at_top: bool = False) -> QLineEdit:
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setText(value)
        if at_top:
            self._form_layout.insertRow(0, label, field)
        else:
            self._form_layout.addRow(label, field)
        return field

    def add_combo_field(
        self, label: str, options: list[tuple[object, str]], current: object = None
    ) -> QComboBox:
        """options is a list of (value, display_label) pairs. The combo
        shows display_label (translatable) but the caller reads the
        selection back via combo.currentData() to get the canonical
        value -- keeping display text free to localize without touching
        whatever gets stored in properties / the saved file / compared
        against elsewhere (e.g. "retracted"/"torque"/"NO" must never
        become "Retraído"/"Torque"/"NO" *as stored data* just because the
        UI switched language)."""
        combo = QComboBox()
        for value, display_label in options:
            combo.addItem(display_label, value)
        idx = combo.findData(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        self._form_layout.addRow(label, combo)
        return combo

    def add_bool_field(self, label: str, value: bool = False) -> QCheckBox:
        field = QCheckBox()
        field.setChecked(value)
        self._form_layout.addRow(label, field)
        return field

    def add_number_field(
        self,
        label: str,
        placeholder: str = "",
        value: float | None = None,
        required: bool = False,
        min_value: float | None = None,
        min_inclusive: bool = False,
    ) -> QLineEdit:
        """min_value is an exclusive lower bound (value > min_value);
        min_inclusive=True accepts min_value itself (value >= min_value)."""
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        if value is not None:
            field.setText(str(value))

        field._is_number_field = True
        field._is_required = required
        field._min_value = min_value
        field._min_inclusive = min_inclusive

        field.textChanged.connect(self._refresh_ok_button)

        def on_edit_finished():
            self._validate_field(field)

        field.editingFinished.connect(on_edit_finished)
        self._form_layout.addRow(label, field)

        # validates initial state (a required empty field already starts with a border)
        self._validate_field(field)
        self._refresh_ok_button()

        return field

    def add_check(self, check) -> None:
        """Registers a cross-field rule: check() returns an error message
        (already translated) or None. A failing check disables OK and
        shows its message, like an invalid field."""
        self._checks.append(check)
        self._refresh_ok_button()

    def _field_problem(self, field: QLineEdit) -> tuple[bool, str | None]:
        """(ok, message). message is None for an empty required field --
        the red border is enough there."""
        text = field.text().strip()

        if not text:
            return (not getattr(field, "_is_required", False)), None

        try:
            parsed = float(text)
        except ValueError:
            return False, QCoreApplication.translate("PropertiesDialog", "not a valid number")

        min_value = getattr(field, "_min_value", None)
        if min_value is not None:
            if getattr(field, "_min_inclusive", False):
                if parsed < min_value:
                    return False, QCoreApplication.translate(
                        "PropertiesDialog", "must be at least {0}").format(min_value)
            elif parsed <= min_value:
                return False, QCoreApplication.translate(
                    "PropertiesDialog", "must be greater than {0}").format(min_value)

        return True, None

    def _validate_field(self, field: QLineEdit) -> bool:
        """Validates a single field. Returns True if ok."""
        ok, message = self._field_problem(field)
        field.setStyleSheet("" if ok else "border: 1px solid red;")
        field.setToolTip(message or "")
        return ok

    def _first_problem(self) -> tuple[bool, str | None]:
        """(all_ok, first message) across number fields, then checks."""
        all_ok, first = True, None
        for i in range(self._form_layout.rowCount()):
            item = self._form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            widget = item.widget() if item else None
            if not isinstance(widget, QLineEdit) or not getattr(widget, "_is_number_field", False):
                continue
            if self._validate_field(widget):
                continue
            all_ok = False
            message = widget.toolTip()
            if message and first is None:
                label = self._form_layout.labelForField(widget)
                first = f"{label.text()}: {message}" if label is not None else message
        for check in self._checks:
            message = check()
            if message:
                all_ok = False
                if first is None:
                    first = message
        return all_ok, first

    def _refresh_ok_button(self):
        """Enables OK only when every required field is filled and valid
        and every check passes; shows the first problem's message."""
        all_ok, message = self._first_problem()
        self._ok_btn.setEnabled(all_ok)
        self._error_label.setText(message or "")
        self._error_label.setVisible(bool(message))

    def _validate_and_accept(self):
        # second line of defense: validates everything before closing
        all_ok, _ = self._first_problem()
        if not all_ok:
            return  # doesn't close
        self.accept()