from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import numpy as np

from .db import get_db
from .embeddings.base import blob_to_vector, cosine_similarity, vector_to_blob
from .embeddings.factory import get_embedding_client
from .reddit_client.factory import get_reddit_client


def _example_embedding_text(post_title: str, post_desc: str, user_comment: str) -> str:
    return f"POST: {post_title}\n{post_desc}\nCOMMENT: {user_comment}"


def _insert_example(conn: sqlite3.Connection, source: str, record: dict, embedding: np.ndarray) -> int:
    cur = conn.execute(
        "INSERT INTO examples (source, post_title, post_desc, post_link, parent_comment, "
        "user_comment, subreddit, embedding, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (
            source,
            record["post_title"],
            record.get("post_desc", ""),
            record.get("post_link", ""),
            record.get("parent_comment"),
            record["user_comment"],
            record.get("subreddit"),
            vector_to_blob(embedding),
        ),
    )
    return cur.lastrowid


def sync_reddit_history(username: str, limit: int = 200) -> int:
    """Pulls the user's own past comments via the Reddit API and adds new ones
    (by post_link + user_comment) to the example store."""
    reddit = get_reddit_client()
    embedder = get_embedding_client()

    records = reddit.get_user_comments(username, limit=limit)
    if not records:
        return 0

    inserted = 0
    with get_db() as conn:
        for record in records:
            exists = conn.execute(
                "SELECT 1 FROM examples WHERE post_link = ? AND user_comment = ?",
                (record["post_link"], record["user_comment"]),
            ).fetchone()
            if exists:
                continue
            text = _example_embedding_text(record["post_title"], record.get("post_desc", ""), record["user_comment"])
            embedding = embedder.embed_one(text)
            _insert_example(conn, "reddit_history", record, embedding)
            inserted += 1
    return inserted


def import_csv(path: str | Path) -> int:
    """Imports a CSV with columns: post_title, post_desc, post_link, user_comment,
    parent_comment (optional, blank if replying to the post itself), subreddit (optional)."""
    embedder = get_embedding_client()
    inserted = 0
    with open(path, newline="", encoding="utf-8") as f, get_db() as conn:
        reader = csv.DictReader(f)
        for row in reader:
            record = {
                "post_title": row["post_title"],
                "post_desc": row.get("post_desc", ""),
                "post_link": row.get("post_link", ""),
                "parent_comment": row.get("parent_comment") or None,
                "user_comment": row["user_comment"],
                "subreddit": row.get("subreddit") or None,
            }
            text = _example_embedding_text(record["post_title"], record["post_desc"], record["user_comment"])
            embedding = embedder.embed_one(text)
            _insert_example(conn, "csv_import", record, embedding)
            inserted += 1
    return inserted


def append_posted_example(post_title: str, post_desc: str, post_link: str, user_comment: str,
                           subreddit: str | None = None, parent_comment: str | None = None) -> None:
    """Feeds a comment the system actually posted back into the example store,
    so the voice profile compounds over time."""
    embedder = get_embedding_client()
    record = {
        "post_title": post_title,
        "post_desc": post_desc,
        "post_link": post_link,
        "parent_comment": parent_comment,
        "user_comment": user_comment,
        "subreddit": subreddit,
    }
    text = _example_embedding_text(post_title, post_desc, user_comment)
    embedding = embedder.embed_one(text)
    with get_db() as conn:
        _insert_example(conn, "posted", record, embedding)


def retrieve_similar(query_title: str, query_desc: str, k: int = 5) -> list[dict]:
    """Embeds the candidate post and returns the top-k most similar (post, comment)
    examples from the store, shaped for the drafting prompt."""
    embedder = get_embedding_client()
    query_vec = embedder.embed_one(f"POST: {query_title}\n{query_desc}")

    with get_db() as conn:
        rows = conn.execute(
            "SELECT post_title, post_desc, parent_comment, user_comment, embedding FROM examples"
        ).fetchall()

    if not rows:
        return []

    scored = []
    for row in rows:
        vec = blob_to_vector(row["embedding"])
        score = cosine_similarity(query_vec, vec)
        scored.append((score, row))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = scored[:k]

    return [
        {
            "post_title": row["post_title"],
            "post_desc": row["post_desc"],
            "parent_comment": row["parent_comment"],
            "user_comment": row["user_comment"],
            "similarity": score,
        }
        for score, row in top
    ]
