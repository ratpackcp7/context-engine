"""Tests for LLM abstraction — parsing, fence stripping, and fallback logic."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm import LLMClient, parse_compile_delta, strip_fences
from src.models import CompileDelta


# ---- strip_fences tests ----

class TestStripFences:
    def test_no_fences(self):
        raw = '{"add": [], "update": [], "archive": []}'
        assert strip_fences(raw) == raw

    def test_json_fences(self):
        raw = '```json\n{"add": [], "update": [], "archive": []}\n```'
        assert strip_fences(raw) == '{"add": [], "update": [], "archive": []}'

    def test_plain_fences(self):
        raw = '```\n{"add": []}\n```'
        assert strip_fences(raw) == '{"add": []}'

    def test_fences_with_whitespace(self):
        raw = '  ```json\n{"add": []}\n```  '
        assert strip_fences(raw) == '{"add": []}'

    def test_empty_string(self):
        assert strip_fences("") == ""


# ---- parse_compile_delta tests ----

class TestParseCompileDelta:
    def test_valid_json(self):
        raw = '{"add": [{"category": "task", "content": "Do X", "source": "notion_todo"}], "update": [], "archive": []}'
        result = parse_compile_delta(raw)
        assert result is not None
        assert len(result.add) == 1
        assert result.add[0].category == "task"
        assert result.add[0].content == "Do X"

    def test_fenced_json(self):
        raw = '```json\n{"add": [{"category": "decision", "content": "Use X", "source": "lcm"}], "update": [], "archive": []}\n```'
        result = parse_compile_delta(raw)
        assert result is not None
        assert len(result.add) == 1
        assert result.add[0].category == "decision"

    def test_minimal_json(self):
        result = parse_compile_delta("{}")
        assert result is not None
        assert result.add == []
        assert result.update == []
        assert result.archive == []

    def test_invalid_json(self):
        result = parse_compile_delta("not json at all")
        assert result is None

    def test_empty_string(self):
        result = parse_compile_delta("")
        assert result is None

    def test_valid_with_update_and_archive(self):
        raw = '{"add": [], "update": [{"bullet_id": "abc", "content": "updated"}], "archive": [{"bullet_id": "def", "reason": "done"}]}'
        result = parse_compile_delta(raw)
        assert result is not None
        assert len(result.update) == 1
        assert result.update[0].bullet_id == "abc"
        assert len(result.archive) == 1
        assert result.archive[0].reason == "done"

    def test_invalid_category(self):
        raw = '{"add": [{"category": "INVALID", "content": "X", "source": "lcm"}]}'
        result = parse_compile_delta(raw)
        assert result is None


# ---- LLMClient fallback logic tests ----

@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.gemini_api_key = "fake-key"
    settings.ollama_url = "http://localhost:11434"
    settings.ollama_model = "qwen3:1.7b"
    return settings


VALID_DELTA_JSON = '{"add": [{"category": "task", "content": "test", "source": "lcm"}], "update": [], "archive": []}'


class TestLLMClientFallback:
    @pytest.mark.asyncio
    async def test_gemini_success(self, mock_settings):
        client = LLMClient(settings=mock_settings)
        # Mock gemini to return valid JSON
        client._call_gemini = AsyncMock(return_value=VALID_DELTA_JSON)
        client._call_ollama = AsyncMock(return_value=None)

        result = await client.compile("test prompt")
        assert result is not None
        assert len(result.add) == 1
        client._call_gemini.assert_called_once()
        client._call_ollama.assert_not_called()

    @pytest.mark.asyncio
    async def test_gemini_fails_ollama_succeeds(self, mock_settings):
        client = LLMClient(settings=mock_settings)
        client.RETRY_DELAY = 0  # skip sleep in tests
        client._call_gemini = AsyncMock(return_value=None)
        client._call_ollama = AsyncMock(return_value=VALID_DELTA_JSON)

        result = await client.compile("test prompt")
        assert result is not None
        assert len(result.add) == 1
        # Gemini called twice (initial + retry), then Ollama once
        assert client._call_gemini.call_count == 2
        assert client._call_ollama.call_count >= 1

    @pytest.mark.asyncio
    async def test_all_providers_fail(self, mock_settings):
        client = LLMClient(settings=mock_settings)
        client.RETRY_DELAY = 0
        client._call_gemini = AsyncMock(return_value=None)
        client._call_ollama = AsyncMock(return_value=None)

        result = await client.compile("test prompt")
        assert result is None

    @pytest.mark.asyncio
    async def test_gemini_returns_bad_json_retries_parse(self, mock_settings):
        client = LLMClient(settings=mock_settings)
        client.RETRY_DELAY = 0
        # _try_gemini returns bad text, then _call_gemini returns valid on stricter retry
        client._try_gemini = AsyncMock(return_value="not valid json")
        client._try_ollama = AsyncMock(return_value=None)
        client._call_gemini = AsyncMock(return_value=VALID_DELTA_JSON)

        result = await client.compile("test prompt")
        # Should retry parse with stricter prompt via gemini
        assert result is not None
        assert len(result.add) == 1
        # _call_gemini called once for the stricter retry
        client._call_gemini.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_gemini_key_skips_to_ollama(self, mock_settings):
        mock_settings.gemini_api_key = ""
        client = LLMClient(settings=mock_settings)
        client.RETRY_DELAY = 0
        client._call_ollama = AsyncMock(return_value=VALID_DELTA_JSON)

        result = await client.compile("test prompt")
        assert result is not None

    @pytest.mark.asyncio
    async def test_fenced_response_parsed(self, mock_settings):
        client = LLMClient(settings=mock_settings)
        fenced = f"```json\n{VALID_DELTA_JSON}\n```"
        client._call_gemini = AsyncMock(return_value=fenced)

        result = await client.compile("test prompt")
        assert result is not None
        assert len(result.add) == 1
