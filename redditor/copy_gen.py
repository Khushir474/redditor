from __future__ import annotations

import json
import sqlite3

from .db import get_db
from .example_store import retrieve_similar
from .llm.factory import get_llm_client
from .models import CandidatePost, Draft, Mode


def generate_and_persist_draft(candidate: CandidatePost, analysis: dict, mode: Mode, k_examples: int = 5) -> Draft:
    """One LLM call: draft the comment using retrieved examples (voice + depth)
    and the post analysis, with the model self-grading a quality checklist in
    the same response. Persists as status='pending_gate' — safety_gate.py
    decides the real status next."""
    llm = get_llm_client()
    examples = retrieve_similar(candidate.title, candidate.desc, k=k_examples)

    result = llm.draft_comment(
        post_title=candidate.title,
        post_desc=candidate.desc,
        analysis={"intent": analysis.get("intent"), "thread_tone": analysis.get("thread_tone")},
        examples=[
            {
                "post_title": e["post_title"],
                "post_desc": e["post_desc"],
                "parent_comment": e["parent_comment"],
                "user_comment": e["user_comment"],
            }
            for e in examples
        ],
        ground_truth_context=analysis.get("ground_truth_context"),
    )

    draft = Draft(
        candidate_post_id=candidate.id,
        comment_body=result["comment"],
        similarity_score=0.0,  # filled in by safety_gate.run_gate
        self_checklist=result.get("self_checklist", {}),
        gate_result={},
        mode_at_creation=mode,
        status="pending_review",  # placeholder; safety_gate.run_gate sets the real status
    )
    with get_db() as conn:
        draft.id = _insert_draft(conn, draft)
        conn.execute("UPDATE candidate_posts SET status = 'drafted' WHERE id = ?", (candidate.id,))
    return draft


def _insert_draft(conn: sqlite3.Connection, d: Draft) -> int:
    cur = conn.execute(
        "INSERT INTO drafts (candidate_post_id, comment_body, similarity_score, self_checklist_json, "
        "gate_result_json, mode_at_creation, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            d.candidate_post_id,
            d.comment_body,
            d.similarity_score,
            json.dumps(d.self_checklist),
            json.dumps(d.gate_result),
            d.mode_at_creation,
            d.status,
            d.created_at,
        ),
    )
    return cur.lastrowid
