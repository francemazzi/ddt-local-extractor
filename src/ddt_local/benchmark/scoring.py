"""Benchmark scoring: field accuracy, line alignment, weighted score."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ddt_local.models import DocumentoDDT, RigaDDT

# Weights from specification (configurable)
DEFAULT_WEIGHTS: dict[str, float] = {
    "formatting": 0.1,
    "incomplete_name": 0.3,
    "wrong_date": 0.7,
    "wrong_code": 0.7,
    "wrong_quantity": 0.9,
    "missing_line": 0.9,
    "invented_line": 1.0,
}

HEADER_FIELDS = [
    ("documento.numero_ddt", "documento", "numero_ddt"),
    ("documento.data_ddt", "documento", "data_ddt"),
    ("documento.riferimento_ordine", "documento", "riferimento_ordine"),
    ("documento.causale_trasporto", "documento", "causale_trasporto"),
    ("documento.numero_colli", "documento", "numero_colli"),
    ("documento.peso_lordo", "documento", "peso_lordo"),
    ("documento.peso_netto", "documento", "peso_netto"),
    ("documento.vettore", "documento", "vettore"),
    ("documento.destinazione", "documento", "destinazione"),
    ("fornitore.ragione_sociale", "fornitore", "ragione_sociale"),
    ("fornitore.partita_iva", "fornitore", "partita_iva"),
    ("fornitore.indirizzo", "fornitore", "indirizzo"),
    ("destinatario.ragione_sociale", "destinatario", "ragione_sociale"),
    ("destinatario.partita_iva", "destinatario", "partita_iva"),
    ("destinatario.indirizzo", "destinatario", "indirizzo"),
]

CASE_SENSITIVE_FIELDS = {"fornitore.partita_iva", "destinatario.partita_iva"}


@dataclass
class FieldMetric:
    path: str
    match: bool
    expected: Any
    predicted: Any
    null_correct: bool = False
    false_positive: bool = False


@dataclass
class ErrorDetail:
    document: str
    field: str
    expected: Any
    predicted: Any
    error_type: str
    weight: float


@dataclass
class ScoreResult:
    field_metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    lines_found: int = 0
    lines_missing: int = 0
    lines_invented: int = 0
    wrong_quantities: int = 0
    wrong_codes: int = 0
    weighted_score: float = 0.0
    total_penalty: float = 0.0
    max_penalty: float = 0.0
    error_details: list[ErrorDetail] = field(default_factory=list)
    header_accuracy: float = 0.0


def normalize_string(value: str | None, *, casefold: bool = True) -> str | None:
    if value is None:
        return None
    text = " ".join(value.strip().split())
    if not text:
        return None
    return text.casefold() if casefold else text


def normalize_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip().replace(",", ".")
        if not cleaned or cleaned in {"-", "N/A", "n/a"}:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def normalize_description(value: str | None) -> str | None:
    if value is None:
        return None
    text = normalize_string(value, casefold=True)
    if text is None:
        return None
    return re.sub(r"\s+", " ", text)


def values_equal(expected: Any, predicted: Any, *, path: str) -> bool:
    if expected is None and predicted is None:
        return True
    if expected is None or predicted is None:
        return False

    if isinstance(expected, date) or isinstance(predicted, date):
        exp = expected if isinstance(expected, date) else date.fromisoformat(str(expected))
        pred = predicted if isinstance(predicted, date) else date.fromisoformat(str(predicted))
        return exp == pred

    if isinstance(expected, Decimal) or isinstance(predicted, Decimal) or path.endswith(
        ("quantita", "numero_colli", "peso_lordo", "peso_netto")
    ):
        return normalize_decimal(expected) == normalize_decimal(predicted)

    casefold = path not in CASE_SENSITIVE_FIELDS
    return normalize_string(str(expected), casefold=casefold) == normalize_string(
        str(predicted), casefold=casefold
    )


def _get_nested(doc: DocumentoDDT, section: str, attr: str) -> Any:
    obj = getattr(doc, section)
    return getattr(obj, attr)


def _line_key_code_qty(riga: RigaDDT) -> tuple[str | None, Decimal | None]:
    code = normalize_string(riga.codice, casefold=True)
    qty = normalize_decimal(riga.quantita)
    return code, qty


def align_lines(
    gt_lines: list[RigaDDT],
    pred_lines: list[RigaDDT],
) -> tuple[list[tuple[RigaDDT, RigaDDT]], list[RigaDDT], list[RigaDDT]]:
    """
    Align article lines.

    Algorithm:
    1. Primary match: normalized codice + Decimal quantita
    2. Fallback: normalized descrizione
    3. Greedy one-to-one; unmatched GT → missing, unmatched pred → invented
    """
    matched: list[tuple[RigaDDT, RigaDDT]] = []
    gt_remaining = list(gt_lines)
    pred_remaining = list(pred_lines)

    # Pass 1: codice + quantita
    still_gt: list[RigaDDT] = []
    for gt in gt_remaining:
        gkey = _line_key_code_qty(gt)
        found = None
        for pred in pred_remaining:
            if gkey[0] and gkey[1] is not None and _line_key_code_qty(pred) == gkey:
                found = pred
                break
        if found is not None:
            matched.append((gt, found))
            pred_remaining.remove(found)
        else:
            still_gt.append(gt)
    gt_remaining = still_gt

    # Pass 2: description fallback
    still_gt = []
    for gt in gt_remaining:
        gdesc = normalize_description(gt.descrizione)
        found = None
        if gdesc:
            for pred in pred_remaining:
                if normalize_description(pred.descrizione) == gdesc:
                    found = pred
                    break
        if found is not None:
            matched.append((gt, found))
            pred_remaining.remove(found)
        else:
            still_gt.append(gt)

    return matched, still_gt, pred_remaining


def score_prediction(
    ground_truth: DocumentoDDT,
    prediction: DocumentoDDT | None,
    *,
    weights: dict[str, float] | None = None,
) -> ScoreResult:
    """Compare prediction against ground truth and compute weighted score."""
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    result = ScoreResult()
    penalty = 0.0
    max_penalty = 0.0

    if prediction is None:
        # Full failure: all lines missing + all headers wrong
        for path, _, _ in HEADER_FIELDS:
            result.field_metrics[path] = {
                "match": False,
                "expected": None,
                "predicted": None,
            }
            penalty += weights["formatting"]
            max_penalty += weights["formatting"]
            result.error_details.append(
                ErrorDetail(
                    document=ground_truth.source_filename,
                    field=path,
                    expected="(present)",
                    predicted=None,
                    error_type="missing_extraction",
                    weight=weights["formatting"],
                )
            )
        result.lines_missing = len(ground_truth.articoli)
        for _ in ground_truth.articoli:
            penalty += weights["missing_line"]
            max_penalty += weights["missing_line"]
        max_penalty = max(max_penalty, 1.0)
        result.total_penalty = penalty
        result.max_penalty = max_penalty
        result.weighted_score = max(0.0, 1.0 - penalty / max_penalty)
        return result

    # Header fields
    matches = 0
    for path, section, attr in HEADER_FIELDS:
        expected = _get_nested(ground_truth, section, attr)
        predicted = _get_nested(prediction, section, attr)
        max_penalty += weights["formatting"]

        null_correct = expected is None and predicted is None
        false_positive = expected is None and predicted is not None
        match = values_equal(expected, predicted, path=path)

        result.field_metrics[path] = {
            "match": match,
            "expected": str(expected) if expected is not None else None,
            "predicted": str(predicted) if predicted is not None else None,
            "null_correct": null_correct,
            "false_positive": false_positive,
        }

        if match:
            matches += 1
            continue

        error_type = "formatting"
        weight = weights["formatting"]
        if path.endswith("data_ddt"):
            error_type = "wrong_date"
            weight = weights["wrong_date"]
        elif "ragione_sociale" in path and expected and predicted:
            # Partial name difference → incomplete_name if one contains the other
            exp_s = normalize_string(str(expected)) or ""
            pred_s = normalize_string(str(predicted)) or ""
            if exp_s in pred_s or pred_s in exp_s:
                error_type = "incomplete_name"
                weight = weights["incomplete_name"]

        if false_positive:
            error_type = "false_positive"

        penalty += weight
        result.error_details.append(
            ErrorDetail(
                document=ground_truth.source_filename,
                field=path,
                expected=expected,
                predicted=predicted,
                error_type=error_type,
                weight=weight,
            )
        )

    result.header_accuracy = matches / len(HEADER_FIELDS) if HEADER_FIELDS else 1.0

    # Line alignment
    matched, missing, invented = align_lines(ground_truth.articoli, prediction.articoli)
    result.lines_found = len(matched)
    result.lines_missing = len(missing)
    result.lines_invented = len(invented)

    for gt, pred in matched:
        max_penalty += weights["wrong_code"] + weights["wrong_quantity"]
        g_code = normalize_string(gt.codice)
        p_code = normalize_string(pred.codice)
        if g_code != p_code:
            result.wrong_codes += 1
            penalty += weights["wrong_code"]
            result.error_details.append(
                ErrorDetail(
                    document=ground_truth.source_filename,
                    field="articoli.codice",
                    expected=gt.codice,
                    predicted=pred.codice,
                    error_type="wrong_code",
                    weight=weights["wrong_code"],
                )
            )
        g_qty = normalize_decimal(gt.quantita)
        p_qty = normalize_decimal(pred.quantita)
        if g_qty != p_qty:
            result.wrong_quantities += 1
            penalty += weights["wrong_quantity"]
            result.error_details.append(
                ErrorDetail(
                    document=ground_truth.source_filename,
                    field="articoli.quantita",
                    expected=str(gt.quantita),
                    predicted=str(pred.quantita),
                    error_type="wrong_quantity",
                    weight=weights["wrong_quantity"],
                )
            )

    for gt in missing:
        max_penalty += weights["missing_line"]
        penalty += weights["missing_line"]
        result.error_details.append(
            ErrorDetail(
                document=ground_truth.source_filename,
                field="articoli",
                expected=gt.codice or gt.descrizione,
                predicted=None,
                error_type="missing_line",
                weight=weights["missing_line"],
            )
        )

    for pred in invented:
        max_penalty += weights["invented_line"]
        penalty += weights["invented_line"]
        result.error_details.append(
            ErrorDetail(
                document=ground_truth.source_filename,
                field="articoli",
                expected=None,
                predicted=pred.codice or pred.descrizione,
                error_type="invented_line",
                weight=weights["invented_line"],
            )
        )

    max_penalty = max(max_penalty, 1.0)
    result.total_penalty = penalty
    result.max_penalty = max_penalty
    result.weighted_score = max(0.0, 1.0 - penalty / max_penalty)
    return result
