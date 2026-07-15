"""Pipeline protocol and factory."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ddt_local.config import AppConfig
from ddt_local.models import ExtractionResult, PipelineName, SourceDocument


@runtime_checkable
class ExtractionPipeline(Protocol):
    """Common interface for interchangeable extraction strategies."""

    name: str

    def extract(self, document: SourceDocument) -> ExtractionResult: ...


class PipelineNotImplementedError(NotImplementedError):
    """Raised when a pipeline class is registered but not yet implemented."""


class _StubPipeline:
    """Placeholder pipeline used until concrete implementations exist."""

    def __init__(self, name: str, config: AppConfig) -> None:
        self.name = name
        self._config = config

    def extract(self, document: SourceDocument) -> ExtractionResult:
        raise PipelineNotImplementedError(
            f"Pipeline '{self.name}' is not yet implemented. "
            f"Document: {document.filename}"
        )


def create_pipeline(config: AppConfig) -> ExtractionPipeline:
    """Instantiate the configured extraction pipeline."""
    pipeline_name = config.pipeline.strip().lower()

    valid = {p.value for p in PipelineName}
    if pipeline_name not in valid:
        raise ValueError(
            f"Unknown pipeline '{config.pipeline}'. Valid options: {sorted(valid)}"
        )

    return _StubPipeline(name=pipeline_name, config=config)


def resolve_pipeline_name(name: str) -> PipelineName:
    """Resolve and validate a pipeline name string."""
    normalized = name.strip().lower()
    try:
        return PipelineName(normalized)
    except ValueError as exc:
        valid = [p.value for p in PipelineName]
        raise ValueError(f"Unknown pipeline '{name}'. Valid options: {valid}") from exc
