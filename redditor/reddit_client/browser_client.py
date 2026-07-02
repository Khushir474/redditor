from __future__ import annotations

from .base import RedditClient, RedditPost


class BrowserRedditClient(RedditClient):
    """Playwright-driven fallback for when the official Reddit API is unavailable
    (e.g. API app rejected, rate-limited at the app level, or creds not yet set up).

    Deliberately not implemented in v1 — the official API (ApiRedditClient) is the
    primary path and covers the full lean pipeline. This class exists so the
    interface and the factory fallback wiring are in place; fill in each method
    with Playwright page interactions when the fallback is actually needed.
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "Browser automation fallback is not implemented yet. "
            "Fix REDDIT_CLIENT_ID/SECRET (and REDDIT_USERNAME/PASSWORD if posting) "
            "to use the official API client, or implement BrowserRedditClient."
        )

    def search_posts(self, subreddits: list[str], query: str | None = None, limit: int = 25) -> list[RedditPost]:
        raise NotImplementedError

    def get_post_with_thread(self, post_id: str, top_n_comments: int = 10) -> RedditPost:
        raise NotImplementedError

    def post_comment(self, target_id: str, body: str, is_reply_to_comment: bool = False) -> str:
        raise NotImplementedError

    def get_user_comments(self, username: str, limit: int = 100) -> list[dict]:
        raise NotImplementedError

    def get_subreddit_rules(self, subreddit: str) -> dict:
        raise NotImplementedError

    def get_account_karma_and_age(self) -> tuple[int, int]:
        raise NotImplementedError

    def get_comment_status(self, comment_id: str) -> dict:
        raise NotImplementedError
