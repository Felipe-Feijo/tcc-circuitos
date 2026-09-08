import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import matplotlib
matplotlib.use("Agg")

from simulation.report.frame_recorder import Frame
from simulation.report.report_builder import (
    build_charts, save_pdf, save_chart_pngs, build_gauge_charts, build_data_txt,
)


def _frames():
    return [
        Frame(step_index=0, sim_time=0.0, piston_positions={"c1": 0.0, "c2": 1.0}, image_path=""),
        Frame(step_index=1, sim_time=0.1, piston_positions={"c1": 0.5, "c2": 1.0}, image_path=""),
        Frame(step_index=2, sim_time=0.2, piston_positions={"c1": 1.0, "c2": 0.0}, image_path=""),
    ]


def _gauge_frames():
    return [
        Frame(step_index=0, sim_time=0.0, piston_positions={}, image_path="",
              gauge_readings={"g_hyd": 0.0, "g_pneu": False}),
        Frame(step_index=1, sim_time=0.1, piston_positions={}, image_path="",
              gauge_readings={"g_hyd": 5e6, "g_pneu": True}),
        Frame(step_index=2, sim_time=0.2, piston_positions={}, image_path="",
              gauge_readings={"g_hyd": 3e6, "g_pneu": False}),
    ]


def test_build_charts_returns_one_figure_per_piston():
    figures = build_charts(_frames())
    assert len(figures) == 2


def test_build_charts_uses_continuous_line_by_default():
    """No digital_pistons given -- every piston stays a linearly
    interpolated line (the hydraulic case: a real continuous ramp)."""
    figures = build_charts(_frames())
    for fig in figures:
        assert fig.axes[0].lines[0].get_drawstyle() == "default"


def test_build_charts_uses_step_line_for_digital_pistons():
    """A digital (non-hydraulic) piston jumps 0/1 instantly -- no
    intermediate position ever existed, so it must render as a step,
    not an interpolated ramp."""
    figures = build_charts(_frames(), digital_pistons={"c1"})
    by_id = dict(zip(sorted({"c1", "c2"}), figures))

    assert by_id["c1"].axes[0].lines[0].get_drawstyle() == "steps-post"
    assert by_id["c2"].axes[0].lines[0].get_drawstyle() == "default"


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


def test_build_gauge_charts_returns_one_figure_per_gauge():
    figures = build_gauge_charts(_gauge_frames())
    assert len(figures) == 2


def test_build_gauge_charts_handles_no_frames():
    assert build_gauge_charts([]) == []


def test_build_gauge_charts_plots_pa_for_numeric_readings():
    figures = build_gauge_charts(_gauge_frames())
    fig = dict(zip(sorted({"g_hyd", "g_pneu"}), figures))["g_hyd"]
    ax = fig.axes[0]
    assert "Pa" in ax.get_ylabel()
    line = ax.lines[0]
    assert list(line.get_ydata()) == [0.0, 5e6, 3e6]


def test_build_gauge_charts_plots_binary_step_for_boolean_readings():
    figures = build_gauge_charts(_gauge_frames())
    fig = dict(zip(sorted({"g_hyd", "g_pneu"}), figures))["g_pneu"]
    ax = fig.axes[0]
    line = ax.lines[0]
    assert list(line.get_ydata()) == [0.0, 1.0, 0.0]
    assert ax.get_ylim() == pytest.approx((-0.05, 1.05))


def test_build_data_txt_handles_no_frames():
    assert build_data_txt([]) == "# Nenhum dado registrado\n"


def test_build_data_txt_has_one_section_per_piston_with_title_and_csv_rows():
    text = build_data_txt(_frames())

    assert "# Posição do pistão — Cilindro 1" in text
    assert "# xlabel: Tempo (s)" in text
    assert "# ylabel: Posição (0 = recuado, 1 = avançado)" in text
    assert "tempo_s,posicao" in text
    assert "0.0,0.0" in text
    assert "0.1,0.5" in text
    assert "0.2,1.0" in text


def test_build_data_txt_writes_pa_column_for_numeric_gauge():
    text = build_data_txt(_gauge_frames())

    assert "# Pressão — Manômetro 1" in text
    assert "# ylabel: Pressão (Pa)" in text
    assert "tempo_s,pressao_pa" in text
    assert "0.1,5000000.0" in text


def test_build_data_txt_writes_0_1_column_for_binary_gauge():
    text = build_data_txt(_gauge_frames())

    assert "# Pressão — Manômetro 2" in text
    assert "# ylabel: Despressurizado (0) / Pressurizado (1)" in text
    assert "tempo_s,pressurizado" in text
    assert "0.0,0\n" in text
    assert "0.1,1\n" in text


def test_build_data_txt_sections_are_separated_by_a_blank_line():
    text = build_data_txt(_gauge_frames())
    assert "\n\n#" in text


def test_build_charts_title_uses_given_display_name():
    figures = build_charts(_frames(), node_names={"c1": "Cilindro A"})
    fig = dict(zip(sorted({"c1", "c2"}), figures))["c1"]
    assert "Cilindro A" in fig.axes[0].get_title()


def test_build_charts_title_falls_back_to_auto_numbered_name_without_display_name():
    """No display name given for either piston -- title must never show
    the raw node_id, and numbering follows the same alphabetical id
    order build_charts already iterates in."""
    figures = build_charts(_frames())
    by_id = dict(zip(sorted({"c1", "c2"}), figures))
    assert "Cilindro 1" in by_id["c1"].axes[0].get_title()
    assert "Cilindro 2" in by_id["c2"].axes[0].get_title()
    assert "c1" not in by_id["c1"].axes[0].get_title()


def test_build_gauge_charts_title_uses_given_display_name():
    figures = build_gauge_charts(_gauge_frames(), node_names={"g_hyd": "Manômetro da bomba"})
    fig = dict(zip(sorted({"g_hyd", "g_pneu"}), figures))["g_hyd"]
    assert "Manômetro da bomba" in fig.axes[0].get_title()


def test_build_gauge_charts_title_falls_back_to_auto_numbered_name():
    figures = build_gauge_charts(_gauge_frames())
    by_id = dict(zip(sorted({"g_hyd", "g_pneu"}), figures))
    assert "Manômetro 1" in by_id["g_hyd"].axes[0].get_title()
    assert "Manômetro 2" in by_id["g_pneu"].axes[0].get_title()


def test_build_data_txt_title_uses_given_display_name():
    text = build_data_txt(_frames(), node_names={"c1": "Cilindro A", "c2": "Cilindro B"})
    assert "# Posição do pistão — Cilindro A" in text
    assert "# Posição do pistão — Cilindro B" in text
