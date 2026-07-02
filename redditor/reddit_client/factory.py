from __future__ import annotations

import os

from .base import RedditClient

_client: RedditClient | None = None


def get_reddit_client(force_new: bool = False) -> RedditClient:
    """Returns the browser-session client by default — it drives the user's
    own logged-in Reddit account through old.reddit.com and needs no Reddit
    API app (Reddit's Responsible Builder Policy, effective 2026-06-05,
    removed self-serve app creation and gated API access behind an
    approval process). Set REDDIT_CLIENT_MODE=api to use the official
    PRAW/OAuth client instead, for anyone who has approved API access."""
    global _client
    if _client is not None and not force_new:
        return _client

    mode = os.environ.get("REDDIT_CLIENT_MODE", "browser")

    if mode == "api":
        from .api_client import ApiRedditClient

        _client = ApiRedditClient()
        return _client

    from .browser_client import BrowserRedditClient

    _client = BrowserRedditClient()
    return _client
