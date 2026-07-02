from __future__ import annotations

from redditor.reddit_client.browser_client import (
    comment_permalink,
    post_permalink,
    strip_fullname_prefix,
    subreddit_new_url,
    subreddit_search_url,
    user_comments_url,
)


def test_strip_fullname_prefix_removes_known_prefix():
    assert strip_fullname_prefix("t3_abc123", "t3_") == "abc123"
    assert strip_fullname_prefix("t1_xyz789", "t1_") == "xyz789"


def test_strip_fullname_prefix_leaves_unmatched_prefix_untouched():
    assert strip_fullname_prefix("abc123", "t3_") == "abc123"


def test_strip_fullname_prefix_handles_empty_string():
    assert strip_fullname_prefix("", "t3_") == ""


def test_post_permalink_shape():
    assert post_permalink("abc123") == "https://old.reddit.com/comments/abc123/"


def test_comment_permalink_shape():
    url = comment_permalink("startups", "abc123", "def456")
    assert url == "https://old.reddit.com/r/startups/comments/abc123/_/def456/"


def test_subreddit_new_url_shape():
    assert subreddit_new_url("startups") == "https://old.reddit.com/r/startups/new/"


def test_subreddit_search_url_encodes_query():
    url = subreddit_search_url("startups", "first sales hire")
    assert url.startswith("https://old.reddit.com/r/startups/search?q=")
    assert "restrict_sr=on" in url
    assert "sort=new" in url
    assert "first%20sales%20hire" in url or "first+sales+hire" in url


def test_user_comments_url_shape():
    assert user_comments_url("some_user") == "https://old.reddit.com/user/some_user/comments/"
