from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Mode = Literal["human_approved", "auto"]
DraftStatus = Literal["pending_review", "approved", "rejected", "posted", "held"]
CandidateStatus = Literal["sourced", "analyzed", "drafted", "done"]
Intent = Literal[
    "problem_solving", "experience_sharing", "hypothetical", "hiring_announcement"
]
ExampleSource = Literal["reddit_history", "csv_import", "posted"]


@dataclass
class ICPProfile:
    name: str
    description: str
    target_subreddits: list[str]
    include_keywords: list[str] = field(default_factory=list)
    pain_signals: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    min_relevance_score: float = 0.6
    default_mode: Mode = "human_approved"


@dataclass
class ExampleRecord:
    source: ExampleSource
    post_title: str
    post_desc: str
    post_link: str
    user_comment: str
    parent_comment: str | None = None
    subreddit: str | None = None
    embedding: bytes | None = None
    id: int | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class CandidatePost:
    subreddit: str
    title: str
    desc: str
    url: str
    icp_name: str
    relevance_score: float
    reddit_post_id: str
    intent: Intent | None = None
    thread_tone: str | None = None
    referenced_link: str | None = None
    is_lead: bool = False
    status: CandidateStatus = "sourced"
    id: int | None = None
    sourced_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Draft:
    candidate_post_id: int
    comment_body: str
    similarity_score: float
    self_checklist: dict
    gate_result: dict
    mode_at_creation: Mode
    status: DraftStatus = "pending_review"
    id: int | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    posted_at: str | None = None
    reddit_comment_id: str | None = None


@dataclass
class Lead:
    candidate_post_id: int
    signal_snippet: str
    icp_name: str
    id: int | None = None
    flagged_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class SubredditConfig:
    subreddit: str
    min_karma: int = 0
    min_age_days: int = 0
    self_promo_allowed: bool = False
    banned_keywords: list[str] = field(default_factory=list)
    rules_text: str = ""
    last_refreshed: str | None = None


@dataclass
class AccountState:
    account: str
    daily_counts: dict[str, int] = field(default_factory=dict)  # subreddit -> count today
    daily_counts_date: str = field(default_factory=lambda: datetime.utcnow().date().isoformat())
    cooldown_until: str | None = None
    last_comment_at: str | None = None
