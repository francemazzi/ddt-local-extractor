"""Ollama HTTP client for text and vision generation."""

from __future__ import annotations

import base64
import logging
import time
import tracemalloc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from ddt_local.config import AppConfig

logger = logging.getLogger(__name__)


class OllamaServiceError(Exception):
    """Base error for Ollama client failures."""


class OllamaUnavailableError(OllamaServiceError):
    """Ollama service is not reachable."""


class OllamaModelNotFoundError(OllamaServiceError):
    """Requested model is not installed locally."""


class OllamaEmptyResponseError(OllamaServiceError):
    """Model returned an empty response."""


class OllamaTimeoutError(OllamaServiceError):
    """Request timed out."""


@dataclass
class GenerateResult:
    text: str
    model: str
    duration_seconds: float
    peak_memory_bytes: int | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


class OllamaClient:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._base_url = config.ollama_base_url

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._base_url,
            timeout=self._config.request_timeout_seconds,
        )

    def health_check(self) -> bool:
        try:
            with self._client() as client:
                response = client.get("/api/tags")
                response.raise_for_status()
                return True
        except httpx.HTTPError:
            return False

    def list_models(self) -> list[str]:
        with self._client() as client:
            response = client.get("/api/tags")
            response.raise_for_status()
            payload = response.json()
        return [m.get("name", "") for m in payload.get("models", [])]

    def ensure_model_available(self, model: str) -> None:
        if getattr(self, "_models_cache", None) is None:
            if not self.health_check():
                raise OllamaUnavailableError(
                    f"Ollama is not reachable at {self._base_url}. "
                    "Start it with: ollama serve"
                )
            self._models_cache = self.list_models()
        installed = self._models_cache
        if model not in installed and not any(model in m for m in installed):
            self._models_cache = self.list_models()
            installed = self._models_cache
            if model not in installed and not any(model in m for m in installed):
                raise OllamaModelNotFoundError(
                    f"Model '{model}' is not installed. Run: ollama pull {model}"
                )

    def unload_model(self, model: str) -> None:
        if not self._config.unload_models:
            return
        try:
            with self._client() as client:
                client.post(
                    "/api/generate",
                    json={"model": model, "prompt": "", "keep_alive": 0},
                )
        except httpx.HTTPError as exc:
            logger.warning("Failed to unload model %s: %s", model, type(exc).__name__)

    def generate_text(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        json_schema: dict[str, Any] | None = None,
        images: list[str] | None = None,
        keep_alive: str | int | None = None,
    ) -> GenerateResult:
        self.ensure_model_available(model)
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0,
                "seed": self._config.seed,
            },
        }
        if system:
            payload["system"] = system
        if json_schema:
            payload["format"] = json_schema
        if images:
            payload["images"] = images
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        elif self._config.unload_models:
            # Keep model warm during active use; unload_model() frees RAM later
            payload["keep_alive"] = "10m"

        return self._post_generate(payload, model)

    def generate_from_image(
        self,
        *,
        model: str,
        prompt: str,
        image_path: Path,
        system: str | None = None,
    ) -> GenerateResult:
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return self.generate_text(
            model=model,
            prompt=prompt,
            system=system,
            images=[image_b64],
        )

    def _post_generate(self, payload: dict[str, Any], model: str) -> GenerateResult:
        tracemalloc.start()
        start = time.perf_counter()
        last_error: Exception | None = None

        for attempt in range(1, self._config.max_retries + 1):
            try:
                with self._client() as client:
                    response = client.post("/api/generate", json=payload)
                    response.raise_for_status()
                    data = response.json()
                text = (data.get("response") or "").strip()
                if not text:
                    thinking = (data.get("thinking") or "").strip()
                    if thinking:
                        text = thinking
                if not text:
                    raise OllamaEmptyResponseError(f"Empty response from model '{model}'")
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                return GenerateResult(
                    text=text,
                    model=model,
                    duration_seconds=time.perf_counter() - start,
                    peak_memory_bytes=peak,
                    raw_response=data,
                )
            except httpx.TimeoutException as exc:
                last_error = OllamaTimeoutError(
                    f"Ollama request timed out after {self._config.request_timeout_seconds}s"
                )
            except (httpx.HTTPError, httpx.TransportError) as exc:
                last_error = OllamaServiceError(str(exc))
            except OllamaEmptyResponseError as exc:
                last_error = exc

            if attempt < self._config.max_retries:
                backoff = min(2 ** attempt, 15)
                logger.warning(
                    "Ollama generate attempt %s failed (%s); retry in %ss",
                    attempt,
                    type(last_error).__name__,
                    backoff,
                )
                time.sleep(backoff)

        tracemalloc.stop()
        assert last_error is not None
        raise last_error
