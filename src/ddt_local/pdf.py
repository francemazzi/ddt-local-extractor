"""PDF processing: native text extraction and page rendering."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import fitz

from ddt_local.config import AppConfig

DDT_KEYWORDS = re.compile(
    r"(DDT|documento\s+di\s+trasporto|partita\s+iva|p\.?\s*iva|colli|vettore|causale)",
    re.IGNORECASE,
)


@dataclass
class PageTextInfo:
    page_number: int
    native_text: str
    char_count: int
    readable_ratio: float
    is_sufficient: bool
    needs_ocr: bool


@dataclass
class PdfAnalysis:
    path: Path
    page_count: int
    pages: list[PageTextInfo] = field(default_factory=list)
    is_mostly_scanned: bool = False
    total_native_chars: int = 0

    @property
    def needs_visual_ocr(self) -> bool:
        return any(p.needs_ocr for p in self.pages)


@dataclass
class RenderedPage:
    page_number: int
    image_path: Path


def _readable_ratio(text: str) -> float:
    if not text:
        return 0.0
    readable = sum(1 for c in text if c.isalnum() or c.isspace() or c in ".,/-:;()")
    return readable / len(text)


def _page_has_sufficient_text(text: str, config: AppConfig) -> bool:
    stripped = text.strip()
    if len(stripped) < config.min_native_text_chars:
        return False
    if _readable_ratio(stripped) < 0.6:
        return False
    if not DDT_KEYWORDS.search(stripped):
        return False
    return True


def _page_image_ratio(page: fitz.Page) -> float:
    page_area = abs(page.rect.width * page.rect.height) or 1.0
    image_area = 0.0
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") == 1:
            x0, y0, x1, y1 = block.get("bbox", (0, 0, 0, 0))
            image_area += abs((x1 - x0) * (y1 - y0))
    return min(image_area / page_area, 1.0)


def analyze_pdf(path: Path, config: AppConfig) -> PdfAnalysis:
    """Analyze PDF pages for native text quality."""
    doc = fitz.open(path)
    try:
        pages: list[PageTextInfo] = []
        total_chars = 0
        scanned_pages = 0

        for idx in range(doc.page_count):
            page = doc.load_page(idx)
            text = page.get_text("text") or ""
            char_count = len(text.strip())
            ratio = _readable_ratio(text)
            image_ratio = _page_image_ratio(page)
            sufficient = _page_has_sufficient_text(text, config)
            needs_ocr = not sufficient or image_ratio > 0.7
            if needs_ocr:
                scanned_pages += 1
            total_chars += char_count
            pages.append(
                PageTextInfo(
                    page_number=idx + 1,
                    native_text=text,
                    char_count=char_count,
                    readable_ratio=ratio,
                    is_sufficient=sufficient,
                    needs_ocr=needs_ocr,
                )
            )

        mostly_scanned = scanned_pages > doc.page_count / 2
        return PdfAnalysis(
            path=path,
            page_count=doc.page_count,
            pages=pages,
            is_mostly_scanned=mostly_scanned,
            total_native_chars=total_chars,
        )
    finally:
        doc.close()


def render_page_png(
    path: Path,
    page_number: int,
    config: AppConfig,
    output_dir: Path | None = None,
) -> RenderedPage:
    """Render a PDF page to PNG at configured DPI."""
    doc = fitz.open(path)
    try:
        if page_number < 1 or page_number > doc.page_count:
            raise ValueError(f"Invalid page number {page_number} for {path.name}")

        page = doc.load_page(page_number - 1)
        zoom = config.render_dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        if output_dir is None:
            output_dir = Path(tempfile.mkdtemp(prefix="ddt_render_"))
        else:
            output_dir.mkdir(parents=True, exist_ok=True)

        out_path = output_dir / f"{path.stem}_p{page_number:03d}.png"
        pix.save(str(out_path))
        return RenderedPage(page_number=page_number, image_path=out_path)
    finally:
        doc.close()


def cleanup_render_dir(directory: Path) -> None:
    """Remove temporary rendered images."""
    if not directory.exists():
        return
    for item in directory.iterdir():
        if item.is_file():
            item.unlink(missing_ok=True)
    try:
        directory.rmdir()
    except OSError:
        pass
