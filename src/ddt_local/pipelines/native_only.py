"""native_only pipeline: native PDF text → structure model; fail on scans."""

from __future__ import annotations

import time

from ddt_local.models import (
    ExtractionArtifacts,
    ExtractionMethod,
    ExtractionResult,
    PhaseTiming,
    SourceDocument,
)
from ddt_local.pipelines.base import BasePipeline


class NativeOnlyPipeline(BasePipeline):
    name = "native_only"

    def extract(self, document: SourceDocument) -> ExtractionResult:
        phase_timings: list[PhaseTiming] = []
        artifacts = ExtractionArtifacts()

        start = time.perf_counter()
        analysis = self._analyze(document)
        phase_timings.append(
            PhaseTiming(phase="pdf_analysis", duration_seconds=time.perf_counter() - start)
        )

        if analysis.is_mostly_scanned or analysis.needs_visual_ocr:
            return ExtractionResult(
                document=None,
                metadata=self._build_metadata(
                    page_count=analysis.page_count,
                    extraction_method=ExtractionMethod.NATIVE_TEXT,
                    phase_timings=phase_timings,
                ),
                artifacts=artifacts,
                success=False,
                error_message=(
                    "native_only pipeline cannot process scanned documents; "
                    "use ocr_struct or vision_direct"
                ),
            )

        text_parts = [
            f"--- Page {p.page_number} ---\n{p.native_text}" for p in analysis.pages
        ]
        combined = "\n\n".join(text_parts).strip()
        artifacts.native_text = combined

        if not combined:
            return ExtractionResult(
                document=None,
                metadata=self._build_metadata(
                    page_count=analysis.page_count,
                    extraction_method=ExtractionMethod.NATIVE_TEXT,
                    phase_timings=phase_timings,
                ),
                artifacts=artifacts,
                success=False,
                error_message="No native text found in PDF",
            )

        return self._structure_from_text(
            document=document,
            text=combined,
            table_markdown=None,
            page_count=analysis.page_count,
            extraction_method=ExtractionMethod.NATIVE_TEXT,
            phase_timings=phase_timings,
            artifacts=artifacts,
        )
