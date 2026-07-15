"""JSON parsing and Pydantic validation with one controlled repair retry."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from pydantic import ValidationError

from ddt_local.models import DocumentoDDT, ollama_documento_schema


STRUCTURE_SYSTEM_PROMPT = """Sei un sistema di estrazione dati specializzato in Documenti di Trasporto
italiani.

Estrai esclusivamente informazioni presenti nel testo ricevuto.

Non inventare dati.
Usa null quando un valore è assente o ambiguo.
Mantieni separate tutte le righe articolo.
Non confondere numero DDT, numero ordine, quantità, peso e numero colli.
Normalizza le date soltanto quando sono certe.
Conserva l'unità di misura originale.
Segnala ogni ambiguità in campi_da_verificare.
Non produrre testo fuori dal JSON."""

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def extract_json_payload(raw: str) -> str:
    """Extract a JSON object string from a model response without destructive edits."""
    text = raw.strip()
    if not text:
        raise ValueError("Empty response")

    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()

    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]

    raise ValueError("No JSON object found in response")


def validate_documento(
    payload: dict[str, Any] | str,
    source_filename: str,
) -> DocumentoDDT:
    """Validate payload as DocumentoDDT, enforcing source_filename."""
    if isinstance(payload, str):
        data = json.loads(payload)
    else:
        data = dict(payload)

    if not data.get("source_filename"):
        data["source_filename"] = source_filename

    return DocumentoDDT.model_validate(data)


def parse_raw_to_document(
    raw: str,
    source_filename: str,
) -> tuple[DocumentoDDT | None, str | None]:
    """Parse raw model text into DocumentoDDT. Returns (doc, error)."""
    try:
        json_text = extract_json_payload(raw)
        doc = validate_documento(json_text, source_filename)
        return doc, None
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        return None, str(exc)


def build_repair_prompt(original_raw: str, error_message: str) -> str:
    return (
        "The previous JSON response was invalid.\n"
        f"Validation error: {error_message}\n\n"
        "Original response:\n"
        f"{original_raw}\n\n"
        "Return a corrected JSON object that conforms to the schema. "
        "Do not invent missing values; use null. Output JSON only."
    )


def parse_and_validate(
    raw: str,
    source_filename: str,
    *,
    repair_fn: Callable[[str], str] | None = None,
) -> tuple[DocumentoDDT | None, str | None, int]:
    """
    Parse and validate JSON. Optionally perform one controlled repair via repair_fn.

    Returns: (document, error_message, retry_count)
    retry_count is 0 or 1.
    """
    doc, error = parse_raw_to_document(raw, source_filename)
    if doc is not None:
        return doc, None, 0

    if repair_fn is None:
        return None, error, 0

    repaired_raw = repair_fn(build_repair_prompt(raw, error or "unknown error"))
    doc2, error2 = parse_raw_to_document(repaired_raw, source_filename)
    if doc2 is not None:
        return doc2, None, 1
    return None, error2 or error, 1


def structure_json_schema() -> dict[str, Any]:
    return ollama_documento_schema()
