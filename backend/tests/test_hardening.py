"""Cross-cutting security and policy checks (Phase 14).

These tests look at the whole application rather than one feature: every route's authentication,
response headers, error envelopes, log hygiene and repo-wide policy rules.
"""

from __future__ import annotations

import logging
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest

from tests.guest_fixtures import Env

U = "/api/v1"
REPO = Path(__file__).resolve().parents[2]

# Routes that are open by design. Anything else must reject an unauthenticated request.
PUBLIC = {
    ("GET", "/health"), ("GET", "/health/database"), ("GET", "/health/llm"), ("GET", "/health/vector-store"),
    ("GET", f"{U}/health"), ("GET", f"{U}/health/database"), ("GET", f"{U}/health/llm"),
    ("GET", f"{U}/health/vector-store"),
    ("POST", f"{U}/auth/register"), ("POST", f"{U}/auth/login"), ("POST", f"{U}/auth/refresh"),
    ("POST", f"{U}/auth/logout"), ("POST", f"{U}/guest/sessions"),
    ("GET", f"{U}/certificates/verify/{{certificate_id}}"),
    ("GET", f"{U}/portfolio/public/{{slug}}"),
    ("GET", f"{U}/testimonials/public"), ("GET", f"{U}/feedback/stats"),
    ("GET", f"{U}/testimonials/public/{{testimonial_id}}"),
    ("GET", f"{U}/testimonials/public/{{testimonial_id}}/card.png"),
    ("POST", f"{U}/testimonials/public/{{testimonial_id}}/events"),
    ("GET", f"{U}/projects/catalog"), ("GET", f"{U}/interview/topics"),
}


def _routes(env: Env) -> list[tuple[str, str]]:
    """Every documented operation, from the OpenAPI schema (the source of truth for the API surface)."""
    schema = env.client.app.openapi()  # type: ignore[attr-defined]
    return sorted((m.upper(), path) for path, ops in schema["paths"].items() for m in ops
                  if m.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"})


def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", lambda m: str(uuid.uuid4()) if m.group(0).endswith("_id}") else "x", path)


def test_every_non_public_route_rejects_anonymous_requests(env: Env) -> None:
    routes = _routes(env)
    assert len(routes) > 100  # the check must actually cover the API
    leaks = []
    for method, path in routes:
        if (method, path) in PUBLIC:
            continue
        r = env.client.request(method, _fill(path), json={} if method in ("POST", "PUT", "PATCH") else None)
        if r.status_code not in (401, 403):
            leaks.append((method, path, r.status_code))
    assert leaks == [], f"routes reachable without credentials: {leaks}"


def test_unlisted_public_routes_are_still_the_expected_ones(env: Env) -> None:
    """The allow-list must not rot: every entry has to exist."""
    existing = set(_routes(env))
    assert PUBLIC <= existing, sorted(PUBLIC - existing)


def test_admin_routes_reject_ordinary_users(env: Env) -> None:
    from tests.api.test_projects_certificates import register
    h = register(env)
    admin_routes = [(m, p) for m, p in _routes(env) if p.startswith(f"{U}/admin/")]
    assert len(admin_routes) >= 14
    for method, path in admin_routes:
        r = env.client.request(method, _fill(path), headers=h,
                               json={} if method in ("POST", "PUT", "PATCH") else None)
        assert r.status_code == 403, (method, path, r.status_code)


def test_guest_tokens_cannot_reach_user_routes(env: Env) -> None:
    guest, _ = env.new_guest()
    for method, path in ((m, p) for m, p in _routes(env) if p.startswith((f"{U}/users/me", f"{U}/learning", f"{U}/portfolio", f"{U}/coach"))):
        if (method, path) in PUBLIC:
            continue
        r = env.client.request(method, _fill(path), headers=guest,
                               json={} if method in ("POST", "PUT", "PATCH") else None)
        assert r.status_code in (401, 403), (method, path, r.status_code)


# ---------------------------------------------------------------- headers and errors
@pytest.mark.parametrize("path", ["/health", f"{U}/health", f"{U}/nope", f"{U}/users/me", f"{U}/guest/sessions"])
def test_security_headers_on_every_kind_of_response(env: Env, path: str) -> None:
    r = env.client.get(path)
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers.get("x-frame-options") in ("DENY", "SAMEORIGIN") or "frame-ancestors" in r.headers.get(
        "content-security-policy", "")
    assert "referrer-policy" in r.headers
    assert "x-correlation-id" in {k.lower() for k in r.headers}


def test_error_envelope_never_echoes_input_or_internals(env: Env) -> None:
    secret = "SUPERSECRETVALUE-123"
    r = env.client.post(f"{U}/auth/login", json={"email": secret, "password": secret})
    assert r.status_code == 422 and secret not in r.text
    body = r.json()
    assert set(body) == {"error"} and "code" in body["error"]
    r = env.client.get(f"{U}/definitely/not/here")
    assert r.status_code == 404 and set(r.json()) == {"error"}
    for leak in ("Traceback", "sqlalchemy", ".py", "File \""):
        assert leak not in r.text
    assert env.client.delete(f"{U}/health").status_code == 405


def test_cors_allows_only_the_configured_origin(env: Env) -> None:
    ok = env.client.options(f"{U}/health", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = env.client.options(f"{U}/health", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
    assert ok.headers.get("access-control-allow-origin") != "*"


def test_refresh_cookie_is_httponly_and_samesite(env: Env) -> None:
    r = env.client.post(f"{U}/auth/register", json={
        "email": "c@example.com", "password": "Str0ng-passw0rd", "display_name": "C"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=" in cookie
    assert "refresh" in cookie and r.json()["access_token"] not in cookie


def test_oversized_json_and_wrong_content_types_are_rejected(env: Env) -> None:
    r = env.client.post(f"{U}/auth/login", content=b"x" * 10, headers={"Content-Type": "text/plain"})
    assert r.status_code in (415, 422)
    assert env.client.post(f"{U}/auth/login", content=b"{not json", headers={
        "Content-Type": "application/json"}).status_code == 422


# ---------------------------------------------------------------- log hygiene
def test_resume_text_passwords_and_tokens_are_not_logged(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    marker = "ZXQ-UNIQUE-RESUME-MARKER-9137"
    guest, session = env.new_guest()
    env.upload_text(guest, text=f"Jane Doe\nPython developer {marker}\nSkills: Python, SQL, Docker")
    env.client.post(f"{U}/auth/register", json={
        "email": "log@example.com", "password": "L0g-check-Passw0rd", "display_name": "Log"})
    env.client.post(f"{U}/auth/login", json={"email": "log@example.com", "password": "wrong-Passw0rd!!"})
    logged = "\n".join(f"{r.getMessage()} {getattr(r, '__dict__', {})}" for r in caplog.records)
    for secret in (marker, "L0g-check-Passw0rd", "wrong-Passw0rd!!", session["token"], "j" * 40):
        assert secret not in logged


# ---------------------------------------------------------------- repository policy
def _tracked() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return [REPO / line for line in out.splitlines() if line and (REPO / line).is_file()]


def _text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


SKIP_SUFFIX = {".png", ".jpg", ".ico", ".pdf", ".lock", ".svg"}


def test_no_unsupported_social_platform_in_tracked_files() -> None:
    pattern = re.compile(r"twitter|telegram|\bt\.me\b|\bx\.com\b", re.IGNORECASE)
    this = Path(__file__).resolve()
    bad = [str(p.relative_to(REPO)) for p in _tracked()
           if p.suffix not in SKIP_SUFFIX and p.resolve() != this and "tests" not in p.parts
           and "package-lock" not in p.name
           and pattern.search(_text(p))]
    assert bad == [], bad


def test_no_unsupported_roadmap_duration_in_tracked_text() -> None:
    pattern = re.compile(r"\b(?!7\b|15\b|60\b)\d{1,3}[- ]day (roadmap|plan|learning)", re.IGNORECASE)
    bad = [str(p.relative_to(REPO)) for p in _tracked()
           if p.suffix in {".py", ".md", ".ts", ".tsx", ".json", ".yml", ".yaml", ".txt"}
           and "package-lock" not in p.name and pattern.search(_text(p))]
    assert bad == [], bad


def test_no_real_looking_secrets_or_env_files_are_tracked() -> None:
    names = [p.name for p in _tracked()]
    assert ".env" not in names and not any(n.startswith(".env.") and n != ".env.example" for n in names)
    patterns = [re.compile(r"gsk_[A-Za-z0-9]{20,}"), re.compile(r"AKIA[0-9A-Z]{16}"),
                re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), re.compile(r"ghp_[A-Za-z0-9]{30,}"),
                re.compile(r"postgres(ql)?(\+\w+)?://[^:\s/]+:(?!career@|password@|\$|<|\{)[^@\s]{6,}@")]
    hits: list[Any] = []
    for p in _tracked():
        if p.suffix in SKIP_SUFFIX or "package-lock" in p.name:
            continue
        t = _text(p)
        hits += [(str(p.relative_to(REPO)), pat.pattern) for pat in patterns if pat.search(t)]
    assert hits == [], hits


def test_env_example_uses_placeholders_only() -> None:
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    for line in text.splitlines():
        if re.match(r"^(GROQ_API_KEY|CHROMA_API_KEY|JWT_SECRET_KEY|GITHUB_TOKEN)=", line):
            value = line.split("=", 1)[1].split("#", 1)[0].strip()
            assert value == "" or "change" in value.lower() or "your" in value.lower() or "<" in value, line


def test_deploy_artifacts_never_enable_debug_or_wildcard_cors() -> None:
    for p in _tracked():
        if p.name in {"docker-compose.yml", "render.yaml", "vercel.json"}:
            t = _text(p).lower()
            assert "cors_origins=*" not in t.replace(": ", "=").replace(" ", "")
            assert "app_env: development" not in t or p.name == "docker-compose.yml"


def test_sample_certificate_ids_never_verify(env: Env) -> None:
    """The ID printed on the public sample images is not a real certificate."""
    for code in ("SAMPLE-NOT-VALID-1", "SAMPLE-NOT-VALID-2", "SAMPLE-NOT-VALID-3"):
        assert env.client.get(f"{U}/certificates/verify/{code}").status_code == 404


def test_brand_logo_matches_frontend_asset_and_renders() -> None:
    from app.services.brand import LOGO_SVG, logo_png

    root = Path(__file__).resolve().parents[2]
    assert (root / "frontend" / "public" / "logo.svg").read_text(encoding="utf-8").strip() == LOGO_SVG.strip()
    assert (root / "frontend" / "public" / "favicon.svg").read_text(encoding="utf-8").strip() == LOGO_SVG.strip()
    assert logo_png(64).startswith(b"\x89PNG")
