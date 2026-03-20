"""LLM abstraction — OpenRouter (DeepSeek V3 primary), no local inference."""

from __future__ import annotations

import asyncio
import json
import logging
import re

import httpx

from src.config import Settings
from src.models import CompileDelta

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
PRIMARY_MODEL = "deepseek/deepseek-chat"  # DeepSeek V3 — fast, ~$0.0001/call

# Patterns to strip from LLM output before JSON parsing
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)


def extract_json(text: str) -> str:
    """Extract JSON from LLM output, stripping thinking tags, fences, and preamble."""
    # Strip <think>...</think> blocks (DeepSeek V3)
    text = _THINK_RE.sub("", text).strip()

    # Strip markdown code fences
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()

    # Find the first { and last } — extract the JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    return text.strip()


def parse_compile_delta(raw: str) -> CompileDelta | None:
    """Parse raw LLM text into a CompileDelta, returning None on failure."""
    cleaned = extract_json(raw)
    if not cleaned:
        logger.warning("No JSON found in LLM output (length=%d)", len(raw))
        return None
    try:
        return CompileDelta.model_validate_json(cleaned)
    except Exception as exc:
        # Log a snippet of what we tried to parse
        logger.warning("Failed to parse CompileDelta: %s — raw snippet: %s", exc, cleaned[:200])
        return None


class LLMClient:
    """OpenRouter with DeepSeek V3. No local CPU ever."""

    RETRY_DELAY = 2.0

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    async def compile(self, prompt: str) -> CompileDelta | None:
        if not self.settings.openrouter_api_key:
            logger.error("OpenRouter API key not configured")
            return None

        text = await self._try(prompt)
        if text is None:
            logger.error("LLM call failed")
            return None

        delta = parse_compile_delta(text)
        if delta is None:
            logger.info("Parse failed, retrying with stricter prompt")
            strict = (
                "IMPORTANT: Respond with ONLY valid JSON. No <think> tags, no markdown fences, "
                "no explanation. Just the raw JSON object starting with { and ending with }.\n\n"
                + prompt
            )
            text = await self._call(strict)
            if text is not None:
                delta = parse_compile_delta(text)
            if delta is None:
                logger.error("Parse failed after retry")

        if delta is not None:
            logger.info("Compile succeeded via %s", PRIMARY_MODEL)
        return delta

    async def _try(self, prompt: str) -> str | None:
        text = await self._call(prompt)
        if text is not None:
            return text
        logger.warning("First attempt failed, retrying in %.1fs", self.RETRY_DELAY)
        await asyncio.sleep(self.RETRY_DELAY)
        return await self._call(prompt)

    async def _call(self, prompt: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": PRIMARY_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                        "max_tokens": 16384,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                logger.info(
                    "%s — prompt: %s, completion: %s tokens",
                    PRIMARY_MODEL,
                    usage.get("prompt_tokens", "?"),
                    usage.get("completion_tokens", "?"),
                )
                return text if text else None
        except Exception as exc:
            logger.warning("%s call failed: %s", PRIMARY_MODEL, exc)
            return None
