"""Deterministic quality score and requires_review flag."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ddt_local.models import DocumentoDDT

DEFAULT_REVIEW_THRESHOLD = 0.85


@dataclass(frozen=True)
class QualityPenalties:
    missing_numero_ddt: float = 0.25
    missing_data_ddt: float = 0.15
    missing_fornitore: float = 0.15
    missing_destinatario: float = 0.15
    no_articoli: float = 0.20
    missing_quantita: float = 0.08
    missing_unita_misura: float = 0.05
    ambiguous_field: float = 0.05
    parse_error: float = 0.30
    negative_quantita: float = 0.05
    invalid_date_flag: float = 0.10


@dataclass
class QualityResult:
    score: float
    flags: list[str] = field(default_factory=list)
    requires_review: bool = False


def compute_quality_score(
    doc: DocumentoDDT,
    *,
    penalties: QualityPenalties | None = None,
    has_parse_error: bool = False,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> QualityResult:
    """Compute quality_score from 1.0 with configurable penalties."""
    penalties = penalties or QualityPenalties()
    score = 1.0
    flags: list[str] = []

    if has_parse_error:
        score -= penalties.parse_error
        flags.append("parse_error")

    if not doc.documento.numero_ddt:
        score -= penalties.missing_numero_ddt
        flags.append("missing_numero_ddt")

    if not doc.documento.data_ddt:
        score -= penalties.missing_data_ddt
        flags.append("missing_data_ddt")

    if not doc.fornitore.ragione_sociale:
        score -= penalties.missing_fornitore
        flags.append("missing_fornitore")

    if not doc.destinatario.ragione_sociale:
        score -= penalties.missing_destinatario
        flags.append("missing_destinatario")

    if not doc.articoli:
        score -= penalties.no_articoli
        flags.append("no_articoli")
    else:
        for idx, riga in enumerate(doc.articoli):
            if riga.quantita is None:
                score -= penalties.missing_quantita
                flags.append(f"missing_quantita_riga_{idx + 1}")
            elif riga.quantita < Decimal("0"):
                # Negative quantities are allowed (e.g. weight adjustments)
                # but flagged for review without heavy penalty
                score -= penalties.negative_quantita
                flags.append(f"negative_quantita_riga_{idx + 1}")
            if not riga.unita_misura:
                score -= penalties.missing_unita_misura
                flags.append(f"missing_um_riga_{idx + 1}")

    for field_name in doc.campi_da_verificare:
        score -= penalties.ambiguous_field
        flags.append(f"ambiguous:{field_name}")

    score = max(0.0, min(1.0, score))
    review = requires_review(score, doc, flags, threshold=review_threshold)
    return QualityResult(score=score, flags=flags, requires_review=review)


def requires_review(
    score: float,
    doc: DocumentoDDT,
    flags: list[str],
    *,
    threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> bool:
    if score < threshold:
        return True
    if not doc.documento.numero_ddt:
        return True
    if any(r.quantita is None for r in doc.articoli):
        return True
    if doc.campi_da_verificare:
        return True
    if any(f.startswith("parse_error") or "critical" in f for f in flags):
        return True
    return False


def apply_quality(doc: DocumentoDDT, *, has_parse_error: bool = False) -> QualityResult:
    """Update document quality_score and campi_da_verificare in-place."""
    result = compute_quality_score(doc, has_parse_error=has_parse_error)
    doc.quality_score = result.score
    merged = list(dict.fromkeys([*doc.campi_da_verificare, *result.flags]))
    doc.campi_da_verificare = merged
    return result
