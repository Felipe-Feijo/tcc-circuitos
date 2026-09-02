import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import glob

from PIL import Image

from simulation.report.frame_recorder import Frame
from simulation.report.report_builder import build


def _frames_with_images(tmp_path, gauge_readings=None):
    frames = []
    for i in range(3):
        img_path = tmp_path / f"frame_{i}.png"
        Image.new("RGB", (64, 48), color=(i * 50, 0, 0)).save(img_path)
        frames.append(Frame(
            step_index=i,
            sim_time=i * 0.1,
            piston_positions={"c1": i / 2.0},
            image_path=str(img_path),
            gauge_readings=dict(gauge_readings[i]) if gauge_readings else {},
        ))
    return frames


def test_build_writes_html_pdf_and_video(tmp_path):
    frames = _frames_with_images(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    build(frames, str(out_dir))

    html_path = out_dir / "relatorio.html"
    pdf_path = out_dir / "graficos.pdf"
    video_path = out_dir / "video.mp4"

    assert html_path.exists() and html_path.stat().st_size > 0
    assert pdf_path.exists() and pdf_path.stat().st_size > 0
    assert video_path.exists() and video_path.stat().st_size > 0

    html = html_path.read_text(encoding="utf-8")
    assert "<video" in html
    assert 'href="graficos.pdf"' in html


def test_build_includes_gauge_chart_in_html(tmp_path):
    gauge_readings = [{"g1": 0.0}, {"g1": 5e6}, {"g1": 3e6}]
    frames = _frames_with_images(tmp_path, gauge_readings=gauge_readings)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    build(frames, str(out_dir))

    html = (out_dir / "relatorio.html").read_text(encoding="utf-8")
    assert html.count("<img") == 2  # 1 gráfico de pistão + 1 de manômetro
    assert "Manômetros" in html


def test_build_degrades_gracefully_without_video(tmp_path, monkeypatch):
    import simulation.report.report_builder as rb
    monkeypatch.setattr(rb, "build_video", lambda *a, **kw: False)

    frames = _frames_with_images(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    build(frames, str(out_dir))

    html = (out_dir / "relatorio.html").read_text(encoding="utf-8")
    assert (out_dir / "graficos.pdf").exists()
    assert not (out_dir / "video.mp4").exists()
    assert "<video" not in html
    assert "Vídeo não disponível" in html


def test_build_handles_no_frames(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    build([], str(out_dir))

    assert (out_dir / "relatorio.html").exists()
    assert (out_dir / "graficos.pdf").exists()


def test_build_deletes_frame_pngs_from_out_dir(tmp_path):
    """Reproduz o cenário real: FrameRecorder grava os PNGs dentro do
    próprio `out_dir` (seu temp_dir). Depois de build(), só os 3
    artefatos finais devem sobrar — nenhum frame_*.png."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    frames = []
    for i in range(3):
        img_path = out_dir / f"frame_{i:05d}.png"
        Image.new("RGB", (64, 48), color=(i * 50, 0, 0)).save(img_path)
        frames.append(Frame(
            step_index=i,
            sim_time=i * 0.1,
            piston_positions={"c1": i / 2.0},
            image_path=str(img_path),
        ))

    build(frames, str(out_dir))

    remaining_frame_pngs = glob.glob(str(out_dir / "frame_*.png"))
    assert remaining_frame_pngs == []

    assert (out_dir / "relatorio.html").exists()
    assert (out_dir / "graficos.pdf").exists()
    assert (out_dir / "video.mp4").exists()
