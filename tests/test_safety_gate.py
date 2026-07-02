from __future__ import annotations

from redditor import safety_gate
from redditor.db import get_db


def test_heuristic_checklist_flags_short_comment():
    ok, reasons = safety_gate._heuristic_checklist("nice")
    assert ok is False
    assert any("too short" in r for r in reasons)


def test_heuristic_checklist_flags_generic_opener():
    ok, reasons = safety_gate._heuristic_checklist(
        "Great post! I really think this is a solid approach to the problem you described here."
    )
    assert ok is False
    assert any("generic opener" in r for r in reasons)


def test_heuristic_checklist_passes_reasonable_comment():
    ok, reasons = safety_gate._heuristic_checklist(
        "We ran into the same thing at 5 people — ended up building a tiny Airtable base "
        "before ever touching a real CRM. Worked until we had a dedicated sales hire."
    )
    assert ok is True
    assert reasons == []


def test_quota_allows_under_threshold():
    ok, reason = safety_gate.check_quota_and_cooldown("test-account", "startups")
    assert ok is True
    assert reason is None


def test_quota_blocks_after_daily_limit():
    for _ in range(safety_gate.DEFAULT_DAILY_QUOTA_PER_SUBREDDIT):
        safety_gate.record_posted_comment("test-account", "startups")

    ok, reason = safety_gate.check_quota_and_cooldown("test-account", "startups")
    assert ok is False
    assert "daily quota" in reason


def test_quota_is_per_subreddit():
    for _ in range(safety_gate.DEFAULT_DAILY_QUOTA_PER_SUBREDDIT):
        safety_gate.record_posted_comment("test-account", "startups")

    ok, _ = safety_gate.check_quota_and_cooldown("test-account", "SaaS")
    assert ok is True


def test_has_duplicate_post_true_when_already_posted():
    with get_db() as conn:
        conn.execute(
            "INSERT INTO candidate_posts (subreddit, title, desc, url, reddit_post_id, icp_name, "
            "relevance_score, status, sourced_at) VALUES ('startups', 't', '', 'u', 'p1', 'icp', 0.8, "
            "'drafted', datetime('now'))"
        )
        candidate_id = conn.execute("SELECT id FROM candidate_posts WHERE reddit_post_id = 'p1'").fetchone()["id"]
        conn.execute(
            "INSERT INTO drafts (candidate_post_id, comment_body, mode_at_creation, status, created_at) "
            "VALUES (?, 'already posted this one', 'human_approved', 'posted', datetime('now'))",
            (candidate_id,),
        )

    assert safety_gate._has_duplicate_post(candidate_id, exclude_draft_id=None) is True


def test_similarity_check_flags_near_identical_comment(fake_embedder, monkeypatch):
    # Force the fake embedder to return the *same* vector for both texts,
    # simulating a near-duplicate comment against prior history.
    import numpy as np

    monkeypatch.setattr(fake_embedder, "embed", lambda texts: [np.ones(16, dtype=np.float32) for _ in texts])

    with get_db() as conn:
        conn.execute(
            "INSERT INTO examples (source, post_title, post_desc, post_link, user_comment, embedding, created_at) "
            "VALUES ('posted', 't', '', 'u', 'prior comment', ?, datetime('now'))",
            (np.ones(16, dtype=np.float32).tobytes(),),
        )

    score, ok = safety_gate._check_similarity("this is effectively the same comment text")
    assert ok is False
    assert score >= safety_gate.SIMILARITY_REJECT_THRESHOLD
