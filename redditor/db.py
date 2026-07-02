from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    post_title TEXT NOT NULL,
    post_desc TEXT NOT NULL DEFAULT '',
    post_link TEXT NOT NULL DEFAULT '',
    parent_comment TEXT,
    user_comment TEXT NOT NULL,
    subreddit TEXT,
    embedding BLOB,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subreddit TEXT NOT NULL,
    title TEXT NOT NULL,
    desc TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    reddit_post_id TEXT NOT NULL UNIQUE,
    icp_name TEXT NOT NULL,
    relevance_score REAL NOT NULL,
    intent TEXT,
    thread_tone TEXT,
    referenced_link TEXT,
    is_lead INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'sourced',
    sourced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_post_id INTEGER NOT NULL REFERENCES candidate_posts(id),
    comment_body TEXT NOT NULL,
    similarity_score REAL,
    self_checklist_json TEXT,
    gate_result_json TEXT,
    mode_at_creation TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_review',
    created_at TEXT NOT NULL,
    posted_at TEXT,
    reddit_comment_id TEXT
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_post_id INTEGER NOT NULL REFERENCES candidate_posts(id),
    signal_snippet TEXT NOT NULL,
    icp_name TEXT NOT NULL,
    flagged_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subreddit_config (
    subreddit TEXT PRIMARY KEY,
    min_karma INTEGER NOT NULL DEFAULT 0,
    min_age_days INTEGER NOT NULL DEFAULT 0,
    self_promo_allowed INTEGER NOT NULL DEFAULT 0,
    banned_keywords_json TEXT NOT NULL DEFAULT '[]',
    rules_text TEXT NOT NULL DEFAULT '',
    last_refreshed TEXT
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    subreddit TEXT,
    ref_id TEXT,
    timestamp TEXT NOT NULL,
    outcome TEXT
);

CREATE TABLE IF NOT EXISTS account_state (
    account TEXT PRIMARY KEY,
    daily_counts_json TEXT NOT NULL DEFAULT '{}',
    daily_counts_date TEXT NOT NULL,
    cooldown_until TEXT,
    last_comment_at TEXT
);
"""


def db_path() -> Path:
    return Path(os.environ.get("REDDITOR_DB_PATH", "data/redditor.db"))


@contextmanager
def get_db():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(SCHEMA)


def log_activity(conn: sqlite3.Connection, action: str, subreddit: str | None = None,
                  ref_id: str | None = None, outcome: str | None = None) -> None:
    from datetime import datetime

    conn.execute(
        "INSERT INTO activity_log (action, subreddit, ref_id, timestamp, outcome) "
        "VALUES (?, ?, ?, ?, ?)",
        (action, subreddit, ref_id, datetime.utcnow().isoformat(), outcome),
    )
