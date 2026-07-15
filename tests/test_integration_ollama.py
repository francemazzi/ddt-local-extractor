"""Per-phase Ollama integration tests — run with: pytest -m ollama -v"""

from __future__ import annotations

from pathlib import Path

import pytest

from ddt_local.benchmark.ground_truth import load_dataset_ground_truth
from ddt_local.config import load_config
from ddt_local.database import Database
from ddt_local.files import compute_sha256
from ddt_local.models import DocumentoDDT, documento_ddt_json_schema
from ddt_local.ollama import OllamaClient
from ddt_local.pdf import analyze_pdf, render_page_png
from ddt_local.pipelines import create_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = PROJECT_ROOT / "dataset"
NATIVE_PDF = DATASET_DIR / "01_DDT_Acciai_Nordest.pdf"
SCAN_PDF = DATASET_DIR / "08_DDT_Inox_Labirinto_scansione.pdf"
GT_PATH = DATASET_DIR / "ground_truth_ddt.json"

REQUIRED_MODELS = ("glm-ocr:latest", "qwen3.5:4b", "qwen3.5:9b")


@pytest.fixture(scope="module")
def ollama_client():
    config = load_config()
    client = OllamaClient(config)
    if not client.health_check():
        pytest.skip("Ollama not running — start with: ollama serve")
    return client


@pytest.fixture(scope="module")
def ensure_models(ollama_client: OllamaClient):
    installed = ollama_client.list_models()
    missing = [m for m in REQUIRED_MODELS if m not in installed]
    if missing:
        pytest.skip(f"Missing models: {missing}. Run: ollama pull <model>")
    return installed


# --- Phase 0: environment + Ollama reachable ---


@pytest.mark.ollama
def test_phase0_ollama_service_reachable(ollama_client: OllamaClient):
    assert ollama_client.health_check() is True


# --- Phase 1: models + config work with live Ollama ---


@pytest.mark.ollama
def test_phase1_config_and_json_schema_with_ollama(ensure_models):
    config = load_config()
    assert config.ollama_base_url.startswith("http")
    schema = documento_ddt_json_schema()
    assert schema["title"] == "DocumentoDDT"
    assert config.ocr_model in ensure_models


# --- Phase 2: ground truth adapter (no Ollama call, runs in ollama suite) ---


@pytest.mark.ollama
def test_phase2_ground_truth_loads_while_ollama_up(ensure_models):
    docs = load_dataset_ground_truth(GT_PATH)
    assert len(docs) == 10
    first = docs["01_DDT_Acciai_Nordest.pdf"]
    assert isinstance(first, DocumentoDDT)
    assert first.documento.numero_ddt is not None


# --- Phase 3: database works while Ollama up ---


@pytest.mark.ollama
def test_phase3_database_init_while_ollama_up(ensure_models, tmp_path):
    db = Database(tmp_path / "phase3.sqlite3")
    db.initialize()
    assert db.count_production_documents() == 0


# --- Phase 4: file hashing on real dataset PDFs ---


@pytest.mark.ollama
def test_phase4_hash_real_pdfs_while_ollama_up(ensure_models):
    assert NATIVE_PDF.exists()
    digest = compute_sha256(NATIVE_PDF)
    assert len(digest) == 64


# --- Phase 5: Ollama client full integration ---


@pytest.mark.ollama
def test_phase5_required_models_installed(ensure_models):
    for model in REQUIRED_MODELS:
        assert model in ensure_models


@pytest.mark.ollama
def test_phase5_generate_text_qwen(ollama_client: OllamaClient, ensure_models):
    result = ollama_client.generate_text(
        model="qwen3.5:4b",
        prompt='Return JSON with field status set to "ok".',
        json_schema={"type": "object", "properties": {"status": {"type": "string"}}},
    )
    assert result.text
    assert "ok" in result.text.lower()
    assert result.duration_seconds >= 0
    ollama_client.unload_model("qwen3.5:4b")


# --- Phase 6: PDF analysis + OCR on scanned document ---


@pytest.mark.ollama
def test_phase6_native_pdf_detected(ensure_models):
    config = load_config()
    analysis = analyze_pdf(NATIVE_PDF, config)
    assert analysis.page_count >= 1
    assert not analysis.is_mostly_scanned


@pytest.mark.ollama
def test_phase6_scan_pdf_needs_ocr(ensure_models):
    config = load_config()
    analysis = analyze_pdf(SCAN_PDF, config)
    assert analysis.needs_visual_ocr


@pytest.mark.ollama
def test_phase6_glm_ocr_on_scanned_page(ollama_client: OllamaClient, ensure_models, tmp_path):
    from ddt_local.ocr import OcrEngine

    config = load_config()
    rendered = render_page_png(SCAN_PDF, page_number=1, config=config, output_dir=tmp_path)
    engine = OcrEngine(config, client=ollama_client)
    result = engine.ocr_image(rendered.image_path, page_number=1)
    assert len(result.text) > 20, "OCR should return meaningful text"
    ollama_client.unload_model(config.ocr_model)


# --- Phase 7: pipeline factory resolves while Ollama up ---


@pytest.mark.ollama
def test_phase7_pipeline_factory_while_ollama_up(ensure_models):
    config = load_config()
    pipeline = create_pipeline(config)
    assert pipeline.name == config.pipeline
