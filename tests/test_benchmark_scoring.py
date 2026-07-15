"""Tests for benchmark scoring."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ddt_local.benchmark.scoring import (
    align_lines,
    normalize_decimal,
    normalize_string,
    score_prediction,
    values_equal,
)
from ddt_local.models import DatiDocumento, DocumentoDDT, RigaDDT, Soggetto


def _doc(filename: str = "t.pdf", **kwargs) -> DocumentoDDT:
    defaults = dict(
        source_filename=filename,
        fornitore=Soggetto(ragione_sociale="Fornitore SpA", partita_iva="IT1"),
        destinatario=Soggetto(ragione_sociale="Cliente SpA"),
        documento=DatiDocumento(
            numero_ddt="N1",
            data_ddt=date(2026, 7, 14),
            numero_colli=Decimal("3"),
        ),
        articoli=[
            RigaDDT(
                codice="S355-10-2010",
                descrizione="Lamiera nera",
                quantita=Decimal("24"),
                unita_misura="FOGLI",
            ),
            RigaDDT(
                codice="TAGLIO-01",
                descrizione="Rettifica",
                quantita=Decimal("-1603.0"),
                unita_misura="KG",
            ),
        ],
    )
    defaults.update(kwargs)
    return DocumentoDDT(**defaults)


def test_normalize_string_casefold():
    assert normalize_string("  AbC  ") == "abc"


def test_normalize_decimal_formats():
    assert normalize_decimal("24") == Decimal("24")
    assert normalize_decimal("24.0") == Decimal("24.0")
    assert normalize_decimal("24,0") == Decimal("24.0")
    assert normalize_decimal("-1603.0") == Decimal("-1603.0")


def test_values_equal_qty_formats():
    assert values_equal(Decimal("24"), "24.0", path="articoli.quantita")


def test_perfect_match_score():
    gt = _doc()
    pred = _doc()
    result = score_prediction(gt, pred)
    assert result.lines_found == 2
    assert result.lines_missing == 0
    assert result.lines_invented == 0
    assert result.weighted_score == 1.0
    assert result.header_accuracy == 1.0


def test_missing_line():
    gt = _doc()
    pred = _doc(articoli=[gt.articoli[0]])
    result = score_prediction(gt, pred)
    assert result.lines_found == 1
    assert result.lines_missing == 1
    assert result.weighted_score < 1.0


def test_invented_line():
    gt = _doc(articoli=[_doc().articoli[0]])
    pred = _doc()
    result = score_prediction(gt, pred)
    assert result.lines_invented == 1


def test_wrong_quantity():
    gt = _doc()
    pred_art = [
        RigaDDT(codice="S355-10-2010", descrizione="Lamiera nera", quantita=Decimal("99"), unita_misura="FOGLI"),
        gt.articoli[1],
    ]
    pred = _doc(articoli=pred_art)
    result = score_prediction(gt, pred)
    assert result.wrong_quantities == 1


def test_align_fallback_description():
    gt = [RigaDDT(codice="X", descrizione="Lamiera speciale XYZ", quantita=Decimal("1"))]
    pred = [RigaDDT(codice="Y", descrizione="Lamiera speciale XYZ", quantita=Decimal("2"))]
    matched, missing, invented = align_lines(gt, pred)
    assert len(matched) == 1
    assert not missing
    assert not invented


def test_null_correct_and_false_positive():
    gt = _doc(documento=DatiDocumento(numero_ddt="N1", data_ddt=None, vettore=None))
    pred = _doc(
        documento=DatiDocumento(numero_ddt="N1", data_ddt=None, vettore="Inventato")
    )
    result = score_prediction(gt, pred)
    assert result.field_metrics["documento.data_ddt"]["null_correct"] is True
    assert result.field_metrics["documento.vettore"]["false_positive"] is True


def test_none_prediction_low_score():
    gt = _doc()
    result = score_prediction(gt, None)
    assert result.weighted_score < 0.5
    assert result.lines_missing == 2
