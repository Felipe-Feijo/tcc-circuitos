import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import matplotlib
matplotlib.use("Agg")

from simulation.report.frame_recorder import Frame
from simulation.report.report_builder import build_charts, save_pdf, save_chart_pngs


def _frames():
    return [
        Frame(step_index=0, sim_time=0.0, piston_positions={"c1": 0.0, "c2": 1.0}, image_path=""),
        Frame(step_index=1, sim_time=0.1, piston_positions={"c1": 0.5, "c2": 1.0}, image_path=""),
        Frame(step_index=2, sim_time=0.2, piston_positions={"c1": 1.0, "c2": 0.0}, image_path=""),
    ]


def test_build_charts_returns_one_figure_per_piston():
    figures = build_charts(_frames())
    assert len(figures) == 2


def test_build_charts_handles_no_frames():
    assert build_charts([]) == []


def test_save_pdf_writes_a_page_per_figure(tmp_path):
    figures = build_charts(_frames())
    out = tmp_path / "graficos.pdf"

    save_pdf(figures, str(out))

    assert out.exists()
    assert out.stat().st_size > 0


def test_save_chart_pngs_returns_one_png_per_figure():
    figures = build_charts(_frames())
    pngs = save_chart_pngs(figures)

    assert len(pngs) == len(figures)
    for png in pngs:
        assert png.startswith(b"\x89PNG")
