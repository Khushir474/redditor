from __future__ import annotations

from .models import ICPProfile
from .reddit_client.base import RedditPost

# A candidate is worth flagging as a lead when it clears both a stronger
# relevance bar than the general commenting threshold AND actually contains
# a pain-signal phrase (not just topical keywords).
LEAD_RELEVANCE_MARGIN = 0.15


def evaluate_lead(post: RedditPost, icp: ICPProfile, relevance_score: float) -> str | None:
    """Returns a snippet to log if this candidate looks like a lead, else None."""
    if relevance_score < icp.min_relevance_score + LEAD_RELEVANCE_MARGIN:
        return None

    text = f"{post.title} {post.desc}"
    text_lower = text.lower()
    for signal in icp.pain_signals:
        idx = text_lower.find(signal.lower())
        if idx != -1:
            start = max(0, idx - 40)
            end = min(len(text), idx + len(signal) + 40)
            return text[start:end].strip()
    return None
