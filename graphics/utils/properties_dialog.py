"""Diálogo genérico de edição de propriedades de componentes do diagrama."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt


class PropertiesDialog(QDialog):
    def __init__(self, title="Properties", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(320)
        self.setModal(True)

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setSpacing(12)
        self._main_layout.setContentsMargins(16, 16, 16, 16)

        # título interno
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self._main_layout.addWidget(title_label)

        # separador
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        self._main_layout.addWidget(line)

        # área de campos (preenchida por add_field)
        self._form_layout = QFormLayout()
        self._form_layout.setSpacing(8)
        self._form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._main_layout.addLayout(self._form_layout)

        self._main_layout.addStretch()

        # botões
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._cancel_btn = QPushButton("Cancelar")
        self._cancel_btn.clicked.connect(self.reject)

        self._ok_btn = QPushButton("OK")
        self._ok_btn.setDefault(True)
        self._ok_btn.clicked.connect(self._validate_and_accept)

        btn_layout.addWidget(self._cancel_btn)
        btn_layout.addWidget(self._ok_btn)
        self._main_layout.addLayout(btn_layout)

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
        msg = QLabel("This node has no editable properties.")
        msg.setStyleSheet("color: gray; font-style: italic;")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_layout.insertWidget(2, msg)  # após separador
        self._ok_btn.setEnabled(False)

    def add_number_field(
        self,
        label: str,
        placeholder: str = "",
        value: float | None = None,
        required: bool = False,
    ) -> QLineEdit:
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        if value is not None:
            field.setText(str(value))

        field._is_number_field = True
        field._is_required = required

        field.textChanged.connect(self._refresh_ok_button)

        def on_edit_finished():
            self._validate_field(field)

        field.editingFinished.connect(on_edit_finished)
        self._form_layout.addRow(label, field)

        # valida estado inicial (campo vazio obrigatório já começa com borda)
        self._validate_field(field)
        self._refresh_ok_button()

        return field

    def _validate_field(self, field: QLineEdit) -> bool:
        """Valida um campo individualmente. Retorna True se ok."""
        text = field.text().strip()
        required = getattr(field, "_is_required", False)

        if not text:
            if required:
                field.setStyleSheet("border: 1px solid red;")
                return False
            field.setStyleSheet("")
            return True

        try:
            float(text)
            field.setStyleSheet("")
            return True
        except ValueError:
            field.setStyleSheet("border: 1px solid red;")
            return False

    def _refresh_ok_button(self):
        """Habilita OK só quando todos os campos obrigatórios estão preenchidos e válidos."""
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
        # segunda linha de defesa: valida tudo antes de fechar
        for i in range(self._form_layout.rowCount()):
            item = self._form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if not item:
                continue
            widget = item.widget()
            if isinstance(widget, QLineEdit) and getattr(widget, "_is_number_field", False):
                if not self._validate_field(widget):
                    return  # não fecha
        self.accept()