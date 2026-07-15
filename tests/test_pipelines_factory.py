"""Tests for pipeline factory and name resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from ddt_local.config import AppConfig
from ddt_local.models import PipelineName, SourceDocument
from ddt_local.pipelines import (
    ExtractionPipeline,
    PipelineNotImplementedError,
    create_pipeline,
    resolve_pipeline_name,
)


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
    "pipeline",
    ["ocr_struct", "vision_direct", "native_only"],
)
def test_create_pipeline_returns_protocol_instance(
    app_config: AppConfig, pipeline: str, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DDT_PIPELINE", pipeline)
    from ddt_local.config import load_config

    config = load_config()
    instance = create_pipeline(config)
    assert isinstance(instance, ExtractionPipeline)
    assert instance.name == pipeline


def test_create_pipeline_unknown_raises(app_config: AppConfig, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DDT_PIPELINE", "invalid_pipeline")
    from ddt_local.config import load_config

    config = load_config()
    with pytest.raises(ValueError, match="Unknown pipeline"):
        create_pipeline(config)


def test_stub_pipeline_raises_not_implemented(source_doc: SourceDocument, app_config: AppConfig):
    pipeline = create_pipeline(app_config)
    with pytest.raises(PipelineNotImplementedError, match="not yet implemented"):
        pipeline.extract(source_doc)


def test_pipeline_name_enum_covers_all_strategies():
    values = {p.value for p in PipelineName}
    assert values == {"ocr_struct", "vision_direct", "native_only"}
