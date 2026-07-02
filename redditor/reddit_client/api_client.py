from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import praw
from praw.models import Comment, Submission

from .base import RedditClient, RedditComment, RedditPost


class ApiRedditClient(RedditClient):
    """Official Reddit API access via PRAW (OAuth "script" app)."""

    def __init__(self) -> None:
        missing = [
            var
            for var in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")
            if not os.environ.get(var)
        ]
        if missing:
            raise RuntimeError(f"Missing Reddit API env vars: {', '.join(missing)}")

        kwargs = dict(
            client_id=os.environ["REDDIT_CLIENT_ID"],
            client_secret=os.environ["REDDIT_CLIENT_SECRET"],
            user_agent=os.environ["REDDIT_USER_AGENT"],
        )
        # Username/password enables posting comments as that account.
        # Without them the client is read-only (fine for sourcing/dry-run).
        if os.environ.get("REDDIT_USERNAME") and os.environ.get("REDDIT_PASSWORD"):
            kwargs["username"] = os.environ["REDDIT_USERNAME"]
            kwargs["password"] = os.environ["REDDIT_PASSWORD"]

        self.reddit = praw.Reddit(**kwargs)
        # Force an auth check now so factory.py's fallback logic can catch bad creds early.
        self.reddit.user.me()

    def _submission_to_post(self, sub: Submission, top_n_comments: int = 0) -> RedditPost:
        top_comments: list[RedditComment] = []
        if top_n_comments:
            sub.comment_sort = "top"
            sub.comments.replace_more(limit=0)
            for c in sub.comments[:top_n_comments]:
                if isinstance(c, Comment):
                    top_comments.append(
                        RedditComment(
                            id=c.id,
                            body=c.body,
                            author=str(c.author) if c.author else None,
                            score=c.score,
                        )
                    )
        return RedditPost(
            id=sub.id,
            subreddit=str(sub.subreddit),
            title=sub.title,
            desc=sub.selftext or "",
            url=f"https://reddit.com{sub.permalink}",
            author=str(sub.author) if sub.author else None,
            created_utc=sub.created_utc,
            top_comments=top_comments,
        )

    def search_posts(
        self, subreddits: list[str], query: str | None = None, limit: int = 25
    ) -> list[RedditPost]:
        posts: list[RedditPost] = []
        for sub_name in subreddits:
            subreddit = self.reddit.subreddit(sub_name)
            listing = subreddit.search(query, sort="new", limit=limit) if query else subreddit.new(
                limit=limit
            )
            for sub in listing:
                posts.append(self._submission_to_post(sub))
        return posts

    def get_post_with_thread(self, post_id: str, top_n_comments: int = 10) -> RedditPost:
        sub = self.reddit.submission(id=post_id)
        return self._submission_to_post(sub, top_n_comments=top_n_comments)

    def post_comment(self, target_id: str, body: str, is_reply_to_comment: bool = False) -> str:
        if is_reply_to_comment:
            target = self.reddit.comment(id=target_id)
        else:
            target = self.reddit.submission(id=target_id)
        comment = target.reply(body)
        return comment.id

    def get_user_comments(self, username: str, limit: int = 100) -> list[dict]:
        redditor = self.reddit.redditor(username)
        records = []
        for c in redditor.comments.new(limit=limit):
            try:
                submission = c.submission
                parent_comment_body = None
                if c.parent_id.startswith("t1_"):
                    parent = c.parent()
                    if isinstance(parent, Comment):
                        parent_comment_body = parent.body
                records.append(
                    {
                        "post_title": submission.title,
                        "post_desc": submission.selftext or "",
                        "post_link": f"https://reddit.com{submission.permalink}",
                        "parent_comment": parent_comment_body,
                        "user_comment": c.body,
                        "subreddit": str(c.subreddit),
                    }
                )
            except Exception:
                # Deleted post/comment or API hiccup — skip rather than fail the whole sync.
                continue
            time.sleep(0.1)  # gentle on the API even for read-only history sync
        return records

    def get_subreddit_rules(self, subreddit: str) -> dict:
        rules = list(self.reddit.subreddit(subreddit).rules)
        return {"rules": [{"short_name": r.short_name, "description": r.description} for r in rules]}

    def get_account_karma_and_age(self) -> tuple[int, int]:
        me = self.reddit.user.me()
        age_days = (datetime.now(timezone.utc).timestamp() - me.created_utc) / 86400
        return me.comment_karma, int(age_days)

    def get_comment_status(self, comment_id: str, subreddit: str | None = None, post_id: str | None = None) -> dict:
        comment = self.reddit.comment(id=comment_id)
        comment.refresh()
        removed = bool(getattr(comment, "removed", False) or getattr(comment, "banned_by", None))
        return {"removed": removed, "score": comment.score}
