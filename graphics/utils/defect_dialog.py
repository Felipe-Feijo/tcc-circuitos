"""Dialog for injecting/removing a defect on a component, during simulation.

Unlike PropertiesDialog (which edits the NodeItem's self.properties, a
project configuration persisted to the saved file), this dialog never
touches self.properties -- it only generates commands sent to the domain
node via NodeItem.command, and the defect lives only as long as the
current simulation is running.
"""

from PyQt6.QtWidgets import QDialog, QPushButton

from graphics.utils.properties_dialog import PropertiesDialog


class DefectDialog(PropertiesDialog):
    """PropertiesDialog with a third button: Cancel / Restore / Apply.

    Restore closes the dialog and signals restore_requested=True, bypassing
    the normal numeric validation (Restore always returns the component to
    its default condition -- there's no field to validate).
    """

    def __init__(self, title="Simular defeito", parent=None):
        super().__init__(title=title, parent=parent)
        self.restore_requested = False

        self._ok_btn.setText("Aplicar")

        self._restore_btn = QPushButton("Restaurar")
        self._restore_btn.clicked.connect(self._on_restore_clicked)
        # btn_layout, before this insertion: [stretch(0), Cancel(1), OK(2)].
        # Inserting at 2 positions Restore between Cancel and Apply (pushes
        # Apply to 3): [stretch, Cancel, Restore, Apply].
        self._btn_layout.insertWidget(2, self._restore_btn)

    def _on_restore_clicked(self) -> None:
        self.restore_requested = True
        QDialog.accept(self)
