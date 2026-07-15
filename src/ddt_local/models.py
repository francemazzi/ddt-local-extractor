"""Pydantic data models for DDT extraction."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Soggetto(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    ragione_sociale: str | None = None
    partita_iva: str | None = None
    codice_fiscale: str | None = None
    indirizzo: str | None = None


class RigaDDT(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    numero_riga: int | None = None
    codice: str | None = None
    descrizione: str | None = None
    quantita: Decimal | None = None
    unita_misura: str | None = None
    lotto: str | None = None
    matricola: str | None = None


class DatiDocumento(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    numero_ddt: str | None = None
    data_ddt: date | None = None
    riferimento_ordine: str | None = None
    causale_trasporto: str | None = None
    numero_colli: Decimal | None = None
    peso_lordo: Decimal | None = None
    peso_netto: Decimal | None = None
    vettore: str | None = None
    destinazione: str | None = None


class DocumentoDDT(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_filename: str
    fornitore: Soggetto = Field(default_factory=Soggetto)
    destinatario: Soggetto = Field(default_factory=Soggetto)
    documento: DatiDocumento = Field(default_factory=DatiDocumento)
    articoli: list[RigaDDT] = Field(default_factory=list)
    quality_score: float = 0.0
    campi_da_verificare: list[str] = Field(default_factory=list)
    warning: list[str] = Field(default_factory=list)


class ExtractionMethod(StrEnum):
    NATIVE_TEXT = "native_text"
    OCR = "ocr"
    VISION = "vision"
    MIXED = "mixed"


class PipelineName(StrEnum):
    OCR_STRUCT = "ocr_struct"
    VISION_DIRECT = "vision_direct"
    NATIVE_ONLY = "native_only"


class PhaseTiming(BaseModel):
    phase: str
    duration_seconds: float = 0.0
    model: str | None = None


class ExecutionMetadata(BaseModel):
    pipeline: str
    ocr_model: str | None = None
    struct_model: str | None = None
    vision_model: str | None = None
    page_count: int = 0
    extraction_method: ExtractionMethod = ExtractionMethod.NATIVE_TEXT
    retries: int = 0
    peak_memory_bytes: int | None = None
    ollama_model_memory_bytes: int | None = None
    phase_timings: list[PhaseTiming] = Field(default_factory=list)
    total_duration_seconds: float = 0.0


class ExtractionArtifacts(BaseModel):
    native_text: str | None = None
    ocr_text_by_page: list[str] = Field(default_factory=list)
    table_markdown: str | None = None
    raw_json_response: str | None = None


class ExtractionResult(BaseModel):
    document: DocumentoDDT | None = None
    metadata: ExecutionMetadata
    artifacts: ExtractionArtifacts = Field(default_factory=ExtractionArtifacts)
    success: bool = False
    error_message: str | None = None


class SourceDocument(BaseModel):
    """Input document reference for pipeline extraction."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    filename: str
    sha256: str
    size_bytes: int
    page_count: int = 0


def documento_ddt_json_schema() -> dict[str, Any]:
    """Return JSON Schema for structured Ollama output."""
    return DocumentoDDT.model_json_schema()
