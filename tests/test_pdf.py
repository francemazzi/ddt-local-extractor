"""Tests for PDF processing (unit, no Ollama)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ddt_local.config import load_config
from ddt_local.pdf import analyze_pdf, cleanup_render_dir, render_page_png

DATASET = Path(__file__).resolve().parents[1] / "dataset"
NATIVE = DATASET / "01_DDT_Acciai_Nordest.pdf"
SCAN = DATASET / "08_DDT_Inox_Labirinto_scansione.pdf"


@pytest.fixture
def config():
    return load_config()


def test_analyze_native_pdf_has_text(config,):
    if not NATIVE.exists():
        pytest.skip("dataset PDF not available")
    analysis = analyze_pdf(NATIVE, config)
    assert analysis.page_count >= 1
    assert analysis.total_native_chars > config.min_native_text_chars


def test_analyze_scan_pdf_needs_ocr(config):
    if not SCAN.exists():
        pytest.skip("dataset PDF not available")
    analysis = analyze_pdf(SCAN, config)
    assert analysis.needs_visual_ocr


def test_render_page_creates_png(config, tmp_path):
    if not NATIVE.exists():
        pytest.skip("dataset PDF not available")
    rendered = render_page_png(NATIVE, 1, config, output_dir=tmp_path)
    assert rendered.image_path.exists()
    assert rendered.image_path.suffix == ".png"


def test_cleanup_render_dir(tmp_path):
    f = tmp_path / "img.png"
    f.write_bytes(b"png")
    cleanup_render_dir(tmp_path)
    assert not f.exists()
