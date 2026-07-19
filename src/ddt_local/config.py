"""Application configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ddt_local.user_config import load_user_settings


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
class PipelineSettings:
    """Per-run pipeline parameters (production config or benchmark overrides)."""

    pipeline: str
    ocr_model: str
    struct_model: str
    vision_model: str
    render_dpi: int
    ocr_table_pass: bool = False
    min_native_text_chars: int = 200
    seed: int = 42
    max_retries: int = 3
    request_timeout_seconds: int = 180
    unload_models: bool = True


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
    ocr_table_pass: bool = False

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
    user_settings = load_user_settings()
    configured_home = str(user_settings.ddt_home) if user_settings else "~/DDT"
    return AppConfig(
        # DDT_HOME is kept as an explicit advanced override for scripts, tests and
        # support workflows. Desktop users normally get their persisted selection.
        ddt_home=_expand_path(os.getenv("DDT_HOME", configured_home)),
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
        ocr_table_pass=_env_bool("DDT_OCR_TABLE_PASS", False),
    )


def settings_from_config(config: AppConfig, **overrides: object) -> PipelineSettings:
    """Build PipelineSettings from AppConfig with optional overrides."""
    base = {
        "pipeline": config.pipeline,
        "ocr_model": config.ocr_model,
        "struct_model": config.struct_model,
        "vision_model": config.vision_model,
        "render_dpi": config.render_dpi,
        "ocr_table_pass": config.ocr_table_pass,
        "min_native_text_chars": config.min_native_text_chars,
        "seed": config.seed,
        "max_retries": config.max_retries,
        "request_timeout_seconds": config.request_timeout_seconds,
        "unload_models": config.unload_models,
    }
    base.update(overrides)
    return PipelineSettings(**base)  # type: ignore[arg-type]


def settings_from_benchmark_run(config: AppConfig, run: dict) -> PipelineSettings:
    """Build PipelineSettings from a benchmark YAML run entry."""
    return settings_from_config(
        config,
        pipeline=run.get("pipeline", config.pipeline),
        ocr_model=run.get("ocr_model", config.ocr_model),
        struct_model=run.get("struct_model", config.struct_model),
        vision_model=run.get("vision_model", config.vision_model),
        render_dpi=int(run.get("render_dpi", config.render_dpi)),
        ocr_table_pass=bool(run.get("ocr_table_pass", config.ocr_table_pass)),
    )
