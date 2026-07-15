"""ocr_struct pipeline: native text / GLM-OCR → structure model."""

from __future__ import annotations

import time

from ddt_local.models import (
    ExtractionArtifacts,
    ExtractionMethod,
    ExtractionResult,
    PhaseTiming,
    SourceDocument,
)
from ddt_local.pdf import cleanup_render_dir
from ddt_local.pipelines.base import BasePipeline


class OcrStructPipeline(BasePipeline):
    name = "ocr_struct"

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

            text_parts: list[str] = []
            ocr_pages: list[str] = []
            table_parts: list[str] = []
            used_ocr = False
            used_native = False

            pages_needing_ocr = [p.page_number for p in analysis.pages if p.needs_ocr]
            pages_with_native = [p for p in analysis.pages if not p.needs_ocr]

            for page in pages_with_native:
                used_native = True
                text_parts.append(f"--- Page {page.page_number} (native) ---\n{page.native_text}")

            if pages_needing_ocr:
                used_ocr = True
                start = time.perf_counter()
                images = self._render_pages(document, pages_needing_ocr, render_dir)
                phase_timings.append(
                    PhaseTiming(
                        phase="rendering",
                        duration_seconds=time.perf_counter() - start,
                    )
                )
                start = time.perf_counter()
                ocr_result = self._ocr.ocr_images(
                    images,
                    table_pass=self.settings.ocr_table_pass,
                )
                phase_timings.append(
                    PhaseTiming(
                        phase="ocr",
                        duration_seconds=time.perf_counter() - start,
                        model=self.settings.ocr_model,
                    )
                )
                ocr_pages = ocr_result.page_texts()
                text_parts.append(ocr_result.combined_text)
                if ocr_result.combined_tables:
                    table_parts.append(ocr_result.combined_tables)

            combined = "\n\n".join(t for t in text_parts if t).strip()
            artifacts.native_text = "\n\n".join(
                f"--- Page {p.page_number} ---\n{p.native_text}" for p in pages_with_native
            ) or None
            artifacts.ocr_text_by_page = ocr_pages
            artifacts.table_markdown = "\n\n".join(table_parts) or None

            if used_ocr and used_native:
                method = ExtractionMethod.MIXED
            elif used_ocr:
                method = ExtractionMethod.OCR
            else:
                method = ExtractionMethod.NATIVE_TEXT

            if not combined:
                return ExtractionResult(
                    document=None,
                    metadata=self._build_metadata(
                        page_count=analysis.page_count,
                        extraction_method=method,
                        phase_timings=phase_timings,
                        ocr_model=self.settings.ocr_model if used_ocr else None,
                    ),
                    artifacts=artifacts,
                    success=False,
                    error_message="No extractable text from document",
                )

            return self._structure_from_text(
                document=document,
                text=combined,
                table_markdown=artifacts.table_markdown,
                page_count=analysis.page_count,
                extraction_method=method,
                phase_timings=phase_timings,
                artifacts=artifacts,
                ocr_model=self.settings.ocr_model if used_ocr else None,
            )
        finally:
            cleanup_render_dir(render_dir)
