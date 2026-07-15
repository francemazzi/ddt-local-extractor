"""Tests for OCR engine (mocked unit tests)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ddt_local.config import load_config
from ddt_local.ocr import OcrEngine, OcrResult
from ddt_local.ollama import GenerateResult


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.generate_from_image.return_value = GenerateResult(
        text="DDT numero NE/2026/0714-018\nFornitore: Acciai Nordest",
        model="glm-ocr:latest",
        duration_seconds=1.0,
    )
    return client


def test_ocr_image_returns_text(mock_client, tmp_path):
    img = tmp_path / "page.png"
    img.write_bytes(b"fake-png")
    engine = OcrEngine(load_config(), client=mock_client)
    result = engine.ocr_image(img, page_number=1)
    assert "DDT" in result.text
    assert result.page_number == 1


def test_ocr_images_combines_pages(mock_client, tmp_path):
    images = []
    for i in range(1, 3):
        p = tmp_path / f"p{i}.png"
        p.write_bytes(b"x")
        images.append((i, p))

    engine = OcrEngine(load_config(), client=mock_client)
    result = engine.ocr_images(images)
    assert isinstance(result, OcrResult)
    assert len(result.pages) == 2
    assert "--- Page 1 ---" in result.combined_text
    assert result.total_duration_seconds >= 0
