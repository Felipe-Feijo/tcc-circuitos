import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from PyQt6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])

import main_window.report_resolution as rr


def _make_report_dir(tmp_path):
    report_dir = tmp_path / "temp_report"
    report_dir.mkdir()
    (report_dir / "relatorio.html").write_text("<html></html>", encoding="utf-8")
    return str(report_dir)


def test_user_declines_discards_files(tmp_path, monkeypatch):
    report_dir = _make_report_dir(tmp_path)

    monkeypatch.setattr(rr.QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No)

    rr.resolve_report(None, report_dir, circuit_name="teste")

    assert not os.path.exists(report_dir)


def test_user_accepts_then_cancels_dialog_discards_files(tmp_path, monkeypatch):
    report_dir = _make_report_dir(tmp_path)

    monkeypatch.setattr(rr.QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(rr.QFileDialog, "getExistingDirectory", lambda *a, **kw: "")

    rr.resolve_report(None, report_dir, circuit_name="teste")

    assert not os.path.exists(report_dir)


def test_user_accepts_and_picks_folder_moves_files(tmp_path, monkeypatch):
    report_dir = _make_report_dir(tmp_path)
    dest_parent = tmp_path / "destino"
    dest_parent.mkdir()

    monkeypatch.setattr(rr.QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(rr.QFileDialog, "getExistingDirectory", lambda *a, **kw: str(dest_parent))

    rr.resolve_report(None, report_dir, circuit_name="teste")

    assert not os.path.exists(report_dir)
    moved = list(dest_parent.iterdir())
    assert len(moved) == 1
    assert moved[0].name.startswith("relatorio_teste_")
