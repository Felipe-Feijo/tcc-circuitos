import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image

from simulation.report.frame_recorder import Frame
from simulation.report.report_builder import build


def _frames_with_images(tmp_path):
    frames = []
    for i in range(3):
        img_path = tmp_path / f"frame_{i}.png"
        Image.new("RGB", (64, 48), color=(i * 50, 0, 0)).save(img_path)
        frames.append(Frame(
            step_index=i,
            sim_time=i * 0.1,
            piston_positions={"c1": i / 2.0},
            image_path=str(img_path),
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
