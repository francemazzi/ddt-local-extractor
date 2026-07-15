"""vision_direct pipeline: page images → vision model → JSON in one pass."""

from __future__ import annotations

import base64
import time

from ddt_local.models import (
    ExtractionArtifacts,
    ExtractionMethod,
    ExtractionResult,
    PhaseTiming,
    SourceDocument,
    ollama_documento_schema,
)
from ddt_local.pdf import cleanup_render_dir
from ddt_local.pipelines.base import BasePipeline
from ddt_local.quality import apply_quality
from ddt_local.validation import STRUCTURE_SYSTEM_PROMPT, parse_and_validate


class VisionDirectPipeline(BasePipeline):
    name = "vision_direct"

    def extract(self, document: SourceDocument) -> ExtractionResult:
        phase_timings: list[PhaseTiming] = []
        artifacts = ExtractionArtifacts()
        render_dir = self._temp_render_dir()

        try:
            start = time.perf_counter()
            analysis = self._analyze(document)
            phase_timings.append(
                PhaseTiming(phase="pdf_analysis", duration_seconds=time.perf_counter() - start)
            )

            page_numbers = list(range(1, analysis.page_count + 1))
            start = time.perf_counter()
            images = self._render_pages(document, page_numbers, render_dir)
            phase_timings.append(
                PhaseTiming(phase="rendering", duration_seconds=time.perf_counter() - start)
            )

            images_b64 = [
                base64.b64encode(path.read_bytes()).decode("ascii") for _, path in images
            ]
            prompt = (
                f"source_filename: {document.filename}\n"
                f"page_count: {analysis.page_count}\n"
                "Extract structured DDT data from the document page images."
            )
            schema = ollama_documento_schema()

            start = time.perf_counter()

            def _call(prompt_text: str) -> str:
                result = self._client.generate_text(
                    model=self.settings.vision_model,
                    prompt=prompt_text,
                    system=STRUCTURE_SYSTEM_PROMPT,
                    json_schema=schema,
                    images=images_b64,
                    keep_alive="10m",
                )
                return result.text

            raw = _call(prompt)
            artifacts.raw_json_response = raw
            phase_timings.append(
                PhaseTiming(
                    phase="vision",
                    duration_seconds=time.perf_counter() - start,
                    model=self.settings.vision_model,
                )
            )

            def repair_fn(repair_prompt: str) -> str:
                return _call(repair_prompt)

            doc, error, retries = parse_and_validate(
                raw,
                document.filename,
                repair_fn=repair_fn,
            )

            if doc is None:
                return ExtractionResult(
                    document=None,
                    metadata=self._build_metadata(
                        page_count=analysis.page_count,
                        extraction_method=ExtractionMethod.VISION,
                        phase_timings=phase_timings,
                        retries=retries,
                        vision_model=self.settings.vision_model,
                    ),
                    artifacts=artifacts,
                    success=False,
                    error_message=error or "Vision validation failed",
                )

            apply_quality(doc)
            return ExtractionResult(
                document=doc,
                metadata=self._build_metadata(
                    page_count=analysis.page_count,
                    extraction_method=ExtractionMethod.VISION,
                    phase_timings=phase_timings,
                    retries=retries,
                    vision_model=self.settings.vision_model,
                ),
                artifacts=artifacts,
                success=True,
            )
        finally:
            cleanup_render_dir(render_dir)
