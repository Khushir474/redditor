from __future__ import annotations

import re
import sqlite3

from .db import get_db, log_activity
from .embeddings.base import cosine_similarity
from .embeddings.factory import get_embedding_client
from .leads import evaluate_lead
from .models import CandidatePost, ICPProfile
from .reddit_client.base import RedditPost
from .reddit_client.factory import get_reddit_client

PAIN_SIGNAL_BOOST = 0.1
MAX_PAIN_BOOST = 0.3


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _count_pain_signal_hits(text: str, pain_signals: list[str]) -> int:
    text_lower = text.lower()
    return sum(1 for signal in pain_signals if signal.lower() in text_lower)


def _prefilter(post: RedditPost, icp: ICPProfile) -> bool:
    text = f"{post.title} {post.desc}"
    if icp.exclude_keywords and _matches_keywords(text, icp.exclude_keywords):
        return False
    if icp.include_keywords and not _matches_keywords(text, icp.include_keywords):
        return False
    return True


def source_candidates(icp: ICPProfile, limit_per_subreddit: int = 25) -> list[CandidatePost]:
    """Search target subreddits, filter/score against the ICP, persist new
    candidates (skipping ones already sourced), and tag leads."""
    reddit = get_reddit_client()
    embedder = get_embedding_client()

    posts = reddit.search_posts(icp.target_subreddits, limit=limit_per_subreddit)
    prefiltered = [p for p in posts if _prefilter(p, icp)]
    if not prefiltered:
        return []

    icp_vec = embedder.embed_one(icp.description)
    post_vecs = embedder.embed([f"{p.title}\n{p.desc}" for p in prefiltered])

    new_candidates: list[CandidatePost] = []
    with get_db() as conn:
        for post, post_vec in zip(prefiltered, post_vecs):
            if _already_sourced(conn, post.id):
                continue

            semantic_score = cosine_similarity(icp_vec, post_vec)
            pain_hits = _count_pain_signal_hits(f"{post.title} {post.desc}", icp.pain_signals)
            boost = min(pain_hits * PAIN_SIGNAL_BOOST, MAX_PAIN_BOOST)
            relevance_score = min(semantic_score + boost, 1.0)

            if relevance_score < icp.min_relevance_score:
                continue

            candidate = CandidatePost(
                subreddit=post.subreddit,
                title=post.title,
                desc=post.desc,
                url=post.url,
                icp_name=icp.name,
                relevance_score=relevance_score,
                reddit_post_id=post.id,
            )
            candidate.id = _insert_candidate(conn, candidate)
            new_candidates.append(candidate)

            lead_snippet = evaluate_lead(post, icp, relevance_score)
            if lead_snippet:
                _mark_lead(conn, candidate, lead_snippet, icp.name)

            log_activity(conn, "sourced", subreddit=post.subreddit, ref_id=post.id)

    return new_candidates


def _already_sourced(conn: sqlite3.Connection, reddit_post_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM candidate_posts WHERE reddit_post_id = ?", (reddit_post_id,)
    ).fetchone()
    return row is not None


def _insert_candidate(conn: sqlite3.Connection, c: CandidatePost) -> int:
    cur = conn.execute(
        "INSERT INTO candidate_posts "
        "(subreddit, title, desc, url, reddit_post_id, icp_name, relevance_score, "
        " is_lead, status, sourced_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            c.subreddit,
            c.title,
            c.desc,
            c.url,
            c.reddit_post_id,
            c.icp_name,
            c.relevance_score,
            int(c.is_lead),
            c.status,
            c.sourced_at,
        ),
    )
    return cur.lastrowid


def _mark_lead(conn: sqlite3.Connection, candidate: CandidatePost, snippet: str, icp_name: str) -> None:
    conn.execute(
        "UPDATE candidate_posts SET is_lead = 1 WHERE id = ?", (candidate.id,)
    )
    conn.execute(
        "INSERT INTO leads (candidate_post_id, signal_snippet, icp_name, flagged_at) "
        "VALUES (?, ?, ?, datetime('now'))",
        (candidate.id, snippet, icp_name),
    )
