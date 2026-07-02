from __future__ import annotations

import logging
import os

from .base import RedditClient

logger = logging.getLogger(__name__)

_client: RedditClient | None = None


def get_reddit_client(force_new: bool = False) -> RedditClient:
    """Returns the official API client by default; falls back to the browser
    client only if REDDIT_CLIENT_MODE=browser is set explicitly, or if the API
    client fails to construct/authenticate (e.g. missing/bad creds)."""
    global _client
    if _client is not None and not force_new:
        return _client

    mode = os.environ.get("REDDIT_CLIENT_MODE", "api")

    if mode == "browser":
        from .browser_client import BrowserRedditClient

        _client = BrowserRedditClient()
        return _client

    from .api_client import ApiRedditClient

    try:
        _client = ApiRedditClient()
        return _client
    except Exception as exc:
        logger.warning("Official Reddit API client unavailable (%s); falling back to browser client.", exc)
        from .browser_client import BrowserRedditClient

        _client = BrowserRedditClient()
        return _client
