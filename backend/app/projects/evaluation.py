"""Static evidence review of a submitted project.

This inspects the repository FILE LIST, the README and any pasted documentation. It does NOT clone,
run or test the code, and says so in every result (``code_executed`` is always False). Scores are
transparent rubric points; they show that the work is structured and documented, not that it
works. Criteria: requirement coverage, architecture, code quality, documentation, testing and
completeness (testing is skipped for documentation-only projects).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel

from app.projects.catalog import ProjectTemplate
from app.projects.github import RepoEvidence

NOT_EXECUTED = ("Static evidence review of repository structure and documentation. "
                "The code was NOT executed and its tests were NOT run.")
WEIGHTS = {"requirement_coverage": 0.30, "architecture": 0.15, "code_quality": 0.15,
           "documentation": 0.15, "testing": 0.15, "completeness": 0.10}
SOURCE_EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".cs", ".rb", ".php", ".scala")
LAYER_DIRS = {"api", "routes", "routers", "controllers", "services", "service", "models", "schemas", "repositories",
              "core", "domain", "components", "pages", "hooks", "utils", "handlers", "config", "workers", "adapters"}
MANIFESTS = {"requirements.txt", "pyproject.toml", "package.json", "pom.xml", "build.gradle", "build.gradle.kts",
             "go.mod", "cargo.toml", "gemfile", "composer.json", "poetry.lock", "pipfile"}
SECRET_FILES = re.compile(r"(^|/)(\.env|id_rsa|id_ed25519|credentials\.json|.*\.pem|.*\.p12|secrets\.ya?ml)$", re.IGNORECASE)
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)/|(_test\.[a-z]+$)|(\.(test|spec)\.[a-z]+$)|(Test\.java$)|(^|/)test_[^/]+\.py$", re.IGNORECASE)
LINT = ("ruff.toml", ".ruff.toml", ".flake8", ".pylintrc", "eslint.config", ".eslintrc", ".prettierrc", "prettier.config",
        "checkstyle", ".golangci", "biome.json", "tox.ini", "setup.cfg", ".editorconfig")
TYPECHECK = ("mypy.ini", "tsconfig.json", "pyrightconfig.json", ".mypy.ini")


class CriterionResult(BaseModel):
    name: str
    score: int | None  # None = not applicable
    findings: list[str]


class Evaluation(BaseModel):
    overall_score: float
    passed: bool
    criteria: list[CriterionResult]
    requirements: list[dict[str, object]]
    milestones: list[dict[str, object]]
    improvements: list[str]
    summary: dict[str, object]
    code_executed: bool = False
    disclaimer: str = NOT_EXECUTED


@dataclass(frozen=True)
class _Corpus:
    paths: list[str]
    lower_paths: list[str]
    text: str  # lower-cased README + pasted docs + file paths

    @property
    def names(self) -> set[str]:
        return {p.rsplit("/", 1)[-1].lower() for p in self.paths}


def _hit(keywords: tuple[str, ...], text: str) -> bool:
    return any(k in text for k in keywords)


def _words(text: str) -> int:
    return len(re.findall(r"\w+", text))


def _any_path(corpus: _Corpus, needles: tuple[str, ...]) -> bool:
    return any(n in p for p in corpus.lower_paths for n in needles)


def _architecture(c: _Corpus, readme_lower: str) -> CriterionResult:
    f: list[str] = []
    dirs = {seg for p in c.lower_paths for seg in p.split("/")[:-1]}
    layers = dirs & LAYER_DIRS
    pts = 30 if len(layers) >= 3 else 20 if len(layers) == 2 else 10 if layers else 0
    f.append(f"Layered structure: {', '.join(sorted(layers)) or 'none detected'}")
    if c.names & MANIFESTS:
        pts += 20
        f.append("Dependency manifest present")
    else:
        f.append("No dependency manifest found")
    if _any_path(c, ("architecture", "/adr", "adr/", "design.md", "docs/design")) or re.search(r"#+\s*architecture", readme_lower):
        pts += 20
        f.append("Architecture/design documentation present")
    else:
        f.append("No architecture documentation found")
    if c.names & {".env.example", ".env.sample", "config.py", "settings.py", "application.yml", "application.properties"} or "config" in dirs:
        pts += 15
        f.append("Configuration is separated from code")
    if c.names & {"dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml"}:
        pts += 15
        f.append("Container/infrastructure files present")
    return CriterionResult(name="architecture", score=min(100, pts), findings=f)


def _code_quality(c: _Corpus) -> CriterionResult:
    f: list[str] = []
    pts = 0
    if any(any(m in n for m in LINT) for n in c.names) or "pyproject.toml" in c.names:
        pts += 25
        f.append("Linter/formatter configuration present")
    else:
        f.append("No linter/formatter configuration found")
    if any(any(m in n for m in TYPECHECK) for n in c.names):
        pts += 15
        f.append("Type-checking configuration present")
    if _any_path(c, (".github/workflows/", ".gitlab-ci", "jenkinsfile", ".circleci/")):
        pts += 20
        f.append("CI configuration present")
    else:
        f.append("No CI configuration found")
    if ".gitignore" in c.names:
        pts += 10
    if ".pre-commit-config.yaml" in c.names:
        pts += 10
    secrets = [p for p in c.paths if SECRET_FILES.search(p) and not p.lower().endswith((".example", ".sample"))]
    if secrets:
        f.append("Possible committed secret files: " + ", ".join(secrets[:3]) + " (remove and rotate any real secrets)")
    else:
        pts += 20
        f.append("No committed secret files detected")
    return CriterionResult(name="code_quality", score=min(100, pts), findings=f)


def _documentation(c: _Corpus, readme: str, extra: str) -> CriterionResult:
    f: list[str] = []
    words = _words(readme) + _words(extra)
    pts = 40 if words >= 300 else 25 if words >= 150 else 10 if words >= 50 else 0
    f.append(f"README/documentation length: {words} words")
    low = (readme + "\n" + extra).lower()
    sections = {"installation or setup": ("install", "setup", "getting started"), "usage": ("usage", "how to run", "run the"),
                "testing": ("test",), "architecture": ("architecture", "design"), "license": ("license",), "api or features": ("api", "feature", "endpoint")}
    found = [name for name, kws in sections.items() if _hit(kws, low)]
    pts += min(40, 10 * len(found))
    f.append(f"Sections covered: {', '.join(found) or 'none'}")
    if any(p.startswith("docs/") for p in c.lower_paths) or sum(p.endswith(".md") for p in c.lower_paths) >= 3:
        pts += 10
    if "license" in c.names or "license.md" in c.names:
        pts += 10
    return CriterionResult(name="documentation", score=min(100, pts), findings=f)


def _testing(c: _Corpus, readme_lower: str) -> CriterionResult:
    f: list[str] = []
    src = [p for p in c.paths if p.lower().endswith(SOURCE_EXT) and not TEST_PATH.search(p)]
    tests = [p for p in c.paths if p.lower().endswith(SOURCE_EXT) and TEST_PATH.search(p)]
    ratio = len(tests) / len(src) if src else 0.0
    pts = 40 if ratio >= 0.2 else 20 if tests else 0
    f.append(f"{len(tests)} test file(s) for {len(src)} source file(s)")
    if c.names & {"pytest.ini", "conftest.py", "jest.config.js", "jest.config.ts", "vitest.config.ts", "pom.xml", "tox.ini"} or "pyproject.toml" in c.names:
        pts += 20
    if _any_path(c, (".github/workflows/", ".gitlab-ci", "jenkinsfile")):
        pts += 20
        f.append("CI configuration may run the tests (not verified)")
    if re.search(r"pytest|npm (run )?test|mvn test|go test|gradle test|vitest|jest", readme_lower):
        pts += 20
        f.append("README documents how to run tests")
    if not tests:
        pts = min(pts, 25)  # configuration or README claims cannot substitute for actual test files
        f.append("No test files found: testing score is capped")
    f.append("Tests were not executed by this review")
    return CriterionResult(name="testing", score=min(100, pts), findings=f)


def evaluate_project(template: ProjectTemplate, evidence: RepoEvidence | None, extra_docs: str,
                     pass_score: float = 70.0) -> Evaluation:
    paths = evidence.paths if evidence else []
    readme = evidence.readme if evidence else ""
    corpus = _Corpus(paths, [p.lower() for p in paths], (readme + "\n" + extra_docs + "\n" + "\n".join(paths)).lower())
    readme_lower = (readme + "\n" + extra_docs).lower()

    reqs = [{"requirement": r.text, "evidenced": _hit(r.keywords, corpus.text)} for r in template.requirements]
    stones = [{"milestone": m.text, "evidenced": _hit(m.keywords, corpus.text)} for m in template.milestones]
    coverage = round(100 * sum(bool(r["evidenced"]) for r in reqs) / len(reqs))
    cov_f = [("Evidenced: " if r["evidenced"] else "Not evidenced: ") + str(r["requirement"]) for r in reqs]

    placeholders = len(re.findall(r"\btodo\b|\bfixme\b|lorem ipsum|work in progress|\bwip\b", readme_lower))
    done = round(70 * sum(bool(m["evidenced"]) for m in stones) / len(stones)) + 30 - (15 if placeholders > 3 else 0)
    comp_f = [f"{sum(bool(m['evidenced']) for m in stones)} of {len(stones)} milestones evidenced"]
    if placeholders > 3:
        comp_f.append(f"{placeholders} TODO/placeholder markers in the documentation")

    criteria = [
        CriterionResult(name="requirement_coverage", score=coverage, findings=cov_f),
        _architecture(corpus, readme_lower), _code_quality(corpus), _documentation(corpus, readme, extra_docs),
        _testing(corpus, readme_lower) if template.kind == "code" else
        CriterionResult(name="testing", score=None, findings=["Not applicable to a documentation project"]),
        CriterionResult(name="completeness", score=max(0, min(100, done)), findings=comp_f),
    ]
    if template.kind != "code":  # no source tree expected: architecture/quality judged on what a docs repo can show
        for c in criteria:
            if c.name in ("architecture", "code_quality"):
                c.score = None
                c.findings = ["Not applicable to a documentation project"]
    applicable = {c.name: c.score for c in criteria if c.score is not None}
    total_w = sum(WEIGHTS[n] for n in applicable)
    overall = round(sum(s * WEIGHTS[n] for n, s in applicable.items()) / total_w, 1)

    src_count = sum(p.lower().endswith(SOURCE_EXT) and not TEST_PATH.search(p) for p in paths)
    gates = [coverage >= 60, bool(readme.strip() or extra_docs.strip())]
    if template.kind == "code":
        gates.append(src_count >= 5)
    passed = overall >= pass_score and all(gates)

    improvements = [f"Show evidence for: {r['requirement']}" for r in reqs if not r["evidenced"]]
    for c in criteria:
        if c.score is not None and c.score < 60 and c.name != "requirement_coverage":
            detail = "; ".join(x for x in c.findings if x.startswith(("No ", "Not ", "Possible"))) or "see findings"
            improvements.append(f"Improve {c.name.replace('_', ' ')}: {detail}")
    if not gates[0]:
        improvements.append("Requirement coverage must reach at least 60% to pass")
    if template.kind == "code" and src_count < 5:
        improvements.append("The repository needs at least 5 source files to be assessed as a project")
    return Evaluation(
        overall_score=overall, passed=passed, criteria=criteria, requirements=reqs, milestones=stones,
        improvements=improvements,
        summary={"files": len(paths), "source_files": src_count, "readme_words": _words(readme),
                 "repo": evidence.repo_key if evidence else None, "head_sha": evidence.head_sha if evidence else None,
                 "tree_truncated": evidence.truncated if evidence else False, "pass_score": pass_score})
