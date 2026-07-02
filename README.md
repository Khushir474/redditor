# redditor

ICP-targeted Reddit comment outreach — finds relevant posts, drafts comments
in your own voice, and gates everything through anti-ban/quality checks
before anything gets posted (or auto-posts, if you flip the mode switch).

## Design

- **Anti-ban is the hard requirement.** Every draft passes through the same
  safety gate regardless of mode: similarity-vs-history check, per-post
  duplicate block, subreddit rule/karma/age checks, daily quota + jitter
  pacing, and a heuristic quality re-check.
- **Mode switch** (`human_approved` / `auto`, set per ICP profile or via
  `--mode`): controls only whether a passed draft waits for your review or
  goes straight to the posting queue. Start in `human_approved`, validate
  the gate's judgment, then flip to `auto`.
- **Voice** comes from retrieval, not a hand-written style prompt: your real
  Reddit comment history (`sync-history`) plus any hand-picked examples you
  import via CSV (`import-csv`) form an example store. Drafting retrieves
  the most similar past (post, comment) pairs and uses them as few-shot
  examples — this captures both voice *and* how much depth you tend to give
  for a given kind of question. Every comment actually posted gets appended
  back into the store.
- **Reddit access**: a browser session (Playwright, driving old.reddit.com
  as your logged-in account) is the default/primary client — no Reddit API
  app needed. Reddit's Responsible Builder Policy (effective 2026-06-05)
  removed self-serve app creation at `reddit.com/prefs/apps` and gated API
  access behind an approval process unlikely to grant a commenting/outreach
  use case, so the official API client (`REDDIT_CLIENT_MODE=api`, PRAW)
  is kept as an opt-in for anyone who does get approved, but isn't the
  default.
- **LLM**: OpenRouter primary, OpenAI fallback. **Embeddings**: Voyage AI or
  OpenAI, via `EMBEDDING_PROVIDER`.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium   # one-time, for the browser-session client
cp .env.example .env          # fill in your Reddit login + LLM/embedding API keys
```

Fill in `REDDIT_USERNAME`/`REDDIT_PASSWORD` in `.env` (and `REDDIT_TOTP_SECRET`
if your account has 2FA — otherwise you'll be prompted for a code in the
terminal on first login). The first command that touches Reddit opens a
**visible** browser window to log in and solve any captcha; it saves the
session to `data/reddit_session.json` so every run after that is headless
and doesn't log in again. If that file is ever deleted or the session goes
stale, it transparently falls back to a visible re-login.

If you have approved Reddit API access instead, set `REDDIT_CLIENT_MODE=api`
and fill in `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` (create a "script" app
at https://www.reddit.com/prefs/apps, if your account still has that option).

## Usage

```bash
# Seed your voice profile
python -m redditor.cli sync-history <your_reddit_username>
python -m redditor.cli import-csv path/to/hand_picked_examples.csv

# Find ICP-relevant posts (edit config/icp_profiles/example.yaml first)
python -m redditor.cli source --icp config/icp_profiles/example.yaml

# Full pipeline, prints drafts, posts nothing — do this before ever posting for real
python -m redditor.cli dry-run --icp config/icp_profiles/example.yaml

# Analyze + draft + gate whatever's been sourced
python -m redditor.cli draft --icp config/icp_profiles/example.yaml --mode human_approved

# Review pending drafts interactively (human_approved mode)
python -m redditor.cli review

# Post approved drafts, respecting daily quota + jitter pacing
python -m redditor.cli run
```

## Tests

```bash
pytest tests/
```

All tests run against a temp SQLite db and a fake (hash-based, deterministic)
embedding client — no network calls, no real API keys needed.

## Known limitations

- The browser client's `get_user_comments` (used by `sync-history`) can't
  pull the full text of a parent comment when you were replying to a
  comment rather than a post — old Reddit's comment-listing page only
  links to it. Use `import-csv` for reply-to-reply examples where the
  parent context matters.
- `get_subreddit_rules` uses the subreddit sidebar as a stand-in for a
  dedicated rules page, since old Reddit doesn't expose one cleanly.
- Scraping selectors (`.thing`, `.usertext-body`, etc.) are inherently
  fragile to Reddit UI changes — if `source`/`draft`/`run` start failing
  with empty results, that's the first thing to check.

## Deferred (not in this lean v1)

- Multi-account / proxy rotation
- Auto-reply to replies/threads
- Outcome-based re-weighting of the example store (basic cooldown-on-removal
  is implemented; re-weighting individual examples by outcome is not)
