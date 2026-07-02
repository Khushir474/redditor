from __future__ import annotations

import re
import sqlite3

import httpx

from .db import get_db
from .llm.factory import get_llm_client
from .models import CandidatePost
from .reddit_client.factory import get_reddit_client

URL_RE = re.compile(r"https?://\S+")
FEEDBACK_HINTS = ("feedback", "thoughts?", "review", "critique", "roast", "check out", "look at")


def _extract_referenced_link(text: str) -> str | None:
    match = URL_RE.search(text)
    return match.group(0).rstrip(").,!?") if match else None


def _wants_feedback(text: str) -> bool:
    text_lower = text.lower()
    return any(hint in text_lower for hint in FEEDBACK_HINTS)


def _fetch_ground_truth(url: str, max_chars: int = 4000) -> str | None:
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True, headers={"User-Agent": "redditor/0.1"})
        resp.raise_for_status()
        # Lean text extraction: strip tags crudely rather than pulling in a parser dependency.
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars] or None
    except Exception:
        return None


def analyze_candidate(candidate: CandidatePost) -> dict:
    """Runs intent/thread-tone analysis and, if the post links something and asks
    for feedback, fetches ground-truth page content. Persists intent/thread_tone/
    referenced_link/status to the DB. Returns the full analysis dict including
    ground_truth_context (not persisted — passed straight into drafting)."""
    reddit = get_reddit_client()
    llm = get_llm_client()

    post = reddit.get_post_with_thread(candidate.reddit_post_id, top_n_comments=10)
    thread_comments = [c.body for c in post.top_comments]

    analysis = llm.analyze_post(
        post_title=post.title, post_desc=post.desc, thread_comments=thread_comments, subreddit=post.subreddit
    )

    full_text = f"{post.title} {post.desc}"
    referenced_link = _extract_referenced_link(full_text)
    ground_truth_context = None
    if referenced_link and _wants_feedback(full_text):
        ground_truth_context = _fetch_ground_truth(referenced_link)

    with get_db() as conn:
        _persist_analysis(conn, candidate, analysis, referenced_link)

    return {
        "intent": analysis.get("intent"),
        "thread_tone": analysis.get("thread_tone"),
        "referenced_link": referenced_link,
        "ground_truth_context": ground_truth_context,
    }


def _persist_analysis(conn: sqlite3.Connection, candidate: CandidatePost, analysis: dict, referenced_link: str | None) -> None:
    conn.execute(
        "UPDATE candidate_posts SET intent = ?, thread_tone = ?, referenced_link = ?, status = 'analyzed' "
        "WHERE id = ?",
        (analysis.get("intent"), analysis.get("thread_tone"), referenced_link, candidate.id),
    )
