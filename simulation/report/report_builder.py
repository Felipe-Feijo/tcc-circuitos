"""Monta os artefatos finais do relatório de simulação: gráficos, PDF, vídeo e HTML."""

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
    """Monta um gráfico de posição × tempo por pistão presente nos frames.

    Args:
        frames: Lista de `Frame` (ver `frame_recorder.Frame`), em ordem
            crescente de `sim_time`.

    Returns:
        Uma `matplotlib.figure.Figure` por `node_id` de pistão encontrado,
        em ordem alfabética de id. Lista vazia se `frames` estiver vazia.
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
    """Escreve todas as figuras num único PDF, uma por página."""
    with PdfPages(path) as pdf:
        for fig in figures:
            pdf.savefig(fig)


def save_chart_pngs(figures: list) -> list:
    """Exporta cada figura como PNG em memória, para embutir no HTML."""
    pngs = []
    for fig in figures:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100)
        pngs.append(buf.getvalue())
    return pngs


def build_video(frame_paths: list, path: str, fps: int = 10) -> bool:
    """Monta um MP4 a partir de uma sequência de PNGs, um frame por step.

    Args:
        frame_paths: Caminhos dos PNGs em ordem cronológica.
        path: Caminho de saída do arquivo .mp4.
        fps: Quadros por segundo do vídeo gerado (independente do `dt` da
            simulação — um `dt` muito pequeno geraria um vídeo
            imperceptivelmente rápido se usado diretamente como fps).

    Returns:
        True se o vídeo foi gerado com sucesso, False se `frame_paths`
        estiver vazio ou se o encoder falhar (ex: binário ffmpeg
        indisponível). Nunca lança exceção.
    """
    if not frame_paths:
        return False

    try:
        with imageio.get_writer(path, fps=fps, codec="libx264", quality=8) as writer:
            for frame_path in frame_paths:
                writer.append_data(imageio.v2.imread(frame_path))
        return True
    except Exception:
        logger.exception("falha ao montar vídeo do relatório")
        return False


def build_html(chart_pngs: list, has_video: bool) -> str:
    """Monta o HTML autocontido do relatório.

    Args:
        chart_pngs: PNGs dos gráficos de trajetória, embutidos em base64.
        has_video: Se True, referencia `video.mp4` (arquivo ao lado do
            HTML); se False, mostra uma mensagem no lugar do player.
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


def build(frames: list, out_dir: str) -> None:
    """Monta os 3 artefatos do relatório (`relatorio.html`, `graficos.pdf`,
    `video.mp4`) em `out_dir`.

    Falha ao montar o vídeo não impede a geração do HTML/PDF — o HTML
    reflete a ausência do vídeo (ver `build_html`).

    Args:
        frames: Frames gravados pelo `FrameRecorder` (pode ser vazio).
        out_dir: Diretório onde os arquivos serão escritos (já deve existir).
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

    html = build_html(chart_pngs, has_video)
    with open(os.path.join(out_dir, "relatorio.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
