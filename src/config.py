"""Pydantic Settings — environment variable loading for Context Engine."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Core
    context_engine_port: int = 8410
    context_engine_token: str = ""
    context_engine_db: str = "./data/context.db"

    # OpenRouter (primary LLM)
    openrouter_api_key: str = ""

    # Gemini (legacy, unused if OpenRouter configured)
    gemini_api_key: str = ""

    # Ollama (fallback)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:1.7b"

    # Notion
    notion_api_token: str = ""
    notion_todo_db: str = ""
    notion_session_db: str = ""

    # LCM-Lite
    lcm_lite_url: str = "http://localhost:8400"
    lcm_lite_token: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = "8697133440"

    # Gmail
    gmail_address: str = ""
    gmail_app_password: str = ""

    # Compile schedule
    compile_schedule: str = "7:00,19:00"

    # Staleness thresholds (hours) — per-category per Review Fix 4
    staleness_hours_task: int = 48
    staleness_hours_decision: int = 168
    staleness_hours_blocker: int = 0
    staleness_hours_tech_state: int = 168
    staleness_hours_note: int = 336

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
