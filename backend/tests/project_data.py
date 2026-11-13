"""Evidence builders for project tests (no network)."""

from __future__ import annotations

from app.projects.catalog import ProjectTemplate
from app.projects.github import RepoEvidence

GOOD_PATHS = [
    "README.md", "LICENSE", ".gitignore", ".env.example", "Dockerfile", "docker-compose.yml", "requirements.txt",
    "pyproject.toml", "ruff.toml", "mypy.ini", ".pre-commit-config.yaml", ".github/workflows/ci.yml",
    "docs/architecture.md", "docs/usage.md", "src/api/routes.py", "src/api/deps.py", "src/services/core_service.py",
    "src/services/other_service.py", "src/models/model.py", "src/core/config.py", "src/utils/helpers.py",
    "tests/conftest.py", "tests/test_api.py", "tests/test_service.py", "tests/test_models.py",
]


def keywords_text(t: ProjectTemplate) -> str:
    kws = [k for item in (*t.requirements, *t.milestones) for k in item.keywords]
    return " ".join(kws)


def good_readme(t: ProjectTemplate) -> str:
    sections = ("# Project\n## Installation\nInstall dependencies and set up the environment.\n"
                "## Usage\nHow to run the application locally.\n## Testing\nRun pytest to execute the test suite.\n"
                "## Architecture\nThe design is layered with api, services and models.\n"
                "## API and features\nEndpoints and features are described here.\n## License\nMIT license.\n")
    return sections + keywords_text(t) + " " + "detail " * 300


def ideal_evidence(t: ProjectTemplate, key: str = "github.com/acme/demo") -> RepoEvidence:
    return RepoEvidence(key, list(GOOD_PATHS), good_readme(t), "main", "abc123", False)


def poor_evidence(key: str = "github.com/acme/poor") -> RepoEvidence:
    return RepoEvidence(key, ["README.md", "main.py"], "# demo\nTODO TODO TODO TODO write docs", "main", "def456", False)


class FakeFetcher:
    def __init__(self, evidence: RepoEvidence | Exception) -> None:
        self.evidence, self.calls = evidence, []

    def fetch(self, owner: str, repo: str) -> RepoEvidence:
        self.calls.append((owner, repo))
        if isinstance(self.evidence, Exception):
            raise self.evidence
        return RepoEvidence(f"github.com/{owner}/{repo}".lower(), self.evidence.paths, self.evidence.readme,
                            self.evidence.default_branch, self.evidence.head_sha, self.evidence.truncated)
