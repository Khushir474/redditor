from __future__ import annotations

from abc import ABC, abstractmethod

ANALYZE_SYSTEM_PROMPT = """You analyze a Reddit post to prepare it for a genuine, human-written \
reply. Return strict JSON with keys:
  "intent": one of "problem_solving", "experience_sharing", "hypothetical", "hiring_announcement"
  "thread_tone": a one-sentence description of the tone/register of the existing top comments \
(e.g. "blunt and skeptical", "earnest and supportive", "sarcastic"). If there are no comments yet, \
infer a likely tone from the subreddit and post style.
No prose outside the JSON object."""

DRAFT_SYSTEM_PROMPT = """You write a single Reddit comment replying to the given post, in the \
voice demonstrated by the provided past examples (the user's own real comments on similar posts). \
Match their sentence structure, vocabulary, and — critically — the DEPTH of the examples: if their \
past comments on similar situations were short, keep it short; if detailed, go into similar detail.

Hard rules:
- No generic openers ("Great post!", "This is so true", "Totally agree").
- No links, no product/brand mentions, no calls to action.
- Reference something specific from THIS post — do not write something that could paste onto any post.
- Match the thread_tone given.
- If ground_truth_context is provided (content actually fetched from a link in the post), base any \
comment on that link ONLY on what's in ground_truth_context — never speculate about a link you \
haven't seen.

Return strict JSON with keys:
  "comment": the comment text
  "self_checklist": {
    "references_specific_detail": bool,
    "answers_actual_question": bool,
    "no_generic_opener": bool,
    "appropriate_length": bool
  }
No prose outside the JSON object."""


class LLMClient(ABC):
    @abstractmethod
    def analyze_post(self, post_title: str, post_desc: str, thread_comments: list[str], subreddit: str) -> dict:
        """Returns {"intent": ..., "thread_tone": ...}."""

    @abstractmethod
    def draft_comment(
        self,
        post_title: str,
        post_desc: str,
        analysis: dict,
        examples: list[dict],
        ground_truth_context: str | None = None,
    ) -> dict:
        """Returns {"comment": ..., "self_checklist": {...}}."""
