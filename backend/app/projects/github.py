"""Public GitHub repository evidence (read-only, strictly allow-listed).

Only ``https://github.com/<owner>/<repo>`` URLs are accepted and only ``api.github.com`` is ever
contacted, with a fixed set of GET endpoints, short timeouts and size caps, so a submitted URL
can never be used to make the server fetch arbitrary hosts (SSRF). Repository code is never
downloaded or executed; only the file listing and the README are read.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.exceptions import InputValidationError, ServiceBusyError

logger = logging.getLogger(__name__)

_URL = re.compile(r"^https://github\.com/([A-Za-z0-9][A-Za-z0-9_.-]{0,38})/([A-Za-z0-9_.-]{1,100}?)(?:\.git)?/?$")
API = "https://api.github.com"
MAX_TREE_ENTRIES = 5000
MAX_README_BYTES = 200_000


@dataclass(frozen=True)
class RepoEvidence:
    repo_key: str  # github.com/owner/repo (lower-case)
    paths: list[str]
    readme: str
    default_branch: str
    head_sha: str | None
    truncated: bool


class RepoFetcher(Protocol):
    def fetch(self, owner: str, repo: str) -> RepoEvidence: ...


def parse_repo_url(url: str) -> tuple[str, str]:
    m = _URL.match(url.strip())
    if not m or m.group(2) in {".", ".."}:
        raise InputValidationError("Use a public GitHub repository URL like https://github.com/owner/repo")
    return m.group(1), m.group(2)


def repo_key(owner: str, repo: str) -> str:
    return f"github.com/{owner}/{repo}".lower()


class GitHubFetcher:
    def __init__(self, token: str = "", timeout: float = 10.0, client: httpx.Client | None = None) -> None:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "ai-career-coach"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = client or httpx.Client(base_url=API, headers=headers, timeout=timeout,
                                              follow_redirects=False)

    def _get(self, path: str, **kw: object) -> httpx.Response:
        try:
            resp = self._client.get(path, **kw)  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            logger.warning("github request failed", extra={"path": path})
            raise ServiceBusyError("GitHub is temporarily unavailable") from exc
        if resp.status_code == 404:
            raise InputValidationError("Repository not found or not public")
        if resp.status_code in (403, 429):
            raise ServiceBusyError("GitHub rate limit reached; try again later")
        if resp.status_code >= 400:
            raise ServiceBusyError("GitHub is temporarily unavailable")
        return resp

    def fetch(self, owner: str, repo: str) -> RepoEvidence:
        meta = self._get(f"/repos/{owner}/{repo}").json()
        if meta.get("private"):
            raise InputValidationError("Repository not found or not public")
        branch = str(meta.get("default_branch") or "main")
        tree = self._get(f"/repos/{owner}/{repo}/git/trees/{branch}", params={"recursive": "1"}).json()
        entries = [e["path"] for e in tree.get("tree", []) if e.get("type") == "blob"]
        truncated = bool(tree.get("truncated")) or len(entries) > MAX_TREE_ENTRIES
        try:
            readme = self._get(f"/repos/{owner}/{repo}/readme", headers={"Accept": "application/vnd.github.raw"}).text
        except InputValidationError:
            readme = ""  # a missing README is evidence, not an error
        return RepoEvidence(repo_key(owner, repo), entries[:MAX_TREE_ENTRIES], readme[:MAX_README_BYTES],
                            branch, tree.get("sha"), truncated)
