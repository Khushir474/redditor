from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RedditComment:
    id: str
    body: str
    author: str | None = None
    score: int = 0


@dataclass
class RedditPost:
    id: str
    subreddit: str
    title: str
    desc: str
    url: str
    author: str | None = None
    created_utc: float = 0.0
    top_comments: list[RedditComment] = field(default_factory=list)


class RedditClient(ABC):
    """Common interface for Reddit access, regardless of transport."""

    @abstractmethod
    def search_posts(
        self, subreddits: list[str], query: str | None = None, limit: int = 25
    ) -> list[RedditPost]:
        """Search/list recent posts across the given subreddits."""

    @abstractmethod
    def get_post_with_thread(self, post_id: str, top_n_comments: int = 10) -> RedditPost:
        """Fetch a single post with its top-level comments populated."""

    @abstractmethod
    def post_comment(self, target_id: str, body: str, is_reply_to_comment: bool = False) -> str:
        """Post a comment on a post (or reply to a comment). Returns the new comment id."""

    @abstractmethod
    def get_user_comments(self, username: str, limit: int = 100) -> list[dict]:
        """Return the authenticated (or given) user's own past comments, each dict shaped like
        an ExampleRecord input: post_title, post_desc, post_link, parent_comment, user_comment,
        subreddit."""

    @abstractmethod
    def get_subreddit_rules(self, subreddit: str) -> dict:
        """Return raw rules payload for a subreddit (from /r/{sub}/about/rules)."""

    @abstractmethod
    def get_account_karma_and_age(self) -> tuple[int, int]:
        """Return (comment_karma, account_age_days) for the authenticated account."""

    @abstractmethod
    def get_comment_status(self, comment_id: str, subreddit: str | None = None, post_id: str | None = None) -> dict:
        """Return {"removed": bool, "score": int} for a comment the account posted,
        used to detect removals/downvotes and trigger a cooldown. subreddit/post_id
        are optional context some transports (e.g. old.reddit.com scraping, which
        has no bare comment-by-id URL) need to build the comment's permalink."""
