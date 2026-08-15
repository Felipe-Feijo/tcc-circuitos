"""Monta os artefatos finais do relatório de simulação: gráficos, PDF, vídeo e HTML."""

import io
import logging

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
