"""Tests for Ollama client (mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from ddt_local.config import load_config
from ddt_local.ollama import (
    OllamaClient,
    OllamaEmptyResponseError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)


@pytest.fixture
def client(app_config, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    return OllamaClient(load_config())


def _mock_response(json_data, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    response.raise_for_status = MagicMock()
    return response


def test_health_check_success(client: OllamaClient):
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response({"models": []})
        mock_client_cls.return_value = mock_client
        assert client.health_check() is True


def test_health_check_failure(client: OllamaClient):
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.ConnectError("connection refused")
        mock_client_cls.return_value = mock_client
        assert client.health_check() is False


def test_ensure_model_available_raises_when_down(client: OllamaClient):
    with patch.object(client, "health_check", return_value=False):
        with pytest.raises(OllamaUnavailableError, match="not reachable"):
            client.ensure_model_available("glm-ocr:latest")


def test_ensure_model_available_raises_when_missing(client: OllamaClient):
    with patch.object(client, "health_check", return_value=True):
        with patch.object(client, "list_models", return_value=["other:model"]):
            with pytest.raises(OllamaModelNotFoundError, match="not installed"):
                client.ensure_model_available("glm-ocr:latest")


def test_generate_text_success(client: OllamaClient):
    with patch.object(client, "ensure_model_available"):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.post.return_value = _mock_response(
                {"response": '{"numero_ddt": "X"}'}
            )
            mock_client_cls.return_value = mock_client

            result = client.generate_text(
                model="qwen3.5:4b",
                prompt="extract",
                json_schema={"type": "object"},
            )
            assert "numero_ddt" in result.text
            assert result.model == "qwen3.5:4b"
            assert result.duration_seconds >= 0


def test_generate_text_empty_response_retries_then_fails(client: OllamaClient, monkeypatch):
    monkeypatch.setenv("DDT_MAX_RETRIES", "2")
    client = OllamaClient(load_config())
    with patch.object(client, "ensure_model_available"):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.post.return_value = _mock_response({"response": ""})
            mock_client_cls.return_value = mock_client
            with patch("time.sleep"):
                with pytest.raises(OllamaEmptyResponseError):
                    client.generate_text(model="qwen3.5:4b", prompt="test")


def test_generate_text_timeout(client: OllamaClient, monkeypatch):
    monkeypatch.setenv("DDT_MAX_RETRIES", "1")
    client = OllamaClient(load_config())
    with patch.object(client, "ensure_model_available"):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.post.side_effect = httpx.TimeoutException("timeout")
            mock_client_cls.return_value = mock_client
            with pytest.raises(OllamaTimeoutError):
                client.generate_text(model="qwen3.5:4b", prompt="test")


def test_generate_text_uses_thinking_when_response_empty(client: OllamaClient):
    with patch.object(client, "ensure_model_available"):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.post.return_value = _mock_response(
                {"response": "", "thinking": '{"status": "ok"}'}
            )
            mock_client_cls.return_value = mock_client

            result = client.generate_text(
                model="qwen3.5:4b",
                prompt="test",
                json_schema={"type": "object"},
            )
            assert "ok" in result.text


@pytest.mark.ollama
def test_ollama_integration_health_and_models(app_config):
    """Requires local Ollama running with models pulled."""
    client = OllamaClient(app_config)
    if not client.health_check():
        pytest.skip("Ollama not running")
    models = client.list_models()
    assert isinstance(models, list)
