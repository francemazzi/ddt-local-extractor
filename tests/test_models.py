"""Tests for Pydantic models."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ddt_local.models import (
    DatiDocumento,
    DocumentoDDT,
    ExtractionResult,
    ExecutionMetadata,
    RigaDDT,
    Soggetto,
    documento_ddt_json_schema,
)


def test_documento_ddt_minimal_valid():
    doc = DocumentoDDT(source_filename="01_DDT.pdf")
    assert doc.source_filename == "01_DDT.pdf"
    assert doc.quality_score == 0.0
    assert doc.articoli == []


def test_documento_ddt_full_roundtrip():
    payload = {
        "source_filename": "01_DDT_Acciai_Nordest.pdf",
        "fornitore": {
            "ragione_sociale": "Acciai Nordest S.r.l.",
            "partita_iva": "IT00000010001",
            "indirizzo": "Via delle Colate 18, 36040 Brendola (VI)",
        },
        "destinatario": {
            "ragione_sociale": "Officine Trave Blu S.r.l.",
            "partita_iva": "IT00000020002",
        },
        "documento": {
            "numero_ddt": "NE/2026/0714-018",
            "data_ddt": "2026-07-14",
            "riferimento_ordine": "OC 781/2026",
            "causale_trasporto": "Vendita",
            "numero_colli": "3",
            "peso_netto": "5368.0",
            "peso_lordo": "5406.0",
            "vettore": "Trasporti Quercia S.r.l.",
            "destinazione": "Magazzino 2",
        },
        "articoli": [
            {
                "numero_riga": 1,
                "codice": "S355-10-2010",
                "descrizione": "Lamiera nera S355JR",
                "quantita": "24",
                "unita_misura": "FOGLI",
                "lotto": "COL-26A184",
            }
        ],
        "quality_score": 0.95,
        "campi_da_verificare": [],
        "warning": [],
    }
    doc = DocumentoDDT.model_validate(payload)
    assert doc.documento.data_ddt == date(2026, 7, 14)
    assert doc.documento.numero_colli == Decimal("3")
    assert doc.articoli[0].quantita == Decimal("24")


def test_decimal_not_float_for_quantities():
    riga = RigaDDT(quantita=Decimal("24.5"))
    assert isinstance(riga.quantita, Decimal)
    assert riga.quantita == Decimal("24.5")


def test_negative_quantity_allowed():
    riga = RigaDDT(codice="TAGLIO-01", quantita=Decimal("-1603.0"))
    assert riga.quantita == Decimal("-1603.0")


def test_json_schema_export_has_required_fields():
    schema = documento_ddt_json_schema()
    assert schema["title"] == "DocumentoDDT"
    assert "properties" in schema
    assert "source_filename" in schema["properties"]
    assert "articoli" in schema["properties"]


def test_json_parsing_from_string():
    raw = json.dumps(
        {
            "source_filename": "test.pdf",
            "fornitore": {},
            "destinatario": {},
            "documento": {},
            "articoli": [],
        }
    )
    doc = DocumentoDDT.model_validate_json(raw)
    assert doc.source_filename == "test.pdf"


def test_missing_source_filename_raises():
    with pytest.raises(ValidationError):
        DocumentoDDT.model_validate(
            {"fornitore": {}, "destinatario": {}, "documento": {}, "articoli": []}
        )


def test_extraction_result_structure():
    meta = ExecutionMetadata(pipeline="ocr_struct", page_count=2)
    result = ExtractionResult(metadata=meta, success=True)
    assert result.metadata.pipeline == "ocr_struct"
    assert result.document is None


def test_soggetto_strips_whitespace():
    s = Soggetto(ragione_sociale="  Test S.r.l.  ")
    assert s.ragione_sociale == "Test S.r.l."


def test_dati_documento_date_parsing():
    d = DatiDocumento(data_ddt="2026-07-14")
    assert d.data_ddt == date(2026, 7, 14)
