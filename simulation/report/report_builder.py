"""Builds the simulation report's final artifacts: charts, PDF, video and HTML."""

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


def build_charts(frames: list) -> list:
    """Builds a position-vs-time chart per piston present in the frames.

    Args:
        frames: List of `Frame` (see `frame_recorder.Frame`), in
            increasing `sim_time` order.

    Returns:
        One `matplotlib.figure.Figure` per piston `node_id` found, in
        alphabetical id order. Empty list if `frames` is empty.
    """
    series: dict[str, list[tuple[float, float]]] = {}
    for frame in frames:
        for node_id, position in frame.piston_positions.items():
            series.setdefault(node_id, []).append((frame.sim_time, position))

    figures = []
    for node_id in sorted(series):
        points = series[node_id]
        times = [t for t, _ in points]
        positions = [p for _, p in points]

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(times, positions, marker="o", markersize=3)
        ax.set_title(f"Posição do pistão — {node_id}")
        ax.set_xlabel("Tempo (s)")
        ax.set_ylabel("Posição (0 = recuado, 1 = avançado)")
        ax.set_ylim(-0.05, 1.05)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        figures.append(fig)

    return figures


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


def build_html(chart_pngs: list, has_video: bool) -> str:
    """Builds the report's self-contained HTML.

    Args:
        chart_pngs: Trajectory chart PNGs, embedded in base64.
        has_video: If True, references `video.mp4` (a file alongside
            the HTML); if False, shows a message in place of the player.
    """
    charts_html = "".join(
        '<img src="data:image/png;base64,{}" alt="Gráfico de trajetória" '
        'style="max-width:100%;margin-bottom:24px;">'.format(base64.b64encode(png).decode("ascii"))
        for png in chart_pngs
    )
    video_html = (
        '<video controls style="max-width:100%;">'
        '<source src="video.mp4" type="video/mp4"></video>'
        if has_video else
        "<p>Vídeo não disponível para esta simulação.</p>"
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


def build(frames: list, out_dir: str) -> None:
    """Builds the report's 3 artifacts (`relatorio.html`, `graficos.pdf`,
    `video.mp4`) in `out_dir`.

    A failure building the video doesn't stop the HTML/PDF from being
    generated -- the HTML reflects the video's absence (see `build_html`).

    Args:
        frames: Frames recorded by the `FrameRecorder` (can be empty).
        out_dir: Directory the files will be written to (must already exist).
    """
    figures = build_charts(frames)
    try:
        if figures:
            save_pdf(figures, os.path.join(out_dir, "graficos.pdf"))
            chart_pngs = save_chart_pngs(figures)
        else:
            # Create an empty PDF with a blank page when there are no figures
            blank_fig = plt.figure(figsize=(8, 6))
            with PdfPages(os.path.join(out_dir, "graficos.pdf")) as pdf:
                pdf.savefig(blank_fig)
            plt.close(blank_fig)
            chart_pngs = []
    finally:
        for fig in figures:
            plt.close(fig)

    frame_paths = [f.image_path for f in frames if os.path.exists(f.image_path)]
    has_video = build_video(frame_paths, os.path.join(out_dir, "video.mp4"))

    _delete_frame_images(frames)

    html = build_html(chart_pngs, has_video)
    with open(os.path.join(out_dir, "relatorio.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
