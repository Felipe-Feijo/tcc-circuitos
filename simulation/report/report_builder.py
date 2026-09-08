"""Builds the simulation report's final artifacts: charts, PDF, video, HTML and data txt."""

import base64
import io
import logging
import os

import imageio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

logger = logging.getLogger(__name__)


def _collect_piston_series(frames: list) -> dict[str, list[tuple[float, float]]]:
    """Groups (sim_time, position) points per piston node_id, in frame order."""
    series: dict[str, list[tuple[float, float]]] = {}
    for frame in frames:
        for node_id, position in frame.piston_positions.items():
            series.setdefault(node_id, []).append((frame.sim_time, position))
    return series


def _collect_gauge_series(frames: list) -> dict[str, list[tuple[float, float | bool]]]:
    """Groups (sim_time, reading) points per gauge node_id, in frame order."""
    series: dict[str, list[tuple[float, float | bool]]] = {}
    for frame in frames:
        for node_id, reading in frame.gauge_readings.items():
            series.setdefault(node_id, []).append((frame.sim_time, reading))
    return series


def _assign_display_names(node_ids: list, node_names: dict | None, type_label: str) -> dict[str, str]:
    """Resolves each node_id to a display name for report titles: the
    user-given name if set, otherwise an auto-numbered fallback
    ("Cilindro 1", "Cilindro 2", ...) in the given order -- report
    titles must never show the raw node_id (an opaque UUID).

    `node_ids` must be given in the same order across build_charts/
    build_gauge_charts/build_data_txt (currently `sorted(series)`) so
    the chart, PDF and data txt agree on which number goes to which
    node.
    """
    node_names = node_names or {}
    display = {}
    counter = 0
    for node_id in node_ids:
        name = node_names.get(node_id)
        if not name:
            counter += 1
            name = f"{type_label} {counter}"
        display[node_id] = name
    return display


def build_charts(frames: list, node_names: dict | None = None,
                  digital_pistons: set | None = None) -> list:
    """Builds a position-vs-time chart per piston present in the frames.

    Args:
        frames: List of `Frame` (see `frame_recorder.Frame`), in
            increasing `sim_time` order.
        node_names: Optional node_id -> user-given display name map
            (see `frame_recorder.FrameRecorder._collect_node_names`).
            Pistons with no entry get an auto-numbered "Cilindro N"
            title -- never the raw node_id.
        digital_pistons: Optional set of node_ids with no continuous
            position -- non-hydraulic (pneumatic) pistons jump straight
            to 0 or 1, never passing through an intermediate value (see
            `frame_recorder.FrameRecorder._collect_digital_pistons`).
            Plotted as a step, not a linearly-interpolated ramp that
            never physically existed.

    Returns:
        One `matplotlib.figure.Figure` per piston `node_id` found, in
        alphabetical id order. Empty list if `frames` is empty.
    """
    series = _collect_piston_series(frames)
    display_names = _assign_display_names(sorted(series), node_names, "Cilindro")
    digital_pistons = digital_pistons or set()

    figures = []
    for node_id in sorted(series):
        points = series[node_id]
        times = [t for t, _ in points]
        positions = [p for _, p in points]
        drawstyle = "steps-post" if node_id in digital_pistons else "default"

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(times, positions, marker="o", markersize=3, drawstyle=drawstyle)
        ax.set_title(f"Posição do pistão — {display_names[node_id]}")
        ax.set_xlabel("Tempo (s)")
        ax.set_ylabel("Posição (0 = recuado, 1 = avançado)")
        ax.set_ylim(-0.05, 1.05)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        figures.append(fig)

    return figures


def build_gauge_charts(frames: list, node_names: dict | None = None) -> list:
    """Builds a reading-vs-time chart per pressure gauge present in the frames.

    Hydraulic gauges (numeric readings, in Pa) get a continuous line;
    pneumatic gauges (boolean readings) get a 0/1 step chart labeled
    Despressurizado/Pressurizado, since the pneumatic domain has no
    real pressure magnitude to plot.

    Args:
        frames: List of `Frame` (see `frame_recorder.Frame`), in
            increasing `sim_time` order.
        node_names: Optional node_id -> user-given display name map.
            Gauges with no entry get an auto-numbered "Manômetro N"
            title -- never the raw node_id.

    Returns:
        One `matplotlib.figure.Figure` per gauge `node_id` found, in
        alphabetical id order. Empty list if `frames` is empty.
    """
    series = _collect_gauge_series(frames)
    display_names = _assign_display_names(sorted(series), node_names, "Manômetro")

    figures = []
    for node_id in sorted(series):
        points = series[node_id]
        times = [t for t, _ in points]
        readings = [r for _, r in points]
        is_binary = isinstance(readings[0], bool)

        fig, ax = plt.subplots(figsize=(8, 4))
        if is_binary:
            ax.plot(times, [1.0 if r else 0.0 for r in readings],
                    drawstyle="steps-post", marker="o", markersize=3)
            ax.set_title(f"Pressão — {display_names[node_id]}")
            ax.set_ylabel("Despressurizado (0) / Pressurizado (1)")
            ax.set_ylim(-0.05, 1.05)
        else:
            ax.plot(times, readings, marker="o", markersize=3)
            ax.set_title(f"Pressão — {display_names[node_id]}")
            ax.set_ylabel("Pressão (Pa)")
        ax.set_xlabel("Tempo (s)")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        figures.append(fig)

    return figures


def _series_section(title: str, xlabel: str, ylabel: str, column: str, points: list) -> str:
    """Formats one chart's data as a commented header plus a CSV table."""
    header = f"# {title}\n# xlabel: {xlabel}\n# ylabel: {ylabel}\ntempo_s,{column}\n"
    rows = "\n".join(f"{t},{1 if v is True else 0 if v is False else v}" for t, v in points)
    return header + rows + "\n"


def build_data_txt(frames: list, node_names: dict | None = None) -> str:
    """Builds a plain-text dump of every chart's underlying x/y data and
    title metadata, so the charts can be redrawn independently later.

    Args:
        frames: List of `Frame` (see `frame_recorder.Frame`), in
            increasing `sim_time` order.
        node_names: Optional node_id -> user-given display name map --
            same fallback/numbering rules as `build_charts`, and same
            resulting names, since both share `_assign_display_names`
            over the same sorted id order.

    Returns:
        One section per piston/gauge, each a `#`-commented header
        (title, xlabel, ylabel) followed by a CSV table (`tempo_s,<col>`).
        Sections are separated by a blank line, in the same alphabetical
        order as `build_charts`/`build_gauge_charts`. A placeholder
        comment if no series was recorded.
    """
    piston_series = _collect_piston_series(frames)
    gauge_series = _collect_gauge_series(frames)

    if not piston_series and not gauge_series:
        return "# Nenhum dado registrado\n"

    piston_names = _assign_display_names(sorted(piston_series), node_names, "Cilindro")
    gauge_names = _assign_display_names(sorted(gauge_series), node_names, "Manômetro")

    sections = []
    for node_id in sorted(piston_series):
        sections.append(_series_section(
            f"Posição do pistão — {piston_names[node_id]}", "Tempo (s)",
            "Posição (0 = recuado, 1 = avançado)", "posicao", piston_series[node_id],
        ))
    for node_id in sorted(gauge_series):
        points = gauge_series[node_id]
        is_binary = isinstance(points[0][1], bool)
        if is_binary:
            sections.append(_series_section(
                f"Pressão — {gauge_names[node_id]}", "Tempo (s)",
                "Despressurizado (0) / Pressurizado (1)", "pressurizado", points,
            ))
        else:
            sections.append(_series_section(
                f"Pressão — {gauge_names[node_id]}", "Tempo (s)", "Pressão (Pa)", "pressao_pa", points,
            ))

    return "\n".join(sections)


def save_pdf(figures: list, path: str) -> None:
    """Writes every figure into a single PDF, one per page."""
    with PdfPages(path) as pdf:
        for fig in figures:
            pdf.savefig(fig)


def save_chart_pngs(figures: list) -> list:
    """Exports each figure as an in-memory PNG, to embed in the HTML."""
    pngs = []
    for fig in figures:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100)
        pngs.append(buf.getvalue())
    return pngs


def build_video(frame_paths: list, path: str, fps: int = 10) -> bool:
    """Builds an MP4 from a sequence of PNGs, one frame per step.

    Args:
        frame_paths: PNG paths in chronological order.
        path: Output path for the .mp4 file.
        fps: Frames per second of the generated video (independent of
            the simulation's `dt` -- a very small `dt` would produce an
            imperceptibly fast video if used directly as fps).

    Returns:
        True if the video was generated successfully, False if
        `frame_paths` is empty or the encoder fails (e.g. the ffmpeg
        binary is unavailable). Never raises.
    """
    if not frame_paths:
        return False

    try:
        with imageio.get_writer(path, fps=fps, codec="libx264", quality=8) as writer:
            for frame_path in frame_paths:
                writer.append_data(imageio.v2.imread(frame_path))
        return True
    except Exception:
        logger.exception("failed to build the report's video")
        return False


def _pngs_to_html(pngs: list, alt: str) -> str:
    return "".join(
        '<img src="data:image/png;base64,{}" alt="{}" '
        'style="max-width:100%;margin-bottom:24px;">'.format(base64.b64encode(png).decode("ascii"), alt)
        for png in pngs
    )


def build_html(chart_pngs: list, has_video: bool, gauge_pngs: list | None = None) -> str:
    """Builds the report's self-contained HTML.

    Args:
        chart_pngs: Trajectory chart PNGs, embedded in base64.
        has_video: If True, references `video.mp4` (a file alongside
            the HTML); if False, shows a message in place of the player.
        gauge_pngs: Pressure gauge chart PNGs, embedded in base64.
            Section omitted entirely if empty/None.
    """
    charts_html = _pngs_to_html(chart_pngs, "Gráfico de trajetória")
    video_html = (
        '<video controls style="max-width:100%;">'
        '<source src="video.mp4" type="video/mp4"></video>'
        if has_video else
        "<p>Vídeo não disponível para esta simulação.</p>"
    )
    gauges_html = (
        f"<h2>Manômetros</h2>\n{_pngs_to_html(gauge_pngs, 'Gráfico de pressão')}"
        if gauge_pngs else ""
    )

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<title>Relatório de Simulação</title>
</head>
<body>
<h1>Relatório de Simulação</h1>
<h2>Circuito ao longo do tempo</h2>
{video_html}
<h2>Trajetória dos pistões</h2>
{charts_html}
{gauges_html}
<p><a href="graficos.pdf">Ver gráficos (PDF)</a></p>
</body>
</html>
"""


def _delete_frame_images(frames: list) -> None:
    """Deletes each frame's raw PNGs after the video has been built (or
    attempted). They shouldn't be left over in `out_dir` alongside the
    report's final artifacts. An already-missing file isn't an error."""
    for frame in frames:
        try:
            os.remove(frame.image_path)
        except OSError:
            pass


def build(frames: list, out_dir: str, node_names: dict | None = None,
          digital_pistons: set | None = None) -> None:
    """Builds the report's artifacts (`relatorio.html`, `graficos.pdf`,
    `video.mp4`, `dados.txt`) in `out_dir`.

    A failure building the video doesn't stop the HTML/PDF from being
    generated -- the HTML reflects the video's absence (see `build_html`).

    Args:
        frames: Frames recorded by the `FrameRecorder` (can be empty).
        out_dir: Directory the files will be written to (must already exist).
        node_names: Optional node_id -> user-given display name map
            (see `frame_recorder.ReportData.node_names`), used for
            chart/PDF/data-txt titles instead of the raw node_id.
        digital_pistons: Optional set of node_ids with no continuous
            position (see `frame_recorder.ReportData.digital_pistons`),
            plotted as a step instead of an interpolated ramp.
    """
    figures = build_charts(frames, node_names, digital_pistons)
    gauge_figures = build_gauge_charts(frames, node_names)
    all_figures = figures + gauge_figures
    try:
        if all_figures:
            save_pdf(all_figures, os.path.join(out_dir, "graficos.pdf"))
            chart_pngs = save_chart_pngs(figures)
            gauge_pngs = save_chart_pngs(gauge_figures)
        else:
            # Create an empty PDF with a blank page when there are no figures
            blank_fig = plt.figure(figsize=(8, 6))
            with PdfPages(os.path.join(out_dir, "graficos.pdf")) as pdf:
                pdf.savefig(blank_fig)
            plt.close(blank_fig)
            chart_pngs = []
            gauge_pngs = []
    finally:
        for fig in all_figures:
            plt.close(fig)

    frame_paths = [f.image_path for f in frames if os.path.exists(f.image_path)]
    has_video = build_video(frame_paths, os.path.join(out_dir, "video.mp4"))

    _delete_frame_images(frames)

    html = build_html(chart_pngs, has_video, gauge_pngs)
    with open(os.path.join(out_dir, "relatorio.html"), "w", encoding="utf-8") as fh:
        fh.write(html)

    with open(os.path.join(out_dir, "dados.txt"), "w", encoding="utf-8") as fh:
        fh.write(build_data_txt(frames, node_names))
