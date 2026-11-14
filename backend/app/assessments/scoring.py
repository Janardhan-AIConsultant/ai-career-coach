"""Server-side question scoring. The client never supplies scores, only raw answers.

Each scorer returns ``QuestionResult`` with ``points`` in [0, 1]:
* mcq: exact option match.
* multi_select: (correct selected - wrong selected) / total correct, floored at 0.
* scenario: score assigned to the chosen option by the author (best action 1.0, plausible less).
* technical / practical: coverage of rubric key points by keyword (+ a minimum length); this is a
  transparent keyword rubric, not a human or LLM review, and feedback says so.
Invalid or missing answers score 0 (never raise), so a malformed payload cannot crash scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FREE_TEXT_NOTE = "Free-text answers are scored by a keyword rubric: practice guidance, not a human review."


@dataclass(frozen=True)
class QuestionResult:
    points: float
    status: str  # correct | partial | incorrect | unanswered | invalid
    feedback: str


def _int_list(value: Any, n: int) -> list[int] | None:
    if not isinstance(value, list) or len(value) > n:
        return None
    if not all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < n for i in value):
        return None
    return sorted(set(value))


def score_question(qtype: str, options: list[Any] | None, correct: Any, answer: Any) -> QuestionResult:
    n = len(options or [])
    if answer is None or answer == "" or answer == []:
        return QuestionResult(0.0, "unanswered", "No answer given")

    if qtype in ("mcq", "scenario"):
        if not isinstance(answer, int) or isinstance(answer, bool) or not 0 <= answer < n:
            return QuestionResult(0.0, "invalid", "Invalid answer format")
        pts = float(correct["scores"].get(str(answer), 0.0)) if qtype == "scenario" else float(answer == correct)
        status = "correct" if pts == 1.0 else "partial" if pts > 0 else "incorrect"
        return QuestionResult(pts, status, "")

    if qtype == "multi_select":
        chosen = _int_list(answer, n)
        if chosen is None:
            return QuestionResult(0.0, "invalid", "Invalid answer format")
        right = set(correct)
        pts = max(0.0, (len(set(chosen) & right) - len(set(chosen) - right)) / len(right))
        status = "correct" if set(chosen) == right else "partial" if pts > 0 else "incorrect"
        return QuestionResult(pts, status, "Partial credit: wrong selections subtract from correct ones")

    if qtype in ("technical", "practical"):
        if not isinstance(answer, str):
            return QuestionResult(0.0, "invalid", "Invalid answer format")
        low = answer.lower()
        points = correct["key_points"]
        hit = [p for p in points if any(k in low for k in p["keywords"])]
        pts = len(hit) / len(points)
        if len(answer.split()) < correct.get("min_words", 0):
            pts = min(pts, 0.5)
        missed = [p["text"] for p in points if p not in hit]
        status = "correct" if pts == 1.0 else "partial" if pts > 0 else "incorrect"
        detail = f"Covered {len(hit)} of {len(points)} expected points."
        if missed:
            detail += " Missing: " + "; ".join(missed) + "."
        return QuestionResult(pts, status, f"{detail} {FREE_TEXT_NOTE}")

    return QuestionResult(0.0, "invalid", "Unsupported question type")


def correct_display(qtype: str, options: list[Any] | None, correct: Any) -> Any:
    """Human-readable correct answer shown only after submission."""
    opts = options or []
    if qtype == "mcq":
        return opts[correct]
    if qtype == "multi_select":
        return [opts[i] for i in correct]
    if qtype == "scenario":
        best = max(correct["scores"].items(), key=lambda kv: kv[1])[0]
        return opts[int(best)]
    return [p["text"] for p in correct["key_points"]]
