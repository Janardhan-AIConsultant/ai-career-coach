"""Heuristic mock-interview answer evaluation (deterministic, explainable).

Dimensions (0-100): technical accuracy (coverage of the question's key points; STAR coverage for
behavioural questions), communication, clarity, problem solving, leadership (only for
leadership/management/behavioural/scenario kinds) and structured thinking. These are transparent
heuristics over the text, NOT an assessment by a human interviewer or an LLM; very short answers
cannot score highly and keyword stuffing is limited by the other dimensions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel

from app.career.taxonomy import leadership_patterns
from app.interview.bank import Question

DISCLAIMER = ("Automated, heuristic feedback based on key-point coverage and answer structure. "
              "It is practice guidance, not an assessment by a human interviewer.")
WEIGHTS = {"technical_accuracy": 0.35, "structured_thinking": 0.15, "problem_solving": 0.15,
           "communication": 0.10, "clarity": 0.10, "leadership": 0.15}
LEADERSHIP_KINDS = {"engineering_leadership", "engineering_management", "behavioural", "scenario"}
_FILLER = re.compile(r"\b(um+|uh+|you know|basically|kind of|sort of|like,|i guess|literally)\b", re.IGNORECASE)
_STRUCTURE = re.compile(
    r"\b(first(ly)?|second(ly)?|third(ly)?|finally|then|next|because|therefore|however|for example|"
    r"for instance|in summary|in short|step|trade-?off|on the other hand|as a result)\b", re.IGNORECASE)
_REASONING = re.compile(
    r"\b(trade-?offs?|alternatives?|constraints?|depends|options?|measure|test(ed|ing)?|validate|"
    r"risks?|fallback|edge cases?|assum\w+|prioriti[sz]e|compare|decid\w+)\b", re.IGNORECASE)


class Dimension(BaseModel):
    name: str
    score: int | None  # None = not applicable to this question kind
    note: str


class AnswerFeedback(BaseModel):
    overall_score: float
    dimensions: list[Dimension]
    key_points_covered: list[str]
    key_points_missed: list[str]
    strengths: list[str]
    improvements: list[str]
    model_answer: str
    practical_example: str
    follow_ups: list[str]
    evaluation_criteria: list[str]
    disclaimer: str = DISCLAIMER


@dataclass(frozen=True)
class _Stats:
    words: int
    sentences: int
    avg_sentence: float


def _stats(text: str) -> _Stats:
    words = len(text.split())
    sentences = max(1, len([s for s in re.split(r"[.!?]+\s|\n+", text) if s.strip()]))
    return _Stats(words, sentences, words / sentences)


def _clamp(v: float) -> int:
    return max(0, min(100, round(v)))


def evaluate_answer(q: Question, answer: str) -> AnswerFeedback:
    text = answer.strip()
    low = text.lower()
    st = _stats(text)

    covered = [kp.text for kp in q.key_points if any(k in low for k in kp.keywords)]
    missed = [kp.text for kp in q.key_points if kp.text not in covered]
    coverage = len(covered) / len(q.key_points)
    accuracy = _clamp(100 * coverage)
    if st.words < 15:
        accuracy = min(accuracy, 30)  # too short to demonstrate knowledge

    fillers = len(_FILLER.findall(text))
    comm = 100 * min(1.0, st.words / 60) - 5 * fillers - (20 if st.words > 450 else 0)
    clarity = 100 - max(0, st.avg_sentence - 25) * 3 - (10 if st.sentences < 2 and st.words > 40 else 0)
    structure_hits = len(_STRUCTURE.findall(text)) + len(re.findall(r"^\s*(?:[-*•]|\d+[.)])\s", text, re.MULTILINE))
    structure = 20 + 16 * structure_hits
    reasoning_hits = len(_REASONING.findall(text))
    problem = 15 + 17 * reasoning_hits
    lead_hits = sum(1 for pats in leadership_patterns().values() if any(p.search(text) for p in pats))
    leadership: int | None = 20 + 20 * lead_hits if q.kind in LEADERSHIP_KINDS else None
    if leadership is not None and q.kind == "behavioural":
        first_person = len(re.findall(r"\bi\b", low))
        leadership = _clamp(leadership + (10 if first_person >= 3 else -15))  # ownership: "I", not only "we"

    notes = {
        "technical_accuracy": f"{len(covered)} of {len(q.key_points)} expected key points covered",
        "communication": f"{st.words} words" + (f", {fillers} filler phrase(s)" if fillers else ""),
        "clarity": f"Average sentence length {st.avg_sentence:.0f} words",
        "structured_thinking": f"{structure_hits} structuring cue(s) (first/then/because/for example, lists)",
        "problem_solving": f"{reasoning_hits} reasoning cue(s) (trade-offs, alternatives, constraints, validation)",
        "leadership": "Leadership/ownership signals in your answer",
    }
    scores: dict[str, int | None] = {
        "technical_accuracy": accuracy, "communication": _clamp(comm), "clarity": _clamp(clarity),
        "structured_thinking": _clamp(structure), "problem_solving": _clamp(problem),
        "leadership": None if leadership is None else _clamp(leadership),
    }
    dims = [Dimension(name=n, score=s, note=notes[n] if s is not None else "Not applicable to this question")
            for n, s in scores.items()]
    applicable = {n: w for n, w in WEIGHTS.items() if scores[n] is not None}
    total_w = sum(applicable.values())
    overall = round(sum((scores[n] or 0) * w for n, w in applicable.items()) / total_w, 1)

    strengths = [f"{d.name.replace('_', ' ').title()}: {d.note}" for d in dims if d.score is not None and d.score >= 70]
    improvements = [f"Cover: {m}" for m in missed]
    if scores["structured_thinking"] is not None and scores["structured_thinking"] < 50:
        improvements.append("Structure your answer (e.g. first/then/finally, or STAR for behavioural questions)")
    if scores["problem_solving"] is not None and scores["problem_solving"] < 50 and q.kind != "hr":
        improvements.append("Discuss trade-offs, alternatives and how you would validate the approach")
    if st.words < 40:
        improvements.append("Give a fuller answer with a concrete example")
    if st.avg_sentence > 30:
        improvements.append("Use shorter sentences for clarity")
    return AnswerFeedback(
        overall_score=overall, dimensions=dims, key_points_covered=covered, key_points_missed=missed,
        strengths=strengths, improvements=improvements, model_answer=q.model_answer,
        practical_example=q.practical_example, follow_ups=list(q.follow_ups),
        evaluation_criteria=q.evaluation_criteria,
    )
