"""SQLite setup — async connection, WAL mode, table creation."""

import aiosqlite

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,
    notion_page_id  TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bullets (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL REFERENCES projects(id),
    category         TEXT NOT NULL,
    content          TEXT NOT NULL,
    source           TEXT NOT NULL,
    source_id        TEXT,
    status           TEXT NOT NULL DEFAULT 'active',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    last_verified_at TEXT NOT NULL,
    helpful_count    INTEGER NOT NULL DEFAULT 0,
    harmful_count    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    id             TEXT PRIMARY KEY,
    project_id     TEXT REFERENCES projects(id),
    summary        TEXT NOT NULL,
    decisions      TEXT NOT NULL DEFAULT '[]',
    open_items     TEXT NOT NULL DEFAULT '[]',
    tech_changes   TEXT NOT NULL DEFAULT '[]',
    next_steps     TEXT NOT NULL DEFAULT '[]',
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digests (
    id              TEXT PRIMARY KEY,
    generated_at    TEXT NOT NULL,
    stale_count     INTEGER NOT NULL DEFAULT 0,
    summary_text    TEXT NOT NULL DEFAULT '',
    sent_telegram   INTEGER NOT NULL DEFAULT 0,
    sent_email      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS compile_runs (
    id               TEXT PRIMARY KEY,
    started_at       TEXT NOT NULL,
    completed_at     TEXT,
    project_slugs    TEXT NOT NULL DEFAULT '[]',
    bullets_added    INTEGER NOT NULL DEFAULT 0,
    bullets_updated  INTEGER NOT NULL DEFAULT 0,
    bullets_archived INTEGER NOT NULL DEFAULT 0,
    llm_provider     TEXT,
    llm_model        TEXT,
    error            TEXT
);
"""


async def init_db(db_path: str) -> None:
    """Create tables and set pragmas (WAL, busy_timeout, foreign_keys)."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.executescript(_CREATE_TABLES)
        await db.commit()


async def get_db(db_path: str) -> aiosqlite.Connection:
    """Open a connection with required pragmas set."""
    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA busy_timeout=5000;")
    await db.execute("PRAGMA foreign_keys=ON;")
    db.row_factory = aiosqlite.Row
    return db
