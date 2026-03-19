"""LLM abstraction — Gemini Flash primary, Ollama fallback."""

from __future__ import annotations

import asyncio
import logging
import re

from google import genai
from google.genai import types as genai_types
import ollama

from src.config import Settings
from src.models import CompileDelta

logger = logging.getLogger(__name__)

# Regex to strip markdown code fences (```json ... ``` or ``` ... ```)
_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def strip_fences(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    text = text.strip()
    m = _FENCE_RE.match(text)
    if m:
        return m.group(1).strip()
    return text


def parse_compile_delta(raw: str) -> CompileDelta | None:
    """Parse raw LLM text into a CompileDelta, returning None on failure."""
    cleaned = strip_fences(raw)
    try:
        return CompileDelta.model_validate_json(cleaned)
    except Exception as exc:
        logger.warning("Failed to parse CompileDelta: %s", exc)
        return None


class LLMClient:
    """Gemini Flash primary, Ollama fallback. One retry per provider with 2s backoff."""

    GEMINI_MODEL = "gemini-2.0-flash"
    RETRY_DELAY = 2.0  # seconds

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        # Gemini client (None if no API key)
        self._gemini: genai.Client | None = None
        if self.settings.gemini_api_key:
            self._gemini = genai.Client(api_key=self.settings.gemini_api_key)
        # Ollama client
        self._ollama = ollama.AsyncClient(host=self.settings.ollama_url)

    # ----- public API -----

    async def compile(self, prompt: str) -> CompileDelta | None:
        """Send prompt to LLM, parse response as CompileDelta.

        Fallback sequence: Gemini → retry → Ollama → retry → None.
        """
        provider = "gemini"
        text = await self._try_gemini(prompt)
        if text is None:
            provider = "ollama"
            text = await self._try_ollama(prompt)
        if text is None:
            logger.error("All LLM providers failed")
            return None

        delta = parse_compile_delta(text)
        if delta is None:
            # Retry once with a stricter prompt
            logger.info("Parse failed, retrying with stricter prompt (%s)", provider)
            strict = (
                "IMPORTANT: Respond with ONLY valid JSON, no markdown fences, no explanation.\n\n"
                + prompt
            )
            if provider == "gemini":
                text = await self._call_gemini(strict)
            else:
                text = await self._call_ollama(strict)
            if text is not None:
                delta = parse_compile_delta(text)
            if delta is None:
                logger.error("Parse failed after retry")

        if delta is not None:
            logger.info("Compile succeeded via %s", provider)
        return delta

    # ----- Gemini -----

    async def _try_gemini(self, prompt: str) -> str | None:
        """Try Gemini with one retry."""
        if self._gemini is None:
            logger.warning("Gemini API key not configured, skipping")
            return None
        text = await self._call_gemini(prompt)
        if text is not None:
            return text
        logger.warning("Gemini first attempt failed, retrying in %.1fs", self.RETRY_DELAY)
        await asyncio.sleep(self.RETRY_DELAY)
        return await self._call_gemini(prompt)

    async def _call_gemini(self, prompt: str) -> str | None:
        """Single Gemini API call."""
        try:
            assert self._gemini is not None
            response = await self._gemini.aio.models.generate_content(
                model=self.GEMINI_MODEL,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=4096,
                ),
            )
            text = response.text
            if text:
                usage = response.usage_metadata
                if usage:
                    logger.info(
                        "Gemini tokens — prompt: %s, completion: %s, total: %s",
                        usage.prompt_token_count,
                        usage.candidates_token_count,
                        usage.total_token_count,
                    )
                return text
            logger.warning("Gemini returned empty text")
            return None
        except Exception as exc:
            logger.warning("Gemini call failed: %s", exc)
            return None

    # ----- Ollama -----

    async def _try_ollama(self, prompt: str) -> str | None:
        """Try Ollama with one retry."""
        text = await self._call_ollama(prompt)
        if text is not None:
            return text
        logger.warning("Ollama first attempt failed, retrying in %.1fs", self.RETRY_DELAY)
        await asyncio.sleep(self.RETRY_DELAY)
        return await self._call_ollama(prompt)

    async def _call_ollama(self, prompt: str) -> str | None:
        """Single Ollama API call."""
        try:
            response = await self._ollama.chat(
                model=self.settings.ollama_model,
                messages=[{"role": "user", "content": prompt}],
                format="json",
            )
            text = response.message.content
            if text:
                logger.info("Ollama model: %s", self.settings.ollama_model)
                return text
            logger.warning("Ollama returned empty content")
            return None
        except Exception as exc:
            logger.warning("Ollama call failed: %s", exc)
            return None
