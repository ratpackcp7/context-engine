# Task 003: LLM abstraction — Gemini Flash primary, Ollama fallback

## Objective

Build the LLM abstraction layer that handles Gemini Flash as primary and Ollama as fallback, with retry logic and structured output parsing.

## Context

Task 002 complete. Config, models, and database exist. `src/models.py` has CompileDelta schema.

## Spec Reference

SPEC.md: Tech Stack (LLM), Compile Loop Step 2, Review Fix 2 (output validation), Review Fix 5 (fallback sequence).

## Operation Order

1. Write `src/llm.py` with abstract interface
2. Implement Gemini Flash provider using `google-genai` SDK
3. Implement Ollama provider using `ollama` SDK (model from config, default qwen3:1.7b)
4. Implement fallback logic: Gemini → retry once → Ollama → retry once → return None
5. Implement response parsing: strip markdown fences, validate with CompileDelta.model_validate_json()
6. Write `tests/test_llm.py` — test parse logic with mock responses (valid JSON, fenced JSON, invalid JSON, empty)

## Deliverables

- [ ] `src/llm.py` — LLMClient class with: `async def compile(self, prompt: str) -> CompileDelta | None`
- [ ] `tests/test_llm.py` — Tests for parsing and fallback logic (mocked, no real API calls)

## Acceptance Criteria

1. [ ] `python -c "from src.llm import LLMClient; print('LLM OK')"`
2. [ ] `pytest tests/test_llm.py -v` — all tests pass
3. [ ] Parse test: valid JSON → CompileDelta object
4. [ ] Parse test: ```json-fenced → strips fences, parses correctly
5. [ ] Parse test: invalid JSON → returns None (no crash)

## Notes

- `google-genai` SDK: use `genai.Client(api_key=...)` then `client.models.generate_content(model="gemini-2.0-flash", contents=prompt)`
- Web search current google-genai docs before implementing — API surface changes frequently
- Ollama: `ollama.AsyncClient(host=config.ollama_url)` then `client.chat(model=..., messages=[...])`
- Backoff: 2s between retries per provider
- Log which provider was used + token counts if available
