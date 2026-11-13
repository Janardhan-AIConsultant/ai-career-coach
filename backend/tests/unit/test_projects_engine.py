import httpx
import pytest

from app.core.exceptions import InputValidationError, ServiceBusyError
from app.projects.catalog import BY_ID, TEMPLATES
from app.projects.evaluation import NOT_EXECUTED, evaluate_project
from app.projects.github import API, GitHubFetcher, RepoEvidence, parse_repo_url, repo_key
from tests.project_data import GOOD_PATHS, good_readme, ideal_evidence, poor_evidence

RAG = BY_ID["rag-qa-api"]


# ---------------------------------------------------------------- catalog
def test_catalog_integrity() -> None:
    assert len({t.id for t in TEMPLATES}) == len(TEMPLATES) >= 6
    for t in TEMPLATES:
        assert t.kind in {"code", "documentation"} and t.description and t.expected_outcomes and t.technologies
        assert len(t.requirements) >= 3 and len(t.milestones) >= 3 and t.skills
        assert all(i.keywords and all(k == k.lower() for k in i.keywords) for i in (*t.requirements, *t.milestones))


@pytest.mark.parametrize("t", TEMPLATES, ids=lambda t: t.id)
def test_ideal_evidence_passes_every_template(t) -> None:  # type: ignore[no-untyped-def]
    ev = evaluate_project(t, ideal_evidence(t), "")
    assert ev.passed and ev.overall_score >= 70, [(c.name, c.score) for c in ev.criteria]
    assert all(r["evidenced"] for r in ev.requirements)


# ---------------------------------------------------------------- GitHub URL handling
@pytest.mark.parametrize("url,expected", [
    ("https://github.com/acme/demo", ("acme", "demo")), ("https://github.com/acme/demo/", ("acme", "demo")),
    ("https://github.com/acme/demo.git", ("acme", "demo")), ("https://github.com/Acme/My.Repo_1", ("Acme", "My.Repo_1")),
    ("  https://github.com/acme/demo  ", ("acme", "demo"))])
def test_valid_repo_urls(url: str, expected: tuple[str, str]) -> None:
    assert parse_repo_url(url) == expected
    assert repo_key(*expected) == f"github.com/{expected[0]}/{expected[1]}".lower()


@pytest.mark.parametrize("url", [
    "http://github.com/acme/demo", "https://gitlab.com/acme/demo", "https://github.com/acme",
    "https://github.com/acme/demo/tree/main", "https://github.com.evil.example/acme/demo",
    "https://evil.example/https://github.com/acme/demo", "https://user:pw@github.com/acme/demo",
    "https://github.com/acme/..", "https://github.com/acme/demo?x=1", "file:///etc/passwd",
    "https://github.com/acme/demo\nhttps://evil.example", "https://127.0.0.1/acme/demo", "", "javascript:alert(1)"])
def test_invalid_repo_urls_rejected(url: str) -> None:
    with pytest.raises(InputValidationError):
        parse_repo_url(url)


def _fetcher(handler) -> tuple[GitHubFetcher, list[str]]:  # type: ignore[no-untyped-def]
    seen: list[str] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.url.host}{request.url.path}")
        return handler(request)

    client = httpx.Client(base_url=API, transport=httpx.MockTransport(wrapped))
    return GitHubFetcher(client=client), seen


def _ok(request: httpx.Request) -> httpx.Response:
    p = request.url.path
    if p.endswith("/readme"):
        return httpx.Response(200, text="# Demo readme")
    if "/git/trees/" in p:
        return httpx.Response(200, json={"sha": "abc", "truncated": False, "tree": [
            {"path": "src/a.py", "type": "blob"}, {"path": "src", "type": "tree"}, {"path": "README.md", "type": "blob"}]})
    return httpx.Response(200, json={"private": False, "default_branch": "dev"})


def test_fetcher_reads_only_allowed_api_endpoints() -> None:
    f, seen = _fetcher(_ok)
    ev = f.fetch("Acme", "Demo")
    assert ev.paths == ["src/a.py", "README.md"] and ev.readme == "# Demo readme" and ev.default_branch == "dev"
    assert ev.repo_key == "github.com/acme/demo" and ev.head_sha == "abc"
    assert all(s.startswith("api.github.com/repos/Acme/Demo") for s in seen) and len(seen) == 3


def test_fetcher_error_mapping() -> None:
    for status, exc in ((404, InputValidationError), (403, ServiceBusyError), (429, ServiceBusyError), (500, ServiceBusyError)):
        f, _ = _fetcher(lambda r, s=status: httpx.Response(s))
        with pytest.raises(exc):
            f.fetch("a", "b")

    def private(r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"private": True})

    with pytest.raises(InputValidationError):
        _fetcher(private)[0].fetch("a", "b")

    def boom(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down")

    with pytest.raises(ServiceBusyError):
        _fetcher(boom)[0].fetch("a", "b")


def test_missing_readme_is_not_an_error() -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        return httpx.Response(404) if r.url.path.endswith("/readme") else _ok(r)

    assert _fetcher(handler)[0].fetch("a", "b").readme == ""


# ---------------------------------------------------------------- evaluation
def test_evaluation_never_claims_execution() -> None:
    ev = evaluate_project(RAG, ideal_evidence(RAG), "")
    assert ev.code_executed is False and ev.disclaimer == NOT_EXECUTED and "NOT executed" in ev.disclaimer
    assert any("not executed" in f.lower() for c in ev.criteria if c.name == "testing" for f in c.findings)


def test_poor_submission_fails_with_actionable_feedback() -> None:
    ev = evaluate_project(RAG, poor_evidence(), "")
    assert not ev.passed and ev.overall_score < 40
    assert any("Show evidence for" in i for i in ev.improvements)
    assert any("at least 5 source files" in i for i in ev.improvements)
    assert any("Requirement coverage must reach" in i for i in ev.improvements)


def test_requirement_coverage_gate_blocks_otherwise_strong_repos() -> None:
    weak_docs = good_readme(RAG)
    for kw in ("ingest", "chunk", "upload", "embedding", "vector", "chroma", "faiss", "pgvector", "retriev", "similarity",
               "top-k", "top_k", "citation", "cite", "source", "isolation", "tenant", "filter", "metadata"):
        weak_docs = weak_docs.replace(kw, "zzz")
    ev = evaluate_project(RAG, RepoEvidence("github.com/a/b", GOOD_PATHS, weak_docs, "main", None, False), "")
    cov = next(c.score for c in ev.criteria if c.name == "requirement_coverage")
    assert cov is not None and cov < 60 and not ev.passed


def test_committed_secrets_and_missing_tests_are_flagged() -> None:
    paths = [p for p in GOOD_PATHS if "test" not in p] + [".env", "config/key.pem"]
    ev = evaluate_project(RAG, RepoEvidence("github.com/a/b", paths, good_readme(RAG), "main", None, False), "")
    quality = next(c for c in ev.criteria if c.name == "code_quality")
    assert any("Possible committed secret files" in f for f in quality.findings)
    testing = next(c for c in ev.criteria if c.name == "testing")
    assert testing.score is not None and testing.score < 60 and "0 test file(s)" in testing.findings[0]
    assert ".env.example" not in " ".join(f for f in quality.findings if "secret" in f)  # example files are fine


def test_placeholders_reduce_completeness() -> None:
    base = evaluate_project(RAG, ideal_evidence(RAG), "")
    todo = ideal_evidence(RAG)
    noisy = RepoEvidence(todo.repo_key, todo.paths, todo.readme + " TODO TODO TODO TODO FIXME", "main", None, False)
    a = next(c.score for c in base.criteria if c.name == "completeness")
    b = next(c.score for c in evaluate_project(RAG, noisy, "").criteria if c.name == "completeness")
    assert a is not None and b is not None and b == a - 15


def test_documentation_project_uses_pasted_text_and_skips_code_criteria() -> None:
    t = BY_ID["team-playbook"]
    text = good_readme(t)
    ev = evaluate_project(t, None, text)
    by = {c.name: c for c in ev.criteria}
    assert by["testing"].score is None and by["architecture"].score is None and by["code_quality"].score is None
    assert ev.passed and ev.summary["repo"] is None
    thin = evaluate_project(t, None, "onboarding only")
    assert not thin.passed


def test_evaluation_is_deterministic_and_bounded() -> None:
    a, b = evaluate_project(RAG, ideal_evidence(RAG), ""), evaluate_project(RAG, ideal_evidence(RAG), "")
    assert a == b and 0 <= a.overall_score <= 100 and all(c.score is None or 0 <= c.score <= 100 for c in a.criteria)
    assert evaluate_project(RAG, None, "").overall_score < 50
