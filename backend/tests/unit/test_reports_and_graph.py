import io
import unicodedata

import pymupdf
import pytest
from docx import Document

from app.core.exceptions import LLMServiceError, ReportGenerationError
from app.guardrails.prompt_safety import CANARY
from app.services import report_builders as rb
from app.services.report_render import ReportDoc, Section, render
from app.workflows.career_graph import build_career_graph
from tests.career_data import JD, RESUME


def pdf_text(data: bytes) -> str:
    doc = pymupdf.open(stream=data, filetype="pdf")
    return "\n".join(str(doc.load_page(i).get_text()) for i in range(doc.page_count))


def test_pdf_render_contains_content_and_escapes_markup() -> None:
    doc = ReportDoc("Report <b>Title</b>", "Disclaimer & note", [
        Section("Skills", ["Paragraph <script>alert(1)</script>"], ["bullet one", "bullet two"],
                [["Name", "Score"], ["python", "90"]])])
    data = render(doc, "pdf")
    assert data.startswith(b"%PDF-")
    text = pdf_text(data)
    assert "<b>Title</b>" in text and "<script>alert(1)</script>" in text  # shown literally, not parsed
    assert "bullet two" in text and "python" in text and "Disclaimer & note" in text


def test_pdf_paginates_long_reports() -> None:
    doc = ReportDoc("Long", None, [Section(f"Section {i}", ["lorem ipsum " * 60]) for i in range(40)])
    data = render(doc, "pdf")
    assert pymupdf.open(stream=data, filetype="pdf").page_count > 1


def test_docx_render_roundtrip() -> None:
    doc = ReportDoc("My Report", "A disclaimer", [
        Section("Heading", ["Body text"], ["item A"], [["H1", "H2"], ["a", "b"]])])
    d = Document(io.BytesIO(render(doc, "docx")))
    texts = [p.text for p in d.paragraphs]
    assert "My Report" in texts and "Body text" in texts and "item A" in texts
    assert d.tables[0].rows[1].cells[1].text == "b"


def test_unsupported_format_rejected() -> None:
    with pytest.raises(ReportGenerationError):
        render(ReportDoc("x"), "xlsx")


def test_all_report_builders_render_both_formats() -> None:
    from app.career.jd_analysis import analyze_job_description
    from app.career.matching import match
    from app.career.optimization import optimize_resume
    from app.career.resume_analysis import analyze_resume
    from app.career.skill_gap import analyze_skill_gaps

    r, j = analyze_resume(RESUME), analyze_job_description(JD)
    m = match(r, j)
    docs = [rb.resume_analysis_doc(r), rb.jd_analysis_doc(j), rb.match_doc(m),
            rb.skill_gap_doc(analyze_skill_gaps(m, j)),
            rb.optimization_doc(optimize_resume(RESUME, r, j, m)),
            rb.optimized_resume_doc(optimize_resume(RESUME, r, j, m))]
    for d in docs:
        assert render(d, "pdf").startswith(b"%PDF-") and len(render(d, "docx")) > 1000
    text = unicodedata.normalize("NFKC", pdf_text(render(rb.match_doc(m), "pdf")))  # PDF ligatures
    assert "not an official ATS score" in " ".join(text.split())


# ---------------------------------------------------------------- LangGraph workflow
class FakeLLM:
    def __init__(self, reply: str = "Strong fit for backend work.") -> None:
        self.reply, self.prompts = reply, []

    def invoke(self, system: str, user: str) -> str:
        self.prompts.append((system, user))
        return self.reply


def _run(llm, narrative: bool = False):  # type: ignore[no-untyped-def]
    return build_career_graph(llm).invoke(
        {"resume_text": RESUME, "jd_text": JD, "declared_absent": set(), "include_narrative": narrative})


def test_graph_runs_all_steps_without_llm() -> None:
    st = _run(None, narrative=True)
    assert {"resume", "jd", "match", "gaps"} <= set(st) and st.get("narrative") is None
    assert st["match"].overall_score > 0


def test_graph_skips_llm_unless_requested() -> None:
    llm = FakeLLM()
    assert _run(llm, narrative=False).get("narrative") is None and llm.prompts == []


def test_graph_narrative_receives_facts_only_not_raw_resume() -> None:
    llm = FakeLLM()
    st = _run(llm, narrative=True)
    assert st["narrative"] == "Strong fit for backend work."
    system, user = llm.prompts[0]
    assert "Estimated match score" in user and "kafka" in user.lower()
    for private in ("Jane Doe", "jane.doe@example.com", "Acme Payments", "98765"):
        assert private not in user and private not in system


def test_graph_narrative_failures_degrade_gracefully() -> None:
    class Failing:
        def invoke(self, system: str, user: str) -> str:
            raise LLMServiceError()

    assert _run(Failing(), narrative=True)["narrative"] is None
    assert _run(FakeLLM(f"leak {CANARY}"), narrative=True)["narrative"] is None
    assert _run(FakeLLM(""), narrative=True)["narrative"] is None
    assert _run(FakeLLM("x" * 2000), narrative=True)["narrative"] is None
