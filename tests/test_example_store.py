from __future__ import annotations

import csv

from redditor import example_store


def _write_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["post_title", "post_desc", "post_link", "parent_comment", "user_comment", "subreddit"]
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_import_csv_inserts_examples(tmp_path, fake_embedder):
    csv_path = tmp_path / "examples.csv"
    _write_csv(
        csv_path,
        [
            {
                "post_title": "Best CRM for a 3-person sales team?",
                "post_desc": "We're outgrowing spreadsheets.",
                "post_link": "https://reddit.com/r/startups/1",
                "parent_comment": "",
                "user_comment": "We went with HubSpot free tier for the first 6 months, worked fine.",
                "subreddit": "startups",
            }
        ],
    )

    inserted = example_store.import_csv(csv_path)
    assert inserted == 1


def test_retrieve_similar_returns_top_k(tmp_path, fake_embedder):
    csv_path = tmp_path / "examples.csv"
    _write_csv(
        csv_path,
        [
            {
                "post_title": "CRM recommendations?",
                "post_desc": "",
                "post_link": "https://reddit.com/r/startups/1",
                "parent_comment": "",
                "user_comment": "HubSpot worked for us early on.",
                "subreddit": "startups",
            },
            {
                "post_title": "Best pizza in Chicago?",
                "post_desc": "",
                "post_link": "https://reddit.com/r/chicago/1",
                "parent_comment": "",
                "user_comment": "Lou Malnati's, no contest.",
                "subreddit": "chicago",
            },
        ],
    )
    example_store.import_csv(csv_path)

    results = example_store.retrieve_similar("Which CRM should I use?", "", k=1)
    assert len(results) == 1
    assert "similarity" in results[0]


def test_append_posted_example_grows_store(fake_embedder):
    example_store.append_posted_example(
        post_title="Any GTM advice?",
        post_desc="Pre-seed, no sales hire yet.",
        post_link="https://reddit.com/r/startups/2",
        user_comment="Founder-led sales for the first 20 customers, then hire.",
        subreddit="startups",
    )
    results = example_store.retrieve_similar("Any GTM advice?", "", k=5)
    assert len(results) == 1
