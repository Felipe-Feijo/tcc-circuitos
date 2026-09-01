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
