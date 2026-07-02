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
- **Reddit access**: the official API (PRAW/OAuth) is primary. A browser
  automation fallback (`REDDIT_CLIENT_MODE=browser`) is stubbed behind the
  same interface for when the API isn't viable — not implemented yet.
- **LLM**: OpenRouter primary, OpenAI fallback. **Embeddings**: Voyage AI or
  OpenAI, via `EMBEDDING_PROVIDER`.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in Reddit API creds + LLM/embedding API keys
```

Create a Reddit "script" app at https://www.reddit.com/prefs/apps to get
`REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`. Username/password are only
needed if you want to post (read-only sourcing/dry-run works without them).

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

## Deferred (not in this lean v1)

- Full browser-automation fallback implementation
- Multi-account / proxy rotation
- Auto-reply to replies/threads
- Outcome-based re-weighting of the example store (basic cooldown-on-removal
  is implemented; re-weighting individual examples by outcome is not)
