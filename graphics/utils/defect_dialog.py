"""Dialog for injecting/removing a defect on a component, during simulation.

Unlike PropertiesDialog (which edits the NodeItem's self.properties, a
project configuration persisted to the saved file), this dialog never
touches self.properties -- it only generates commands sent to the domain
node via NodeItem.command, and the defect lives only as long as the
current simulation is running.
"""

from dataclasses import dataclass
from typing import Literal

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QDialog, QPushButton

from graphics.utils.properties_dialog import PropertiesDialog


@dataclass(frozen=True)
class DefectFieldSpec:
    """One defect field of a component, declared by NodeItem.defect_fields().

    key must match a key of the domain node's DEFECT_FIELDS (see
    simulation/nodes/defect.py) -- it's both the command key and the
    lookup key for prefilling via domain_node.defect_value(key).
    """
    key: str
    label: str  # already translated
    kind: Literal["number", "bool", "choice"]
    options: tuple[tuple[str, str], ...] = ()  # choice: (value, translated label)
    placeholder: str = ""
    min_value: float | None = None


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

        self._defect_fields: dict[str, tuple[DefectFieldSpec, object]] = {}
        self.note_field = None

    def _on_restore_clicked(self) -> None:
        self.restore_requested = True
        QDialog.accept(self)

    # -- Declarative fields (see NodeItem.build_defect_dialog) ------------

    def add_defect_field(self, spec: DefectFieldSpec, value):
        """Adds the widget for `spec`, prefilled with `value` (None = empty/off)."""
        if spec.kind == "number":
            widget = self.add_number_field(
                spec.label, placeholder=spec.placeholder, value=value,
                required=True, min_value=spec.min_value,
            )
        elif spec.kind == "bool":
            widget = self.add_bool_field(spec.label, value=bool(value))
        elif spec.kind == "choice":
            widget = self.add_combo_field(spec.label, list(spec.options), current=value)
        else:
            raise ValueError(f"unknown defect field kind: {spec.kind!r}")
        self._defect_fields[spec.key] = (spec, widget)
        return widget

    def defect_widget(self, key: str):
        return self._defect_fields[key][1]

    def defect_values(self) -> dict:
        """{key: value} for every declared field, in insertion order."""
        values = {}
        for key, (spec, widget) in self._defect_fields.items():
            if spec.kind == "number":
                values[key] = float(widget.text().strip())
            elif spec.kind == "bool":
                values[key] = widget.isChecked()
            else:
                values[key] = widget.currentData()
        return values

    def add_note_field(self):
        """Free-text note shown on the report chart's defect marker."""
        self.note_field = self.add_text_field(
            QCoreApplication.translate("DefectDialog", "Note (optional)"),
            placeholder=QCoreApplication.translate("DefectDialog", "e.g. debris in the orifice"),
        )
        return self.note_field

    def note_text(self) -> str:
        return self.note_field.text().strip() if self.note_field is not None else ""
