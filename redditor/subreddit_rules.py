from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

from .db import get_db
from .models import SubredditConfig
from .reddit_client.factory import get_reddit_client

DEFAULT_REFRESH_MAX_AGE_DAYS = 7


def get_or_refresh_subreddit_config(subreddit: str, max_age_days: int = DEFAULT_REFRESH_MAX_AGE_DAYS) -> SubredditConfig:
    """Fetches r/{sub}/about/rules and caches it. Manually-set fields
    (min_karma, min_age_days, self_promo_allowed, banned_keywords) are
    preserved across refreshes — only rules_text/last_refreshed get
    overwritten by the fetch."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM subreddit_config WHERE subreddit = ?", (subreddit,)
        ).fetchone()

        needs_refresh = row is None or _is_stale(row["last_refreshed"], max_age_days)
        if not needs_refresh:
            return _row_to_config(row)

        rules_text = _fetch_rules_text(subreddit)
        config = _upsert(conn, subreddit, rules_text, existing=row)
        return config


def _is_stale(last_refreshed: str | None, max_age_days: int) -> bool:
    if not last_refreshed:
        return True
    try:
        refreshed_at = datetime.fromisoformat(last_refreshed)
    except ValueError:
        return True
    return datetime.utcnow() - refreshed_at > timedelta(days=max_age_days)


def _fetch_rules_text(subreddit: str) -> str:
    try:
        reddit = get_reddit_client()
        payload = reddit.get_subreddit_rules(subreddit)
        rules = payload.get("rules", [])
        return "\n".join(f"- {r['short_name']}: {r['description']}" for r in rules)
    except Exception:
        return ""


def _upsert(conn: sqlite3.Connection, subreddit: str, rules_text: str, existing: sqlite3.Row | None) -> SubredditConfig:
    now = datetime.utcnow().isoformat()
    if existing:
        conn.execute(
            "UPDATE subreddit_config SET rules_text = ?, last_refreshed = ? WHERE subreddit = ?",
            (rules_text, now, subreddit),
        )
        return SubredditConfig(
            subreddit=subreddit,
            min_karma=existing["min_karma"],
            min_age_days=existing["min_age_days"],
            self_promo_allowed=bool(existing["self_promo_allowed"]),
            banned_keywords=json.loads(existing["banned_keywords_json"]),
            rules_text=rules_text,
            last_refreshed=now,
        )
    conn.execute(
        "INSERT INTO subreddit_config (subreddit, min_karma, min_age_days, self_promo_allowed, "
        "banned_keywords_json, rules_text, last_refreshed) VALUES (?, 0, 0, 0, '[]', ?, ?)",
        (subreddit, rules_text, now),
    )
    return SubredditConfig(subreddit=subreddit, rules_text=rules_text, last_refreshed=now)


def _row_to_config(row: sqlite3.Row) -> SubredditConfig:
    return SubredditConfig(
        subreddit=row["subreddit"],
        min_karma=row["min_karma"],
        min_age_days=row["min_age_days"],
        self_promo_allowed=bool(row["self_promo_allowed"]),
        banned_keywords=json.loads(row["banned_keywords_json"]),
        rules_text=row["rules_text"],
        last_refreshed=row["last_refreshed"],
    )


def set_subreddit_overrides(subreddit: str, min_karma: int | None = None, min_age_days: int | None = None,
                             self_promo_allowed: bool | None = None, banned_keywords: list[str] | None = None) -> None:
    """Manual override entry point — call before/instead of relying purely on
    the auto-fetched rules, e.g. to hand-encode a subreddit's karma threshold
    that isn't machine-readable from the rules text."""
    get_or_refresh_subreddit_config(subreddit)  # ensure a row exists
    with get_db() as conn:
        updates, params = [], []
        if min_karma is not None:
            updates.append("min_karma = ?"); params.append(min_karma)
        if min_age_days is not None:
            updates.append("min_age_days = ?"); params.append(min_age_days)
        if self_promo_allowed is not None:
            updates.append("self_promo_allowed = ?"); params.append(int(self_promo_allowed))
        if banned_keywords is not None:
            updates.append("banned_keywords_json = ?"); params.append(json.dumps(banned_keywords))
        if not updates:
            return
        params.append(subreddit)
        conn.execute(f"UPDATE subreddit_config SET {', '.join(updates)} WHERE subreddit = ?", params)
