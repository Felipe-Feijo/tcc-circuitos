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
