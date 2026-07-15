"""High-level extraction entry point shared by production and benchmark."""

from __future__ import annotations

from ddt_local.config import AppConfig, PipelineSettings, settings_from_config
from ddt_local.models import ExtractionResult, SourceDocument
from ddt_local.pipelines import create_pipeline


def extract_document(
    document: SourceDocument,
    config: AppConfig,
    settings: PipelineSettings | None = None,
) -> ExtractionResult:
    """Run the configured extraction pipeline on a source document."""
    resolved = settings or settings_from_config(config)
    pipeline = create_pipeline(config, resolved)
    return pipeline.extract(document)
