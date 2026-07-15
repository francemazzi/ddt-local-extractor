"""Tests for quality score."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ddt_local.models import DatiDocumento, DocumentoDDT, RigaDDT, Soggetto
from ddt_local.quality import apply_quality, compute_quality_score, requires_review


def _base_doc(**kwargs) -> DocumentoDDT:
    defaults = dict(
        source_filename="t.pdf",
        fornitore=Soggetto(ragione_sociale="Fornitore SpA"),
        destinatario=Soggetto(ragione_sociale="Cliente SpA"),
        documento=DatiDocumento(numero_ddt="N1", data_ddt=date(2026, 7, 14)),
        articoli=[
            RigaDDT(codice="A", quantita=Decimal("1"), unita_misura="PZ"),
        ],
    )
    defaults.update(kwargs)
    return DocumentoDDT(**defaults)


def test_perfect_document_high_score():
    result = compute_quality_score(_base_doc())
    assert result.score >= 0.85
    assert result.requires_review is False


def test_missing_numero_ddt_penalized():
    doc = _base_doc(documento=DatiDocumento(data_ddt=date(2026, 7, 14)))
    result = compute_quality_score(doc)
    assert result.score < 1.0
    assert "missing_numero_ddt" in result.flags
    assert result.requires_review is True


def test_no_articoli_penalized():
    doc = _base_doc(articoli=[])
    result = compute_quality_score(doc)
    assert "no_articoli" in result.flags
    assert result.score < 1.0


def test_missing_quantita_requires_review():
    doc = _base_doc(articoli=[RigaDDT(codice="A", unita_misura="PZ")])
    result = compute_quality_score(doc)
    assert result.requires_review is True
    assert any("missing_quantita" in f for f in result.flags)


def test_negative_quantity_flagged_but_allowed():
    doc = _base_doc(
        articoli=[
            RigaDDT(codice="TAGLIO-01", quantita=Decimal("-1603"), unita_misura="KG"),
        ]
    )
    result = compute_quality_score(doc)
    assert any("negative_quantita" in f for f in result.flags)
    assert result.score > 0.5


def test_apply_quality_updates_document():
    doc = _base_doc(documento=DatiDocumento())
    result = apply_quality(doc)
    assert doc.quality_score == result.score
    assert "missing_numero_ddt" in doc.campi_da_verificare


def test_requires_review_threshold():
    doc = _base_doc()
    assert requires_review(0.84, doc, []) is True
    assert requires_review(0.95, doc, []) is False
