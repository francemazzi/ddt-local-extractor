"""Tests for validation helpers."""

from __future__ import annotations

import json

import pytest

from ddt_local.validation import (
    extract_json_payload,
    parse_and_validate,
    parse_raw_to_document,
    validate_documento,
)


VALID_PAYLOAD = {
    "source_filename": "test.pdf",
    "fornitore": {"ragione_sociale": "Test S.r.l."},
    "destinatario": {},
    "documento": {"numero_ddt": "DDT-1"},
    "articoli": [],
}


def test_extract_json_direct():
    raw = json.dumps(VALID_PAYLOAD)
    assert extract_json_payload(raw).startswith("{")


def test_extract_json_from_fence():
    raw = "```json\n" + json.dumps(VALID_PAYLOAD) + "\n```"
    payload = extract_json_payload(raw)
    assert json.loads(payload)["documento"]["numero_ddt"] == "DDT-1"


def test_extract_json_embedded_in_text():
    raw = "Here is the result:\n" + json.dumps(VALID_PAYLOAD) + "\nThanks"
    payload = extract_json_payload(raw)
    assert "DDT-1" in payload


def test_extract_json_empty_raises():
    with pytest.raises(ValueError, match="Empty"):
        extract_json_payload("")


def test_validate_documento_sets_filename():
    data = dict(VALID_PAYLOAD)
    del data["source_filename"]
    doc = validate_documento(data, "forced.pdf")
    assert doc.source_filename == "forced.pdf"


def test_parse_raw_valid():
    doc, err = parse_raw_to_document(json.dumps(VALID_PAYLOAD), "test.pdf")
    assert err is None
    assert doc is not None
    assert doc.documento.numero_ddt == "DDT-1"


def test_parse_raw_invalid_json():
    doc, err = parse_raw_to_document("not json", "test.pdf")
    assert doc is None
    assert err is not None


def test_parse_and_validate_success_no_retry():
    doc, err, retries = parse_and_validate(json.dumps(VALID_PAYLOAD), "test.pdf")
    assert doc is not None
    assert err is None
    assert retries == 0


def test_parse_and_validate_repair_success():
    def repair_fn(prompt: str) -> str:
        return json.dumps(VALID_PAYLOAD)

    doc, err, retries = parse_and_validate(
        "{invalid",
        "test.pdf",
        repair_fn=repair_fn,
    )
    assert doc is not None
    assert retries == 1
    assert err is None


def test_parse_and_validate_repair_fails():
    def repair_fn(prompt: str) -> str:
        return "still invalid"

    doc, err, retries = parse_and_validate(
        "{invalid",
        "test.pdf",
        repair_fn=repair_fn,
    )
    assert doc is None
    assert retries == 1
    assert err is not None
