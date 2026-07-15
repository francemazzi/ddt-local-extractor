"""Application configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _expand_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    return int(raw)


@dataclass(frozen=True)
class AppConfig:
    ddt_home: Path
    ollama_base_url: str
    pipeline: str
    ocr_model: str
    struct_model: str
    vision_model: str
    render_dpi: int
    min_native_text_chars: int
    file_stability_seconds: int
    request_timeout_seconds: int
    max_retries: int
    seed: int
    keep_raw_ocr: bool
    unload_models: bool
    log_level: str

    @property
    def inbox_dir(self) -> Path:
        return self.ddt_home / "inbox"

    @property
    def processed_dir(self) -> Path:
        return self.ddt_home / "processed"

    @property
    def errors_dir(self) -> Path:
        return self.ddt_home / "errors"

    @property
    def raw_dir(self) -> Path:
        return self.ddt_home / "raw"

    @property
    def logs_dir(self) -> Path:
        return self.ddt_home / "logs"

    @property
    def output_dir(self) -> Path:
        return self.ddt_home / "output"

    @property
    def benchmark_dir(self) -> Path:
        return self.ddt_home / "benchmark"

    @property
    def data_dir(self) -> Path:
        return self.ddt_home / "data"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "ddt.sqlite3"

    @property
    def excel_path(self) -> Path:
        return self.output_dir / "DDT_estratti.xlsx"

    @property
    def lock_path(self) -> Path:
        return self.ddt_home / ".ddt_job.lock"


def load_config() -> AppConfig:
    """Load configuration from environment with spec defaults."""
    return AppConfig(
        ddt_home=_expand_path(os.getenv("DDT_HOME", "~/DDT")),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        pipeline=os.getenv("DDT_PIPELINE", "ocr_struct"),
        ocr_model=os.getenv("DDT_OCR_MODEL", "glm-ocr:latest"),
        struct_model=os.getenv("DDT_STRUCT_MODEL", "qwen3.5:4b"),
        vision_model=os.getenv("DDT_VISION_MODEL", "qwen3.5:4b"),
        render_dpi=_env_int("DDT_RENDER_DPI", 250),
        min_native_text_chars=_env_int("DDT_MIN_NATIVE_TEXT_CHARS", 200),
        file_stability_seconds=_env_int("DDT_FILE_STABILITY_SECONDS", 3),
        request_timeout_seconds=_env_int("DDT_REQUEST_TIMEOUT_SECONDS", 180),
        max_retries=_env_int("DDT_MAX_RETRIES", 3),
        seed=_env_int("DDT_SEED", 42),
        keep_raw_ocr=_env_bool("DDT_KEEP_RAW_OCR", True),
        unload_models=_env_bool("DDT_UNLOAD_MODELS", True),
        log_level=os.getenv("DDT_LOG_LEVEL", "INFO").upper(),
    )
