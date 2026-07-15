"""Tests for ground truth adapter."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ddt_local.benchmark.ground_truth import (
    COLLECTION_FILENAME,
    convert_dataset_document,
    load_dataset_ground_truth,
    load_ground_truth_dir,
    load_ground_truth_file,
    parse_date,
    parse_packages,
    to_decimal,
)
from ddt_local.models import DocumentoDDT

DATASET_PATH = Path(__file__).resolve().parents[1] / "dataset" / "ground_truth_ddt.json"
EXAMPLES_GT = Path(__file__).resolve().parents[1] / "examples" / "ground_truth"


@pytest.fixture
def first_raw_document() -> dict:
    import json

    with DATASET_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload["documents"][0]


def test_parse_date_slash_format():
    assert parse_date("14/07/2026") == date(2026, 7, 14)


def test_parse_date_dash_format():
    assert parse_date("14-07-2026") == date(2026, 7, 14)


def test_parse_date_invalid_returns_none():
    assert parse_date("invalid") is None
    assert parse_date(None) is None


def test_to_decimal_variants():
    assert to_decimal(24) == Decimal("24")
    assert to_decimal(24.5) == Decimal("24.5")
    assert to_decimal("-1603.0") == Decimal("-1603.0")
    assert to_decimal("1,5") == Decimal("1.5")
    assert to_decimal("N/A") is None
    assert to_decimal(None) is None


def test_parse_packages_extracts_leading_number():
    assert parse_packages("3 pacchi reggiati") == Decimal("3")
    assert parse_packages("2 bancali + 1 fascio") == Decimal("2")
    assert parse_packages(5) == Decimal("5")


def test_convert_dataset_document_mapping(first_raw_document):
    doc = convert_dataset_document(first_raw_document)
    assert doc.source_filename == "01_DDT_Acciai_Nordest.pdf"
    assert doc.fornitore.ragione_sociale == "Acciai Nordest S.r.l."
    assert doc.fornitore.partita_iva == "IT00000010001"
    assert "Brendola" in (doc.fornitore.indirizzo or "")
    assert doc.destinatario.ragione_sociale == "Officine Trave Blu S.r.l."
    assert doc.documento.numero_ddt == "NE/2026/0714-018"
    assert doc.documento.data_ddt == date(2026, 7, 14)
    assert doc.documento.numero_colli == Decimal("3")
    assert doc.documento.peso_netto == Decimal("5368.0")
    assert len(doc.articoli) == 3


def test_negative_quantity_preserved(first_raw_document):
    doc = convert_dataset_document(first_raw_document)
    taglio = next(a for a in doc.articoli if a.codice == "TAGLIO-01")
    assert taglio.quantita == Decimal("-1603.0")


def test_load_dataset_excludes_collection():
    docs = load_dataset_ground_truth(DATASET_PATH)
    assert COLLECTION_FILENAME not in docs
    assert len(docs) == 10


def test_converted_document_validates_as_pydantic(first_raw_document):
    doc = convert_dataset_document(first_raw_document)
    roundtrip = DocumentoDDT.model_validate(doc.model_dump())
    assert roundtrip.source_filename == doc.source_filename


@pytest.mark.skipif(
    not EXAMPLES_GT.exists() or not any(EXAMPLES_GT.glob("*.json")),
    reason="examples/ground_truth not generated yet",
)
def test_load_ground_truth_dir():
    docs = load_ground_truth_dir(EXAMPLES_GT)
    assert len(docs) == 10
    assert all(isinstance(d, DocumentoDDT) for d in docs.values())


@pytest.mark.skipif(
    not (EXAMPLES_GT / "01_DDT_Acciai_Nordest.json").exists(),
    reason="examples/ground_truth not generated yet",
)
def test_load_single_ground_truth_file():
    path = EXAMPLES_GT / "01_DDT_Acciai_Nordest.json"
    doc = load_ground_truth_file(path)
    assert doc.source_filename == "01_DDT_Acciai_Nordest.pdf"
