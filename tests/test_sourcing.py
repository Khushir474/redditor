from __future__ import annotations

from redditor.models import ICPProfile
from redditor.reddit_client.base import RedditPost
from redditor.sourcing import _count_pain_signal_hits, _prefilter


def _icp(**overrides) -> ICPProfile:
    defaults = dict(
        name="test-icp",
        description="Non-technical B2B founders picking a CRM.",
        target_subreddits=["startups"],
        include_keywords=["CRM"],
        pain_signals=["looking for", "anyone recommend"],
        exclude_keywords=["hiring", "megathread"],
        min_relevance_score=0.6,
    )
    defaults.update(overrides)
    return ICPProfile(**defaults)


def _post(title: str, desc: str = "") -> RedditPost:
    return RedditPost(id="abc123", subreddit="startups", title=title, desc=desc, url="https://reddit.com/x")


def test_prefilter_passes_on_include_keyword_match():
    icp = _icp()
    assert _prefilter(_post("Anyone recommend a good CRM?"), icp) is True


def test_prefilter_rejects_without_include_keyword():
    icp = _icp()
    assert _prefilter(_post("Best coffee shop near me"), icp) is False


def test_prefilter_rejects_on_exclude_keyword():
    icp = _icp()
    assert _prefilter(_post("Hiring: looking for a CRM expert"), icp) is False


def test_prefilter_with_no_include_keywords_passes_everything_not_excluded():
    icp = _icp(include_keywords=[])
    assert _prefilter(_post("Best coffee shop near me"), icp) is True


def test_count_pain_signal_hits():
    icp = _icp()
    text = "I'm looking for a CRM. Does anyone recommend one?"
    assert _count_pain_signal_hits(text, icp.pain_signals) == 2


def test_count_pain_signal_hits_zero_when_no_match():
    icp = _icp()
    assert _count_pain_signal_hits("Just sharing our stack.", icp.pain_signals) == 0
