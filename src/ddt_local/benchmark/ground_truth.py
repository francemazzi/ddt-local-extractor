"""Ground truth loading and conversion from dataset format to DocumentoDDT."""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ddt_local.models import DatiDocumento, DocumentoDDT, RigaDDT, Soggetto

COLLECTION_FILENAME = "DDT_simulati_siderurgia_raccolta.pdf"
_DATE_PATTERNS = (
    re.compile(r"^(\d{2})/(\d{2})/(\d{4})$"),
    re.compile(r"^(\d{2})-(\d{2})-(\d{4})$"),
)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()
    for pattern in _DATE_PATTERNS:
        match = pattern.match(text)
        if match:
            day, month, year = match.groups()
            return date(int(year), int(month), int(day))
    return None


def to_decimal(value: Any) -> Decimal | None:
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


def parse_packages(value: str | int | float | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return to_decimal(value)
    text = str(value).strip()
    match = re.search(r"(\d+)", text)
    if match:
        return Decimal(match.group(1))
    return None


def _join_address(address: str | None, city: str | None) -> str | None:
    parts = [p.strip() for p in (address, city) if p and p.strip()]
    if not parts:
        return None
    return ", ".join(parts)


def _map_soggetto(data: dict[str, Any] | None) -> Soggetto:
    if not data:
        return Soggetto()
    return Soggetto(
        ragione_sociale=data.get("name"),
        partita_iva=data.get("vat"),
        codice_fiscale=None,
        indirizzo=_join_address(data.get("address"), data.get("city")),
    )


def _map_riga(item: dict[str, Any], index: int) -> RigaDDT:
    return RigaDDT(
        numero_riga=index,
        codice=item.get("code"),
        descrizione=item.get("description"),
        quantita=to_decimal(item.get("qty")),
        unita_misura=item.get("um"),
        lotto=item.get("lot"),
        matricola=None,
    )


def _map_documento(data: dict[str, Any]) -> DatiDocumento:
    return DatiDocumento(
        numero_ddt=data.get("ddt_number"),
        data_ddt=parse_date(data.get("date")),
        riferimento_ordine=data.get("order_ref"),
        causale_trasporto=data.get("reason"),
        numero_colli=parse_packages(data.get("packages")),
        peso_lordo=to_decimal(data.get("gross_weight")),
        peso_netto=to_decimal(data.get("net_weight")),
        vettore=data.get("carrier"),
        destinazione=data.get("destination"),
    )


def convert_dataset_document(raw: dict[str, Any]) -> DocumentoDDT:
    """Convert a single dataset JSON document entry to DocumentoDDT."""
    filename = raw.get("file")
    if not filename:
        raise ValueError("Dataset document missing 'file' field")

    items = raw.get("items") or []
    articoli = [_map_riga(item, idx + 1) for idx, item in enumerate(items)]

    return DocumentoDDT(
        source_filename=filename,
        fornitore=_map_soggetto(raw.get("sender")),
        destinatario=_map_soggetto(raw.get("recipient")),
        documento=_map_documento(raw),
        articoli=articoli,
    )


def load_dataset_ground_truth(path: Path) -> dict[str, DocumentoDDT]:
    """Load all documents from dataset/ground_truth_ddt.json keyed by filename."""
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)

    documents = payload.get("documents", [])
    result: dict[str, DocumentoDDT] = {}
    for raw in documents:
        doc = convert_dataset_document(raw)
        if doc.source_filename == COLLECTION_FILENAME:
            continue
        result[doc.source_filename] = doc
    return result


def load_ground_truth_file(path: Path) -> DocumentoDDT:
    """Load a single per-document ground truth JSON file."""
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    return DocumentoDDT.model_validate(payload)


def load_ground_truth_dir(directory: Path) -> dict[str, DocumentoDDT]:
    """Load all per-document JSON files from a directory."""
    result: dict[str, DocumentoDDT] = {}
    for json_path in sorted(directory.glob("*.json")):
        doc = load_ground_truth_file(json_path)
        result[doc.source_filename] = doc
    return result
