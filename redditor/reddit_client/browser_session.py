from __future__ import annotations

import logging
import os
import random
import time
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

logger = logging.getLogger(__name__)

LOGIN_URL = "https://old.reddit.com/login"
HOME_URL = "https://old.reddit.com"


def _session_path() -> Path:
    return Path(os.environ.get("REDDIT_SESSION_PATH", "data/reddit_session.json"))


def polite_delay(min_s: float = 1.0, max_s: float = 3.0) -> None:
    """Small randomized delay before each navigation — read traffic needs its
    own pacing on top of the comment scheduler's posting jitter, since this
    transport is scrape-shaped."""
    time.sleep(random.uniform(min_s, max_s))


class RedditSession:
    """Owns a single Playwright browser + logged-in context for the process
    lifetime. First-ever login (or a stale/expired session) runs a visible
    browser so the operator can clear a captcha or type a 2FA code; every
    run after that reuses the saved storage_state headless."""

    def __init__(self) -> None:
        self._pw = sync_playwright().start()
        self._browser: Browser = self._pw.chromium.launch(headless=True)
        self._context: BrowserContext = self._acquire_context()

    def _acquire_context(self) -> BrowserContext:
        session_path = _session_path()
        if session_path.exists():
            context = self._browser.new_context(storage_state=str(session_path))
            if self._is_logged_in(context):
                return context
            logger.warning("Saved Reddit session looks stale; re-authenticating.")
            context.close()
            session_path.unlink(missing_ok=True)

        return self._login_and_create_context()

    def _is_logged_in(self, context: BrowserContext) -> bool:
        page = context.new_page()
        try:
            page.goto(HOME_URL, wait_until="domcontentloaded")
            return page.query_selector('a[href*="/logout"]') is not None
        finally:
            page.close()

    def _login_and_create_context(self) -> BrowserContext:
        username = os.environ.get("REDDIT_USERNAME")
        password = os.environ.get("REDDIT_PASSWORD")
        if not username or not password:
            raise RuntimeError(
                "REDDIT_USERNAME/REDDIT_PASSWORD are required for the browser client's first login."
            )

        visible_browser = self._pw.chromium.launch(headless=False)
        context = visible_browser.new_context()
        page = context.new_page()
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            page.fill("#login-username", username)
            page.fill("#login-password", password)
            page.click("#login-form button[type=submit]")
            page.wait_for_timeout(2000)

            otp_field = page.query_selector('input[name="otp"]')
            if otp_field:
                code = self._get_totp_or_prompt()
                otp_field.fill(code)
                page.click("#login-form button[type=submit]")
                page.wait_for_timeout(2000)

            page.goto(HOME_URL, wait_until="domcontentloaded")
            if not self._is_logged_in(context):
                raise RuntimeError(
                    "Reddit login did not succeed — check REDDIT_USERNAME/REDDIT_PASSWORD "
                    "(and REDDIT_TOTP_SECRET, if 2FA is enabled) and try again."
                )

            session_path = _session_path()
            session_path.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(session_path))
            logger.info("Reddit session saved to %s", session_path)
        finally:
            page.close()
            context.close()
            visible_browser.close()

        return self._browser.new_context(storage_state=str(_session_path()))

    def _get_totp_or_prompt(self) -> str:
        totp_secret = os.environ.get("REDDIT_TOTP_SECRET")
        if totp_secret:
            import pyotp

            return pyotp.TOTP(totp_secret).now()
        return input("Enter your Reddit 2FA code: ").strip()

    def new_page(self) -> Page:
        polite_delay()
        return self._context.new_page()

    def close(self) -> None:
        self._context.close()
        self._browser.close()
        self._pw.stop()


_session: RedditSession | None = None


def get_session(force_new: bool = False) -> RedditSession:
    global _session
    if _session is None or force_new:
        _session = RedditSession()
    return _session
