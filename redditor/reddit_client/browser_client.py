from __future__ import annotations

import logging
import os

from .base import RedditClient, RedditComment, RedditPost
from .browser_session import get_session

logger = logging.getLogger(__name__)

BASE_URL = "https://old.reddit.com"

# Pure helpers (unit-testable without a live browser) -----------------------


def strip_fullname_prefix(fullname: str, prefix: str) -> str:
    return fullname[len(prefix):] if fullname and fullname.startswith(prefix) else fullname


def post_permalink(post_id: str) -> str:
    return f"{BASE_URL}/comments/{post_id}/"


def comment_permalink(subreddit: str, post_id: str, comment_id: str) -> str:
    """Old Reddit has no bare comment-by-id URL — a comment can only be
    addressed via its parent post's permalink plus the comment id."""
    return f"{BASE_URL}/r/{subreddit}/comments/{post_id}/_/{comment_id}/"


def subreddit_new_url(subreddit: str) -> str:
    return f"{BASE_URL}/r/{subreddit}/new/"


def subreddit_search_url(subreddit: str, query: str) -> str:
    from urllib.parse import quote

    return f"{BASE_URL}/r/{subreddit}/search?q={quote(query)}&restrict_sr=on&sort=new"


def user_comments_url(username: str) -> str:
    return f"{BASE_URL}/user/{username}/comments/"


def subreddit_home_url(subreddit: str) -> str:
    return f"{BASE_URL}/r/{subreddit}/"


def user_profile_url(username: str) -> str:
    return f"{BASE_URL}/user/{username}/"


# BrowserRedditClient --------------------------------------------------------


class BrowserRedditClient(RedditClient):
    """Drives a real logged-in Reddit session (via browser_session.RedditSession)
    against old.reddit.com. Needs no Reddit API app — it automates the user's
    own account the same way a human uses the site through a browser."""

    def __init__(self) -> None:
        self.session = get_session()

    def search_posts(self, subreddits: list[str], query: str | None = None, limit: int = 25) -> list[RedditPost]:
        posts: list[RedditPost] = []
        for subreddit in subreddits:
            url = subreddit_search_url(subreddit, query) if query else subreddit_new_url(subreddit)
            page = self.session.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded")
                things = page.query_selector_all(".thing.link")[:limit]
                for thing in things:
                    fullname = thing.get_attribute("data-fullname") or ""
                    title_el = thing.query_selector("a.title")
                    if not title_el:
                        continue
                    title = title_el.inner_text().strip()
                    href = title_el.get_attribute("href") or ""
                    permalink_el = thing.query_selector("a.comments")
                    permalink = permalink_el.get_attribute("href") if permalink_el else href
                    if permalink and permalink.startswith("/"):
                        permalink = BASE_URL + permalink

                    desc = ""
                    expand_el = thing.query_selector("a.expando-button")
                    if expand_el:
                        try:
                            expand_el.click()
                            page.wait_for_timeout(300)
                            desc_el = thing.query_selector(".expando .usertext-body .md")
                            if desc_el:
                                desc = desc_el.inner_text().strip()
                        except Exception:
                            pass

                    posts.append(
                        RedditPost(
                            id=strip_fullname_prefix(fullname, "t3_"),
                            subreddit=subreddit,
                            title=title,
                            desc=desc,
                            url=permalink or href,
                        )
                    )
            finally:
                page.close()
        return posts

    def get_post_with_thread(self, post_id: str, top_n_comments: int = 10) -> RedditPost:
        page = self.session.new_page()
        try:
            page.goto(post_permalink(post_id), wait_until="domcontentloaded")

            title_el = page.query_selector("a.title") or page.query_selector("p.title a")
            title = title_el.inner_text().strip() if title_el else ""

            subreddit_el = page.query_selector('a.subreddit')
            subreddit = subreddit_el.inner_text().strip().lstrip("r/") if subreddit_el else ""

            desc_el = page.query_selector(".sitetable .usertext-body .md")
            desc = desc_el.inner_text().strip() if desc_el else ""

            comments: list[RedditComment] = []
            comment_things = page.query_selector_all(".commentarea > .sitetable > .comment")[:top_n_comments]
            for c in comment_things:
                fullname = c.get_attribute("data-fullname") or ""
                body_el = c.query_selector(".usertext-body .md")
                if not body_el:
                    continue
                author_el = c.query_selector(".author")
                score_el = c.query_selector(".score.unvoted")
                score = 0
                if score_el:
                    score_text = (score_el.get_attribute("title") or score_el.inner_text() or "0").split()[0]
                    try:
                        score = int(score_text)
                    except ValueError:
                        score = 0
                comments.append(
                    RedditComment(
                        id=strip_fullname_prefix(fullname, "t1_"),
                        body=body_el.inner_text().strip(),
                        author=author_el.inner_text().strip() if author_el else None,
                        score=score,
                    )
                )

            return RedditPost(
                id=post_id,
                subreddit=subreddit,
                title=title,
                desc=desc,
                url=post_permalink(post_id),
                top_comments=comments,
            )
        finally:
            page.close()

    def post_comment(self, target_id: str, body: str, is_reply_to_comment: bool = False) -> str:
        # target_id is a post id for top-level comments; for replies-to-comments,
        # callers pass the comment's own id and is_reply_to_comment=True. We
        # still need the parent post to reach the page — that's out of scope
        # for the lean v1 (candidate_posts always drives top-level comments).
        page = self.session.new_page()
        try:
            page.goto(post_permalink(target_id), wait_until="domcontentloaded")

            if is_reply_to_comment:
                comment_el = page.query_selector(f'[data-fullname="t1_{target_id}"]')
                reply_link = comment_el.query_selector("a.reply-button, li.reply-button a") if comment_el else None
                if reply_link:
                    reply_link.click()
                    page.wait_for_timeout(500)
                form_selector = f'[data-fullname="t1_{target_id}"] form.usertext-edit textarea'
            else:
                form_selector = "form#newcomment textarea"

            page.fill(form_selector, body)
            submit_selector = (
                f'[data-fullname="t1_{target_id}"] form.usertext-edit button[type=submit]'
                if is_reply_to_comment
                else "form#newcomment button[type=submit]"
            )
            page.click(submit_selector)
            page.wait_for_timeout(2000)

            # Newest top-level comment after posting — best-effort id extraction.
            new_comment = page.query_selector(".commentarea > .sitetable > .comment")
            fullname = new_comment.get_attribute("data-fullname") if new_comment else None
            return strip_fullname_prefix(fullname or "", "t1_")
        finally:
            page.close()

    def get_user_comments(self, username: str, limit: int = 100) -> list[dict]:
        records: list[dict] = []
        url = user_comments_url(username)
        while url and len(records) < limit:
            page = self.session.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded")
                things = page.query_selector_all(".thing.comment")
                for thing in things:
                    if len(records) >= limit:
                        break
                    body_el = thing.query_selector(".usertext-body .md")
                    title_el = thing.query_selector("a.title, a.bylink")
                    subreddit_el = thing.query_selector("a.subreddit")
                    if not body_el or not title_el:
                        continue
                    href = title_el.get_attribute("href") or ""
                    if href.startswith("/"):
                        href = BASE_URL + href
                    records.append(
                        {
                            "post_title": title_el.inner_text().strip(),
                            "post_desc": "",
                            "post_link": href,
                            "parent_comment": None,  # not available from this listing view
                            "user_comment": body_el.inner_text().strip(),
                            "subreddit": subreddit_el.inner_text().strip().lstrip("r/") if subreddit_el else None,
                        }
                    )
                next_el = page.query_selector("span.next-button a")
                url = next_el.get_attribute("href") if next_el else None
            finally:
                page.close()
        return records

    def get_subreddit_rules(self, subreddit: str) -> dict:
        page = self.session.new_page()
        try:
            page.goto(subreddit_home_url(subreddit), wait_until="domcontentloaded")
            sidebar_el = page.query_selector(".side .md")
            rules_text = sidebar_el.inner_text().strip() if sidebar_el else ""
            return {"rules": [{"short_name": "sidebar", "description": rules_text}]}
        finally:
            page.close()

    def get_account_karma_and_age(self) -> tuple[int, int]:
        from datetime import datetime, timezone

        username = os.environ.get("REDDIT_USERNAME", "")
        page = self.session.new_page()
        try:
            page.goto(user_profile_url(username), wait_until="domcontentloaded")
            karma_el = page.query_selector(".karma.comment-karma")
            karma = 0
            if karma_el:
                try:
                    karma = int((karma_el.inner_text() or "0").replace(",", "").strip())
                except ValueError:
                    karma = 0

            cake_el = page.query_selector('.cake-day, .cakeday, span[title*=":"]')
            age_days = 0
            if cake_el:
                title = cake_el.get_attribute("title") or ""
                try:
                    created = datetime.strptime(title, "%a %b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                    age_days = (datetime.now(timezone.utc) - created).days
                except ValueError:
                    age_days = 0

            return karma, age_days
        finally:
            page.close()

    def get_comment_status(self, comment_id: str, subreddit: str | None = None, post_id: str | None = None) -> dict:
        if not subreddit or not post_id:
            raise ValueError("BrowserRedditClient.get_comment_status requires subreddit and post_id")

        page = self.session.new_page()
        try:
            page.goto(comment_permalink(subreddit, post_id, comment_id), wait_until="domcontentloaded")
            comment_el = page.query_selector(f'[data-fullname="t1_{comment_id}"]')
            if not comment_el:
                return {"removed": True, "score": 0}

            body_el = comment_el.query_selector(".usertext-body .md")
            removed = body_el is None or (body_el.inner_text().strip() in ("[removed]", "[deleted]"))

            score = 0
            score_el = comment_el.query_selector(".score.unvoted")
            if score_el:
                score_text = (score_el.get_attribute("title") or score_el.inner_text() or "0").split()[0]
                try:
                    score = int(score_text)
                except ValueError:
                    score = 0

            return {"removed": removed, "score": score}
        finally:
            page.close()
