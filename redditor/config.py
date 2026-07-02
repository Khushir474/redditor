from __future__ import annotations

from pathlib import Path

import yaml

from .models import ICPProfile


def load_icp_profile(path: str | Path) -> ICPProfile:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return ICPProfile(
        name=raw["name"],
        description=raw["description"].strip(),
        target_subreddits=raw.get("target_subreddits", []),
        include_keywords=raw.get("include_keywords", []),
        pain_signals=raw.get("pain_signals", []),
        exclude_keywords=raw.get("exclude_keywords", []),
        min_relevance_score=float(raw.get("min_relevance_score", 0.6)),
        default_mode=raw.get("default_mode", "human_approved"),
    )
