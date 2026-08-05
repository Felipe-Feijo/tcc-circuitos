"""Diálogo de injeção/remoção de defeito num componente, durante a simulação.

Diferente de PropertiesDialog (que edita self.properties do NodeItem, uma
configuração de projeto persistida no arquivo salvo), este diálogo nunca
toca em self.properties -- ele só gera comandos enviados ao nó de domínio
via NodeItem.command, e o defeito vive somente enquanto a simulação atual
estiver rodando.
"""

from PyQt6.QtWidgets import QDialog, QPushButton

from graphics.utils.properties_dialog import PropertiesDialog


class DefectDialog(PropertiesDialog):
    """PropertiesDialog com um terceiro botão: Cancelar / Restaurar / Aplicar.

    Restaurar fecha o diálogo e sinaliza restore_requested=True, contornando
    a validação numérica normal (Restaurar sempre volta o componente à
    condição padrão -- não há campo a validar).
    """

    def __init__(self, title="Simular defeito", parent=None):
        super().__init__(title=title, parent=parent)
        self.restore_requested = False

        self._ok_btn.setText("Aplicar")

        self._restore_btn = QPushButton("Restaurar")
        self._restore_btn.clicked.connect(self._on_restore_clicked)
        # btn_layout tem, antes desta inserção: [stretch(0), Cancelar(1), OK(2)].
        # Inserir em 2 posiciona Restaurar entre Cancelar e Aplicar (empurra
        # Aplicar para 3): [stretch, Cancelar, Restaurar, Aplicar].
        self._btn_layout.insertWidget(2, self._restore_btn)

    def _on_restore_clicked(self) -> None:
        self.restore_requested = True
        QDialog.accept(self)
