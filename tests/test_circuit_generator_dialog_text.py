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


import pytest
from main_window.language import language_manager

# (sequence, expected English message, expected pt_BR message)
_PARSER_ERRORS = [
    ("xyz", "Invalid sequence: 'xyz'", "Sequência inválida: 'xyz'"),
    ("((A+)A-)", "Invalid sequence: nested parentheses are not allowed in '((A+)A-)'",
     "Sequência inválida: parênteses aninhados não são permitidos em '((A+)A-)'"),
    ("A+)A-", "Invalid sequence: ')' without matching '(' in 'A+)A-'",
     "Sequência inválida: ')' sem '(' correspondente em 'A+)A-'"),
    ("(A+A-", "Invalid sequence: '(' without matching ')' in '(A+A-'",
     "Sequência inválida: '(' sem ')' correspondente em '(A+A-'"),
    ("(A+A-)", "Cylinder 'A' repeated within the same simultaneous group in '(A+A-)'",
     "Cilindro 'A' repetido dentro do mesmo grupo simultâneo em '(A+A-)'"),
    ("A+A+A-", "Cylinder 'A' tries to move '+' while already extended. "
               "Consecutive moves in the same direction are invalid.",
     "Cilindro 'A' tenta mover para '+' estando já estendido. "
     "Movimentos consecutivos na mesma direção são inválidos."),
    ("A-A-A+", "Cylinder 'A' tries to move '-' while already retracted. "
               "Consecutive moves in the same direction are invalid.",
     "Cilindro 'A' tenta mover para '-' estando já retraído. "
     "Movimentos consecutivos na mesma direção são inválidos."),
    ("A+B+A-", "Cylinder 'B' does not close the cycle: first move '+', last '+'. "
               "The sequence must return each cylinder to its initial state.",
     "Cilindro 'B' não fecha o ciclo: primeiro movimento '+', último '+'. "
     "A sequência deve retornar cada cilindro ao seu estado inicial."),
]


@pytest.mark.parametrize("seq, en, _pt", _PARSER_ERRORS)
def test_parser_error_is_english(seq, en, _pt):
    dialog = CircuitGeneratorDialog()
    try:
        assert dialog._validate_sequence(seq) == en
    finally:
        dialog.close()


@pytest.mark.parametrize("seq, _en, pt", _PARSER_ERRORS)
def test_parser_error_is_translated_to_pt_br(seq, _en, pt):
    language_manager.apply_language(app, "pt_BR")
    dialog = CircuitGeneratorDialog()
    try:
        assert dialog._validate_sequence(seq) == pt
    finally:
        dialog.close()
        language_manager.apply_language(app, "en")
