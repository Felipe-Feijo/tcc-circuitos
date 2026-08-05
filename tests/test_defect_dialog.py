import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QDialog

app = QApplication.instance() or QApplication([])

from graphics.utils.defect_dialog import DefectDialog


def test_ok_button_relabeled_to_aplicar():
    dialog = DefectDialog(title="Test")
    assert dialog._ok_btn.text() == "Aplicar"


def test_has_three_buttons_in_order_cancelar_restaurar_aplicar():
    dialog = DefectDialog(title="Test")
    labels = [
        dialog._btn_layout.itemAt(i).widget().text()
        for i in range(dialog._btn_layout.count())
        if dialog._btn_layout.itemAt(i).widget() is not None
    ]
    assert labels == ["Cancelar", "Restaurar", "Aplicar"]


def test_restore_requested_defaults_to_false():
    dialog = DefectDialog(title="Test")
    assert dialog.restore_requested is False


def test_clicking_restore_sets_flag_and_accepts_without_validation():
    dialog = DefectDialog(title="Test")
    # campo obrigatório vazio -- validação normal do OK/Aplicar falharia aqui
    dialog.add_number_field("K", value=None, required=True)
    dialog._restore_btn.click()
    assert dialog.restore_requested is True
    assert dialog.result() == QDialog.DialogCode.Accepted
