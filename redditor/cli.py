from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys

from dotenv import load_dotenv

from . import copy_gen, example_store, post_analysis, scheduler, sourcing
from .config import load_icp_profile
from .db import get_db, init_db
from .models import CandidatePost

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("redditor.cli")


def _row_to_candidate(row: sqlite3.Row) -> CandidatePost:
    return CandidatePost(
        id=row["id"],
        subreddit=row["subreddit"],
        title=row["title"],
        desc=row["desc"],
        url=row["url"],
        reddit_post_id=row["reddit_post_id"],
        icp_name=row["icp_name"],
        relevance_score=row["relevance_score"],
        intent=row["intent"],
        thread_tone=row["thread_tone"],
        referenced_link=row["referenced_link"],
        is_lead=bool(row["is_lead"]),
        status=row["status"],
        sourced_at=row["sourced_at"],
    )


def cmd_sync_history(args: argparse.Namespace) -> None:
    n = example_store.sync_reddit_history(args.username, limit=args.limit)
    print(f"Synced {n} new examples from u/{args.username}'s comment history.")


def cmd_import_csv(args: argparse.Namespace) -> None:
    n = example_store.import_csv(args.path)
    print(f"Imported {n} examples from {args.path}.")


def cmd_source(args: argparse.Namespace) -> None:
    icp = load_icp_profile(args.icp)
    candidates = sourcing.source_candidates(icp, limit_per_subreddit=args.limit)
    leads = sum(1 for c in candidates if c.is_lead)
    print(f"Sourced {len(candidates)} new candidates for ICP '{icp.name}' ({leads} flagged as leads).")


def _pending_candidates(icp_name: str | None) -> list[CandidatePost]:
    query = "SELECT * FROM candidate_posts WHERE status = 'sourced'"
    params: tuple = ()
    if icp_name:
        query += " AND icp_name = ?"
        params = (icp_name,)
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_candidate(r) for r in rows]


def cmd_draft(args: argparse.Namespace) -> None:
    from .safety_gate import run_gate

    icp = load_icp_profile(args.icp) if args.icp else None
    mode = args.mode or (icp.default_mode if icp else "human_approved")

    candidates = _pending_candidates(icp.name if icp else None)
    print(f"Drafting for {len(candidates)} candidate(s) in mode={mode}...")

    for candidate in candidates:
        try:
            analysis = post_analysis.analyze_candidate(candidate)
            draft = copy_gen.generate_and_persist_draft(candidate, analysis, mode=mode)
            gate_result = run_gate(draft, candidate, mode=mode)
            print(f"  [{candidate.subreddit}] draft #{draft.id} -> {draft.status}"
                  + ("" if gate_result["passed"] else f" ({'; '.join(gate_result['reasons'])})"))
        except Exception as exc:
            logger.exception("Failed to draft for candidate %s: %s", candidate.id, exc)


def cmd_review(args: argparse.Namespace) -> None:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT d.id, d.comment_body, c.subreddit, c.title, c.url FROM drafts d "
            "JOIN candidate_posts c ON d.candidate_post_id = c.id "
            "WHERE d.status = 'pending_review' ORDER BY d.created_at ASC"
        ).fetchall()

    if not rows:
        print("Nothing pending review.")
        return

    for row in rows:
        print("\n" + "=" * 60)
        print(f"r/{row['subreddit']} — {row['title']}\n{row['url']}\n")
        print(row["comment_body"])
        choice = input("\n[a]pprove / [r]eject / [e]dit / [s]kip? ").strip().lower()
        with get_db() as conn:
            if choice == "a":
                conn.execute("UPDATE drafts SET status = 'approved' WHERE id = ?", (row["id"],))
            elif choice == "r":
                conn.execute("UPDATE drafts SET status = 'rejected' WHERE id = ?", (row["id"],))
            elif choice == "e":
                new_body = input("New comment text:\n").strip()
                conn.execute(
                    "UPDATE drafts SET comment_body = ?, status = 'approved' WHERE id = ?",
                    (new_body, row["id"]),
                )
            # 's' or anything else: leave as pending_review


def cmd_run(args: argparse.Namespace) -> None:
    results = scheduler.dispatch(account=args.account, max_to_post=args.max, dry_run=args.dry_run)
    for r in results:
        print(r)
    removal_report = scheduler.check_for_removals(account=args.account)
    print(f"Removal check: {removal_report}")


def cmd_dry_run(args: argparse.Namespace) -> None:
    icp = load_icp_profile(args.icp)
    candidates = sourcing.source_candidates(icp, limit_per_subreddit=args.limit)
    print(f"Sourced {len(candidates)} candidates. Drafting (nothing will be posted)...\n")
    for candidate in candidates:
        analysis = post_analysis.analyze_candidate(candidate)
        draft = copy_gen.generate_and_persist_draft(candidate, analysis, mode="human_approved")
        from .safety_gate import run_gate

        gate_result = run_gate(draft, candidate, mode="human_approved")
        print("=" * 60)
        print(f"r/{candidate.subreddit} — {candidate.title} ({candidate.url})")
        print(f"intent={analysis.get('intent')} tone={analysis.get('thread_tone')}")
        print(f"\n{draft.comment_body}\n")
        print(f"gate: {'PASS' if gate_result['passed'] else 'FAIL'} {gate_result['reasons']}")


def main() -> None:
    load_dotenv()
    init_db()

    parser = argparse.ArgumentParser(prog="redditor")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sync-history", help="Pull your own comment history into the example store")
    p.add_argument("username", nargs="?", default=os.environ.get("REDDIT_USERNAME"))
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(func=cmd_sync_history)

    p = sub.add_parser("import-csv", help="Import a CSV of past (post, comment) pairs")
    p.add_argument("path")
    p.set_defaults(func=cmd_import_csv)

    p = sub.add_parser("source", help="Source ICP-relevant candidate posts")
    p.add_argument("--icp", required=True)
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_source)

    p = sub.add_parser("draft", help="Analyze + draft + gate all pending candidates")
    p.add_argument("--icp", default=None)
    p.add_argument("--mode", choices=["human_approved", "auto"], default=None)
    p.set_defaults(func=cmd_draft)

    p = sub.add_parser("review", help="Interactively approve/edit/reject pending drafts")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("run", help="Post approved drafts (paced, quota-respecting)")
    p.add_argument("--account", default="default")
    p.add_argument("--max", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("dry-run", help="Full pipeline end-to-end, prints drafts, posts nothing")
    p.add_argument("--icp", required=True)
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_dry_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
