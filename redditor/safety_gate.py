from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime

from .db import get_db
from .embeddings.base import blob_to_vector, cosine_similarity
from .embeddings.factory import get_embedding_client
from .models import CandidatePost, Draft
from .reddit_client.factory import get_reddit_client
from .subreddit_rules import get_or_refresh_subreddit_config

SIMILARITY_REJECT_THRESHOLD = 0.92
DEFAULT_DAILY_QUOTA_PER_SUBREDDIT = 3
MIN_COMMENT_LEN = 20
MAX_COMMENT_LEN = 600
GENERIC_OPENERS = [
    r"^great post",
    r"^this is so true",
    r"^totally agree",
    r"^love this",
    r"^nice[!.]",
    r"^i agree",
]
URL_RE = re.compile(r"https?://\S+")


def run_gate(draft: Draft, candidate: CandidatePost, mode: str, account: str = "default") -> dict:
    """Runs every anti-ban/quality check regardless of mode. Persists the
    result and the resulting status (pending_review / approved / held) onto
    the draft row. Returns the gate_result dict."""
    reasons: list[str] = []

    similarity_score, similarity_ok = _check_similarity(draft.comment_body)
    if not similarity_ok:
        reasons.append(f"too similar to a recent comment (score={similarity_score:.2f})")

    if _has_duplicate_post(candidate.id, exclude_draft_id=draft.id):
        reasons.append("already posted a comment on this exact post")

    rule_ok, rule_reasons = _check_subreddit_rules(candidate.subreddit, draft.comment_body)
    reasons.extend(rule_reasons)
    if not rule_ok:
        pass  # reasons already captured

    quota_ok, quota_reason = _check_quota_and_cooldown(account, candidate.subreddit)
    if not quota_ok:
        reasons.append(quota_reason)

    checklist_ok, checklist_reasons = _heuristic_checklist(draft.comment_body)
    reasons.extend(checklist_reasons)

    passed = not reasons

    if passed:
        status = "approved" if mode == "auto" else "pending_review"
    else:
        status = "held"

    gate_result = {"passed": passed, "reasons": reasons}

    with get_db() as conn:
        conn.execute(
            "UPDATE drafts SET similarity_score = ?, gate_result_json = ?, status = ? WHERE id = ?",
            (similarity_score, json.dumps(gate_result), status, draft.id),
        )

    draft.similarity_score = similarity_score
    draft.gate_result = gate_result
    draft.status = status
    return gate_result


def _check_similarity(comment_body: str) -> tuple[float, bool]:
    embedder = get_embedding_client()
    comment_vec = embedder.embed_one(comment_body)

    with get_db() as conn:
        rows = conn.execute("SELECT embedding FROM examples WHERE embedding IS NOT NULL").fetchall()

    if not rows:
        return 0.0, True

    max_sim = max(cosine_similarity(comment_vec, blob_to_vector(r["embedding"])) for r in rows)
    return max_sim, max_sim < SIMILARITY_REJECT_THRESHOLD


def _has_duplicate_post(candidate_post_id: int, exclude_draft_id: int | None) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM drafts WHERE candidate_post_id = ? AND status = 'posted' AND id != ?",
            (candidate_post_id, exclude_draft_id or -1),
        ).fetchone()
    return row is not None


def _check_subreddit_rules(subreddit: str, comment_body: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    config = get_or_refresh_subreddit_config(subreddit)

    has_link = bool(URL_RE.search(comment_body))
    if has_link and not config.self_promo_allowed:
        reasons.append(f"r/{subreddit} does not allow self-promo/links and comment contains a URL")

    lower_body = comment_body.lower()
    for kw in config.banned_keywords:
        if kw.lower() in lower_body:
            reasons.append(f"comment contains banned keyword for r/{subreddit}: {kw!r}")

    try:
        reddit = get_reddit_client()
        karma, age_days = reddit.get_account_karma_and_age()
        if karma < config.min_karma:
            reasons.append(f"account karma {karma} below r/{subreddit} minimum {config.min_karma}")
        if age_days < config.min_age_days:
            reasons.append(f"account age {age_days}d below r/{subreddit} minimum {config.min_age_days}d")
    except Exception:
        pass  # can't verify — don't hard-block on an infra hiccup, rely on other checks

    return not reasons, reasons


def _check_quota_and_cooldown(account: str, subreddit: str) -> tuple[bool, str | None]:
    with get_db() as conn:
        state = _get_or_init_account_state(conn, account)

        if state["cooldown_until"]:
            cooldown_until = datetime.fromisoformat(state["cooldown_until"])
            if datetime.utcnow() < cooldown_until:
                return False, f"account is in cooldown until {state['cooldown_until']}"

        daily_counts = json.loads(state["daily_counts_json"])
        count_today = daily_counts.get(subreddit, 0)
        if count_today >= DEFAULT_DAILY_QUOTA_PER_SUBREDDIT:
            return False, f"daily quota reached for r/{subreddit} ({count_today}/{DEFAULT_DAILY_QUOTA_PER_SUBREDDIT})"

    return True, None


def _get_or_init_account_state(conn: sqlite3.Connection, account: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM account_state WHERE account = ?", (account,)).fetchone()
    today = date.today().isoformat()

    if row is None:
        conn.execute(
            "INSERT INTO account_state (account, daily_counts_json, daily_counts_date) VALUES (?, '{}', ?)",
            (account, today),
        )
        return conn.execute("SELECT * FROM account_state WHERE account = ?", (account,)).fetchone()

    if row["daily_counts_date"] != today:
        conn.execute(
            "UPDATE account_state SET daily_counts_json = '{}', daily_counts_date = ? WHERE account = ?",
            (today, account),
        )
        return conn.execute("SELECT * FROM account_state WHERE account = ?", (account,)).fetchone()

    return row


def record_posted_comment(account: str, subreddit: str) -> None:
    """Called by scheduler.py after a successful post to advance the daily quota."""
    with get_db() as conn:
        state = _get_or_init_account_state(conn, account)
        daily_counts = json.loads(state["daily_counts_json"])
        daily_counts[subreddit] = daily_counts.get(subreddit, 0) + 1
        conn.execute(
            "UPDATE account_state SET daily_counts_json = ?, last_comment_at = ? WHERE account = ?",
            (json.dumps(daily_counts), datetime.utcnow().isoformat(), account),
        )


def trigger_cooldown(account: str, until: datetime) -> None:
    with get_db() as conn:
        _get_or_init_account_state(conn, account)
        conn.execute(
            "UPDATE account_state SET cooldown_until = ? WHERE account = ?",
            (until.isoformat(), account),
        )


# Public alias — scheduler.py re-checks quota/cooldown right before posting,
# since state may have shifted since the draft was gated.
check_quota_and_cooldown = _check_quota_and_cooldown


def _heuristic_checklist(comment_body: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    length = len(comment_body.strip())
    if length < MIN_COMMENT_LEN:
        reasons.append(f"comment too short ({length} chars, min {MIN_COMMENT_LEN})")
    if length > MAX_COMMENT_LEN:
        reasons.append(f"comment too long ({length} chars, max {MAX_COMMENT_LEN})")

    lower_body = comment_body.strip().lower()
    for pattern in GENERIC_OPENERS:
        if re.match(pattern, lower_body):
            reasons.append(f"generic opener detected ({pattern!r})")
            break

    return not reasons, reasons
