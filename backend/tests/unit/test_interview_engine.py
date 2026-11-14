import pytest

from app.career.jd_analysis import analyze_job_description
from app.career.resume_analysis import analyze_resume
from app.interview.bank import BY_ID, INTERVIEW_KINDS, QUESTIONS, TOPICS
from app.interview.evaluation import evaluate_answer
from app.interview.selection import select_questions
from tests.career_data import JD, RESUME

REQUIRED_TOPICS = {
    "java", "spring_boot", "react", "typescript", "python", "fastapi", "aws", "kafka", "postgresql",
    "microservices", "distributed_systems", "generative_ai", "rag", "langchain", "langgraph",
    "chromadb", "prompt_engineering", "system_design", "solution_architecture",
}


# ---------------------------------------------------------------- bank integrity
def test_bank_is_well_formed() -> None:
    assert len({q.id for q in QUESTIONS}) == len(QUESTIONS) == len(BY_ID)
    for q in QUESTIONS:
        assert q.kind in INTERVIEW_KINDS and q.difficulty in {"beginner", "intermediate", "advanced"}
        assert q.question.endswith(("?", ".")) and len(q.model_answer) > 40
        assert len(q.key_points) >= 3 and q.follow_ups and q.practical_example
        assert all(kp.keywords and all(k == k.lower() for k in kp.keywords) for kp in q.key_points)
        assert q.evaluation_criteria


def test_bank_covers_required_topics_and_every_kind() -> None:
    assert REQUIRED_TOPICS <= set(TOPICS)
    assert {q.kind for q in QUESTIONS} == set(INTERVIEW_KINDS)
    assert any(q.topic == "engineering_management" for q in QUESTIONS)
    for tech in REQUIRED_TOPICS:
        assert sum(q.topic == tech for q in QUESTIONS) >= 2


@pytest.mark.parametrize("q", [q for q in QUESTIONS if q.kind != "behavioural"], ids=lambda q: q.id)
def test_model_answers_cover_their_own_key_points(q) -> None:  # type: ignore[no-untyped-def]
    """Guards the keyword lists: the reference answer must satisfy most of its own key points."""
    fb = evaluate_answer(q, q.model_answer)
    assert len(fb.key_points_covered) / len(q.key_points) >= 0.66, fb.key_points_missed


# ---------------------------------------------------------------- selection
def _ctx():  # type: ignore[no-untyped-def]
    return analyze_resume(RESUME), analyze_job_description(
        "Required\n- Kafka\n- Python\n- Prompt Engineering\n- LangGraph\nPreferred\n- Docker\n- Spring Boot")


def test_selection_prioritises_required_unevidenced_topics() -> None:
    resume, jd = _ctx()
    picked = select_questions(["technical"], resume=resume, jd=jd, count=6)
    topics = [s.question.topic for s in picked]
    assert {"prompt_engineering", "langgraph"} <= set(topics[:4])  # required, not on the resume
    pe = next(s for s in picked if s.question.topic == "prompt_engineering")
    assert "practise" in pe.reason and "does not evidence" in pe.reason
    kafka = next(s for s in picked if s.question.topic == "kafka")
    assert "requires" in kafka.reason.lower() and "does not" not in kafka.reason  # evidenced -> depth


def test_selection_round_robin_and_count() -> None:
    picked = select_questions(["technical", "behavioural", "hr"], count=6)
    assert len(picked) == 6 and {s.question.kind for s in picked} == {"technical", "behavioural", "hr"}
    assert len(select_questions(list(INTERVIEW_KINDS), count=1000)) == len(QUESTIONS)


def test_selection_deterministic_and_unique() -> None:
    resume, jd = _ctx()
    a = select_questions(["technical", "scenario"], resume=resume, jd=jd, count=12)
    b = select_questions(["technical", "scenario"], resume=resume, jd=jd, count=12)
    assert [s.question.id for s in a] == [s.question.id for s in b]
    assert len({s.question.id for s in a}) == len(a)


def test_selection_topic_filter_and_unknown_kinds() -> None:
    picked = select_questions(["technical", "behavioural"], topics=["kafka"], count=20)
    assert {s.question.topic for s in picked if s.question.kind == "technical"} == {"kafka"}
    assert any(s.question.kind == "behavioural" for s in picked)
    assert select_questions(["nonsense"], count=5) == []


def test_leadership_questions_prioritised_when_jd_expects_leadership() -> None:
    jd = analyze_job_description(JD)  # expects mentoring / stakeholders
    picked = select_questions(["engineering_leadership"], jd=jd, count=3)
    assert picked and "leadership" in picked[0].reason.lower()


# ---------------------------------------------------------------- evaluation
GOOD_KAFKA = (
    "First, ordering in Kafka is guaranteed only within a partition, because each partition is an "
    "append-only log. Second, the message key is hashed to choose the partition, so for example using "
    "the order id as key keeps one order's events in order. Then consumers in a consumer group each "
    "read different partitions, so parallelism is bounded by the partition count; offsets track progress. "
    "The trade-off is that more partitions increase overhead, so I would measure before changing them."
)


def test_good_answer_scores_high_and_explains() -> None:
    fb = evaluate_answer(BY_ID["kafka-1"], GOOD_KAFKA)
    dims = {d.name: d for d in fb.dimensions}
    assert dims["technical_accuracy"].score == 100 and fb.key_points_missed == []
    assert dims["structured_thinking"].score and dims["structured_thinking"].score >= 70
    assert dims["leadership"].score is None and "Not applicable" in dims["leadership"].note
    assert fb.overall_score >= 70 and fb.strengths and fb.model_answer == BY_ID["kafka-1"].model_answer
    assert "heuristic" in fb.disclaimer.lower() and fb.follow_ups


def test_short_or_irrelevant_answers_score_low() -> None:
    q = BY_ID["kafka-1"]
    short = evaluate_answer(q, "partition order key consumer group")  # keyword dump, 5 words
    assert short.dimensions[0].score is not None and short.dimensions[0].score <= 30
    irrelevant = evaluate_answer(q, "I enjoy cooking pasta on weekends with fresh basil and garlic every week.")
    assert irrelevant.overall_score < 40 and len(irrelevant.key_points_missed) == 3
    assert any(i.startswith("Cover:") for i in irrelevant.improvements)


def test_better_answer_beats_worse_answer() -> None:
    q = BY_ID["kafka-1"]
    assert evaluate_answer(q, GOOD_KAFKA).overall_score > evaluate_answer(q, "Kafka uses partitions.").overall_score


def test_behavioural_uses_star_and_ownership() -> None:
    q = BY_ID["beh-1"]
    star = ("The situation was a payments migration with unclear scope. My goal was to deliver in a quarter. "
            "I decided to run weekly design reviews, I led the discovery, and I created a milestone plan. "
            "As a result we delivered two weeks early and reduced incidents by 30%. I learned to timebox discovery.")
    weak = "We just worked on it together and it went fine in the end."
    a, b = evaluate_answer(q, star), evaluate_answer(q, weak)
    assert a.overall_score > b.overall_score + 25
    lead = next(d for d in a.dimensions if d.name == "leadership")
    assert lead.score is not None and lead.score >= 40
    assert any("Specific actions" in m for m in b.key_points_missed)


def test_leadership_dimension_for_management_questions() -> None:
    fb = evaluate_answer(BY_ID["em-1"], "I mentor my team in regular one-to-ones, give specific timely feedback on behaviour and impact, and track growth goals with follow-up.")
    lead = next(d for d in fb.dimensions if d.name == "leadership")
    assert lead.score is not None and lead.score >= 40


def test_filler_and_run_on_penalised() -> None:
    q = BY_ID["py-2"]
    clean = "Generators use yield to produce values lazily. This saves memory for large streams and lets you build pipelines."
    messy = ("um basically like, you know, " + "generators are kind of sort of lazy " * 3) + "and um yield"
    assert evaluate_answer(q, clean).overall_score > evaluate_answer(q, messy).overall_score
    run_on = " ".join(["word"] * 80) + "."
    clarity = next(d for d in evaluate_answer(q, run_on).dimensions if d.name == "clarity")
    assert clarity.score is not None and clarity.score < 80


def test_scores_always_bounded() -> None:
    for q in QUESTIONS[:10]:
        for text in ("x", "word " * 700, "!!!", q.model_answer * 3):
            fb = evaluate_answer(q, text)
            assert 0 <= fb.overall_score <= 100
            assert all(d.score is None or 0 <= d.score <= 100 for d in fb.dimensions)
