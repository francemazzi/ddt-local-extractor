"""GLM-OCR pipeline via Ollama /api/generate."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from ddt_local.config import AppConfig
from ddt_local.ollama import OllamaClient

logger = logging.getLogger(__name__)

OCR_PROMPT = (
    "Recognize all visible text in this document image. "
    "Preserve line breaks and table structure. "
    "Do not invent or normalize data. Output plain text only."
)
TABLE_OCR_PROMPT = (
    "Extract only the tabular data from this document image as Markdown tables. "
    "Do not invent values. Use empty cells when unclear."
)


@dataclass
class OcrPageResult:
    page_number: int
    text: str
    table_markdown: str | None = None
    duration_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class OcrResult:
    pages: list[OcrPageResult] = field(default_factory=list)
    combined_text: str = ""
    combined_tables: str = ""
    total_duration_seconds: float = 0.0

    def page_texts(self) -> list[str]:
        return [p.text for p in self.pages]


class OcrEngine:
    def __init__(self, config: AppConfig, client: OllamaClient | None = None) -> None:
        self._config = config
        self._client = client or OllamaClient(config)

    def ocr_image(
        self,
        image_path: Path,
        *,
        page_number: int = 1,
        table_pass: bool = False,
    ) -> OcrPageResult:
        start = time.perf_counter()
        warnings: list[str] = []

        result = self._client.generate_from_image(
            model=self._config.ocr_model,
            prompt=OCR_PROMPT,
            image_path=image_path,
        )
        text = result.text.strip()
        if not text:
            warnings.append("empty_ocr_response")

        table_md: str | None = None
        if table_pass:
            try:
                table_result = self._client.generate_from_image(
                    model=self._config.ocr_model,
                    prompt=TABLE_OCR_PROMPT,
                    image_path=image_path,
                )
                table_md = table_result.text.strip() or None
            except Exception as exc:
                warnings.append(f"table_pass_failed:{type(exc).__name__}")
                logger.warning("Table OCR pass failed for page %s", page_number)

        duration = time.perf_counter() - start
        return OcrPageResult(
            page_number=page_number,
            text=text,
            table_markdown=table_md,
            duration_seconds=duration,
            warnings=warnings,
        )

    def ocr_images(
        self,
        images: list[tuple[int, Path]],
        *,
        table_pass: bool = False,
    ) -> OcrResult:
        pages: list[OcrPageResult] = []
        total_duration = 0.0

        for page_number, image_path in images:
            page_result = self.ocr_image(
                image_path,
                page_number=page_number,
                table_pass=table_pass,
            )
            pages.append(page_result)
            total_duration += page_result.duration_seconds

        combined_parts = []
        table_parts = []
        for page in pages:
            combined_parts.append(f"--- Page {page.page_number} ---\n{page.text}")
            if page.table_markdown:
                table_parts.append(
                    f"--- Tables Page {page.page_number} ---\n{page.table_markdown}"
                )

        return OcrResult(
            pages=pages,
            combined_text="\n\n".join(combined_parts).strip(),
            combined_tables="\n\n".join(table_parts).strip(),
            total_duration_seconds=total_duration,
        )
