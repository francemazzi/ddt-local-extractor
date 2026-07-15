"""Pipeline protocol and factory."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ddt_local.config import AppConfig, PipelineSettings, settings_from_config
from ddt_local.models import ExtractionResult, PipelineName, SourceDocument
from ddt_local.pipelines.native_only import NativeOnlyPipeline
from ddt_local.pipelines.ocr_struct import OcrStructPipeline
from ddt_local.pipelines.vision_direct import VisionDirectPipeline


@runtime_checkable
class ExtractionPipeline(Protocol):
    """Common interface for interchangeable extraction strategies."""

    name: str

    def extract(self, document: SourceDocument) -> ExtractionResult: ...


def create_pipeline(
    config: AppConfig,
    settings: PipelineSettings | None = None,
) -> ExtractionPipeline:
    """Instantiate the configured extraction pipeline."""
    resolved = settings or settings_from_config(config)
    pipeline_name = resolved.pipeline.strip().lower()

    valid = {p.value for p in PipelineName}
    if pipeline_name not in valid:
        raise ValueError(
            f"Unknown pipeline '{resolved.pipeline}'. Valid options: {sorted(valid)}"
        )

    if pipeline_name == PipelineName.OCR_STRUCT.value:
        return OcrStructPipeline(resolved, config)
    if pipeline_name == PipelineName.VISION_DIRECT.value:
        return VisionDirectPipeline(resolved, config)
    return NativeOnlyPipeline(resolved, config)


def resolve_pipeline_name(name: str) -> PipelineName:
    """Resolve and validate a pipeline name string."""
    normalized = name.strip().lower()
    try:
        return PipelineName(normalized)
    except ValueError as exc:
        valid = [p.value for p in PipelineName]
        raise ValueError(f"Unknown pipeline '{name}'. Valid options: {valid}") from exc
