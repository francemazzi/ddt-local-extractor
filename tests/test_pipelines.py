"""Tests for pipeline factory and concrete strategies (mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ddt_local.config import AppConfig, load_config, settings_from_config
from ddt_local.models import PipelineName, SourceDocument
from ddt_local.pipelines import (
    ExtractionPipeline,
    create_pipeline,
    resolve_pipeline_name,
)
from ddt_local.pipelines.native_only import NativeOnlyPipeline
from ddt_local.pipelines.ocr_struct import OcrStructPipeline
from ddt_local.pipelines.vision_direct import VisionDirectPipeline
from ddt_local.pdf import PageTextInfo, PdfAnalysis


@pytest.fixture
def source_doc(tmp_path) -> SourceDocument:
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    return SourceDocument(
        path=pdf,
        filename="test.pdf",
        sha256="abc123",
        size_bytes=8,
        page_count=1,
    )


def test_resolve_pipeline_name_valid():
    assert resolve_pipeline_name("ocr_struct") == PipelineName.OCR_STRUCT
    assert resolve_pipeline_name("VISION_DIRECT") == PipelineName.VISION_DIRECT
    assert resolve_pipeline_name("native_only") == PipelineName.NATIVE_ONLY


def test_resolve_pipeline_name_invalid():
    with pytest.raises(ValueError, match="Unknown pipeline"):
        resolve_pipeline_name("cloud_api")


@pytest.mark.parametrize(
    ("pipeline", "cls"),
    [
        ("ocr_struct", OcrStructPipeline),
        ("vision_direct", VisionDirectPipeline),
        ("native_only", NativeOnlyPipeline),
    ],
)
def test_create_pipeline_returns_concrete_class(
    pipeline: str, cls: type, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DDT_PIPELINE", pipeline)
    monkeypatch.setenv("DDT_HOME", "/tmp/ddt-test")
    config = load_config()
    instance = create_pipeline(config)
    assert isinstance(instance, ExtractionPipeline)
    assert isinstance(instance, cls)
    assert instance.name == pipeline


def test_create_pipeline_unknown_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DDT_PIPELINE", "invalid_pipeline")
    monkeypatch.setenv("DDT_HOME", "/tmp/ddt-test")
    config = load_config()
    with pytest.raises(ValueError, match="Unknown pipeline"):
        create_pipeline(config)


def test_pipeline_name_enum_covers_all_strategies():
    values = {p.value for p in PipelineName}
    assert values == {"ocr_struct", "vision_direct", "native_only"}


def test_settings_from_config_override(app_config: AppConfig):
    settings = settings_from_config(app_config, struct_model="qwen3.5:9b")
    assert settings.struct_model == "qwen3.5:9b"
    assert settings.pipeline == app_config.pipeline


def test_native_only_fails_on_scanned(app_config: AppConfig, source_doc: SourceDocument):
    pipeline = NativeOnlyPipeline(settings_from_config(app_config), app_config)
    analysis = PdfAnalysis(
        path=source_doc.path,
        page_count=1,
        pages=[
            PageTextInfo(
                page_number=1,
                native_text="",
                char_count=0,
                readable_ratio=0.0,
                is_sufficient=False,
                needs_ocr=True,
            )
        ],
        is_mostly_scanned=True,
        total_native_chars=0,
    )
    with patch.object(pipeline, "_analyze", return_value=analysis):
        result = pipeline.extract(source_doc)
    assert result.success is False
    assert "scanned" in (result.error_message or "").lower()
