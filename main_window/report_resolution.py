"""Resolve o destino final do relatório de simulação: mantém, move ou descarta."""

import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox


def resolve_report(parent, report_dir: str, circuit_name: str) -> None:
    """Decide o destino de um relatório já montado num diretório temporário.

    Pergunta ao usuário via popup se deseja manter o relatório. Se a
    resposta for manter, abre um diálogo para escolher a pasta de destino
    e move os arquivos para lá. Em qualquer outro caso (usuário recusa o
    popup, ou cancela o diálogo de pasta), apaga o diretório temporário.

    Args:
        parent: Widget pai para os diálogos Qt (pode ser None em testes).
        report_dir: Diretório temporário com relatorio.html, graficos.pdf
            e, se gerado, video.mp4.
        circuit_name: Usado para sugerir o nome da pasta de destino.
    """
    answer = QMessageBox.question(
        parent,
        "Relatório de simulação",
        "Deseja salvar o relatório desta simulação?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        shutil.rmtree(report_dir, ignore_errors=True)
        return

    dest_parent = QFileDialog.getExistingDirectory(parent, "Salvar relatório em")
    if not dest_parent:
        shutil.rmtree(report_dir, ignore_errors=True)
        return

    folder_name = f"relatorio_{circuit_name}_{datetime.now():%Y%m%d_%H%M%S}"
    dest = str(Path(dest_parent) / folder_name)
    shutil.move(report_dir, dest)
