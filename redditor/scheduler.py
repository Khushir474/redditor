from __future__ import annotations

import logging
import random
import sqlite3
import time
from datetime import datetime, timedelta

from .db import get_db, log_activity
from .example_store import append_posted_example
from .reddit_client.factory import get_reddit_client
from .safety_gate import check_quota_and_cooldown, record_posted_comment, trigger_cooldown

logger = logging.getLogger(__name__)

JITTER_RANGE_SECONDS = (300, 900)  # 5-15 min between posts
REMOVAL_COOLDOWN_HOURS = 24
REMOVAL_RATE_THRESHOLD = 0.5  # if >=50% of recent posts got removed/tanked, cool down
DOWNVOTE_SCORE_THRESHOLD = -1


def dispatch(account: str = "default", max_to_post: int | None = None, dry_run: bool = False) -> list[dict]:
    """Posts every 'approved' draft, respecting per-subreddit daily quota
    (re-checked at post time) and randomized jitter between posts."""
    reddit = get_reddit_client()
    results: list[dict] = []

    approved = _fetch_approved_drafts(limit=max_to_post)
    for i, row in enumerate(approved):
        if i > 0:
            wait = random.randint(*JITTER_RANGE_SECONDS)
            logger.info("Waiting %ss before next comment (anti-ban pacing)...", wait)
            if not dry_run:
                time.sleep(wait)

        quota_ok, quota_reason = check_quota_and_cooldown(account, row["subreddit"])
        if not quota_ok:
            logger.info("Skipping draft %s: %s", row["id"], quota_reason)
            continue

        if dry_run:
            results.append({"draft_id": row["id"], "status": "would_post", "body": row["comment_body"]})
            continue

        try:
            comment_id = reddit.post_comment(row["reddit_post_id"], row["comment_body"])
        except Exception as exc:
            logger.warning("Failed to post draft %s: %s", row["id"], exc)
            with get_db() as conn:
                log_activity(conn, "post_failed", subreddit=row["subreddit"], ref_id=str(row["id"]), outcome=str(exc))
            continue

        _mark_posted(row["id"], comment_id)
        record_posted_comment(account, row["subreddit"])
        append_posted_example(
            post_title=row["title"], post_desc=row["desc"], post_link=row["url"], user_comment=row["comment_body"],
            subreddit=row["subreddit"],
        )
        with get_db() as conn:
            log_activity(conn, "posted", subreddit=row["subreddit"], ref_id=comment_id)
        results.append({"draft_id": row["id"], "status": "posted", "reddit_comment_id": comment_id})

    return results


def _fetch_approved_drafts(limit: int | None = None) -> list[sqlite3.Row]:
    query = (
        "SELECT d.id, d.comment_body, c.subreddit, c.reddit_post_id, c.title, c.desc, c.url "
        "FROM drafts d JOIN candidate_posts c ON d.candidate_post_id = c.id "
        "WHERE d.status = 'approved' ORDER BY d.created_at ASC"
    )
    if limit:
        query += f" LIMIT {int(limit)}"
    with get_db() as conn:
        return conn.execute(query).fetchall()


def _mark_posted(draft_id: int, comment_id: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE drafts SET status = 'posted', posted_at = ?, reddit_comment_id = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), comment_id, draft_id),
        )


def check_for_removals(account: str = "default", lookback_hours: int = REMOVAL_COOLDOWN_HOURS) -> dict:
    """Checks recently-posted comments for removal/heavy downvotes; if the
    rate is too high, triggers a cooldown so the pacing backs off rather
    than keep posting into a pattern that's already getting flagged."""
    reddit = get_reddit_client()
    cutoff = (datetime.utcnow() - timedelta(hours=lookback_hours)).isoformat()

    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, reddit_comment_id, subreddit FROM drafts d "
            "JOIN candidate_posts c ON d.candidate_post_id = c.id "
            "WHERE d.status = 'posted' AND d.posted_at >= ? AND d.reddit_comment_id IS NOT NULL",
            (cutoff,),
        ).fetchall()

    if not rows:
        return {"checked": 0, "flagged": 0, "cooldown_triggered": False}

    flagged = 0
    for row in rows:
        try:
            status = reddit.get_comment_status(row["reddit_comment_id"])
            if status["removed"] or status["score"] <= DOWNVOTE_SCORE_THRESHOLD:
                flagged += 1
        except Exception:
            continue

    rate = flagged / len(rows)
    cooldown_triggered = rate >= REMOVAL_RATE_THRESHOLD
    if cooldown_triggered:
        until = datetime.utcnow() + timedelta(hours=lookback_hours)
        trigger_cooldown(account, until)
        logger.warning("Removal/downvote rate %.0f%% — cooling down account until %s", rate * 100, until)

    return {"checked": len(rows), "flagged": flagged, "cooldown_triggered": cooldown_triggered}
