from __future__ import annotations

import csv
import io
import re
import uuid
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import pymupdf
from sqlalchemy import select

from app.core.constants import SHARE_PLATFORMS
from app.models import AuditLog, Feedback, ModerationLog, Testimonial, TestimonialShareEvent
from tests.api.test_projects_certificates import admin_headers as _make_admin
from tests.api.test_projects_certificates import register
from tests.guest_fixtures import Env

U = "/api/v1"

def admin_headers(env: Env) -> dict[str, str]:
    """One admin per test environment (creating the same admin twice would violate uniqueness)."""
    if "admin_headers" not in env.db.info:
        env.db.info["admin_headers"] = _make_admin(env)
    return env.db.info["admin_headers"]  # type: ignore[no-any-return]
TEXT = "The 15 day roadmap and the mock interviews gave me a clear plan and real confidence."


def make(env: Env, h: dict[str, str], **extra: Any) -> dict[str, Any]:
    body = {"text": TEXT, "feature": "learning_roadmap", "rating": 5, "display_name": "Jane L.", **extra}
    r = env.client.post(f"{U}/testimonials", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def approve(env: Env, adm: dict[str, str], tid: str, action: str = "approve"):  # type: ignore[no-untyped-def]
    return env.client.post(f"{U}/admin/testimonials/{tid}/moderate", headers=adm, json={"action": action})


def live(env: Env, h: dict[str, str], **extra: Any) -> dict[str, Any]:
    """An approved, consented testimonial."""
    t = make(env, h, public_consent=True, **extra)
    assert approve(env, admin_headers(env), t["id"]).status_code == 200
    return t


# ---------------------------------------------------------------- ratings
def test_feedback_requires_a_user_and_validates_rating_and_feature(env: Env) -> None:
    guest, _ = env.new_guest()
    body = {"feature": "career_match", "rating": 4}
    assert env.client.post(f"{U}/feedback", json=body).status_code == 401
    assert env.client.post(f"{U}/feedback", headers=guest, json=body).status_code == 401
    h = register(env)
    for bad in ({"feature": "career_match", "rating": 0}, {"feature": "career_match", "rating": 6},
                {"feature": "nonsense", "rating": 3}):
        assert env.client.post(f"{U}/feedback", headers=h, json=bad).status_code == 422
    r = env.client.post(f"{U}/feedback", headers=h, json={**body, "comment": "<b>Useful</b>\x00"})
    assert r.status_code == 201 and r.json()["comment"] == "bUseful/b"
    assert len(env.client.get(f"{U}/feedback", headers=h).json()) == 1


def test_every_feature_is_accepted_and_daily_limit_applies(env: Env) -> None:
    h = register(env)
    from app.core.constants import FEEDBACK_FEATURES
    for f in FEEDBACK_FEATURES:
        assert env.client.post(f"{U}/feedback", headers=h, json={"feature": f, "rating": 4}).status_code == 201
    for _ in range(20 - len(FEEDBACK_FEATURES)):
        env.client.post(f"{U}/feedback", headers=h, json={"feature": "platform", "rating": 4})
    assert env.client.post(f"{U}/feedback", headers=h, json={"feature": "platform", "rating": 4}).status_code == 429


# ---------------------------------------------------------------- testimonials: creation and consent
def test_consent_defaults_to_false_and_nothing_is_public_until_approved(env: Env) -> None:
    h, adm = register(env), admin_headers(env)
    t = make(env, h)
    assert t["public_consent"] is False and t["status"] == "pending" and t["is_public"] is False
    assert env.client.get(f"{U}/testimonials/public").json() == []
    # consent alone is not enough
    t2 = make(env, h, public_consent=True)
    assert t2["is_public"] is False
    assert env.client.get(f"{U}/testimonials/public/{t2['id']}").status_code == 404
    # approval of a testimonial with no consent is refused
    assert approve(env, adm, t["id"]).status_code == 409
    assert approve(env, adm, t2["id"]).status_code == 200
    pub = env.client.get(f"{U}/testimonials/public").json()
    assert [p["id"] for p in pub] == [t2["id"]]


def test_validation_and_sanitising(env: Env) -> None:
    h = register(env)
    assert env.client.post(f"{U}/testimonials", headers=h, json={"text": "too short"}).status_code == 422
    assert env.client.post(f"{U}/testimonials", headers=h, json={"text": "x" * 1001}).status_code == 422
    assert env.client.post(f"{U}/testimonials", headers=h,
                           json={"text": TEXT, "feature": "twitter"}).status_code == 422
    t = make(env, h, text="<script>alert(1)</script> " + TEXT, display_name="<i>Jo</i>")
    assert "<" not in t["text"] and "<" not in t["display_name"]


def test_owner_isolation_and_limits(env: Env) -> None:
    a, b = register(env, "a@example.com"), register(env, "b@example.com")
    t = make(env, a)
    url = f"{U}/testimonials/{t['id']}"
    assert env.client.get(url, headers=b).status_code == 404
    assert env.client.patch(url, headers=b, json={"rating": 1}).status_code == 404
    assert env.client.delete(url, headers=b).status_code == 404
    assert env.client.get(f"{url}/share", headers=b).status_code == 404
    assert env.client.get(url).status_code == 401
    assert env.client.get(f"{U}/testimonials", headers=b).json() == []
    for _ in range(4):
        make(env, a)
    assert env.client.post(f"{U}/testimonials", headers=a, json={"text": TEXT}).status_code == 409


def test_edit_resets_moderation_and_unpublishes(env: Env) -> None:
    h = register(env)
    t = live(env, h)
    assert env.client.get(f"{U}/testimonials/public/{t['id']}").status_code == 200
    r = env.client.patch(f"{U}/testimonials/{t['id']}", headers=h, json={"text": TEXT + " Updated."})
    assert r.json()["status"] == "pending" and r.json()["is_public"] is False
    assert env.client.get(f"{U}/testimonials/public/{t['id']}").status_code == 404
    # an identical re-save does not reset anything
    t2 = live(env, h)
    same = env.client.patch(f"{U}/testimonials/{t2['id']}", headers=h, json={"text": TEXT})
    assert same.json()["status"] == "approved"


def test_withdrawal_is_immediate_and_reconsent_needs_new_review(env: Env) -> None:
    h, adm = register(env), admin_headers(env)
    t = live(env, h)
    r = env.client.post(f"{U}/testimonials/{t['id']}/withdraw-consent", headers=h)
    assert r.status_code == 200 and r.json()["is_public"] is False and r.json()["consent_withdrawn_at"]
    for path in ("", "/card.png"):
        assert env.client.get(f"{U}/testimonials/public/{t['id']}{path}").status_code == 404
    assert env.client.get(f"{U}/testimonials/public").json() == []
    assert env.client.get(f"{U}/testimonials/{t['id']}/share", headers=h).status_code == 409
    assert env.db.scalar(select(AuditLog).where(AuditLog.action == "testimonial.consent_withdrawn")) is not None
    # withdrawing twice is harmless
    assert env.client.post(f"{U}/testimonials/{t['id']}/withdraw-consent", headers=h).status_code == 200
    # fresh consent -> pending again, not public until re-approved
    r = env.client.patch(f"{U}/testimonials/{t['id']}", headers=h, json={"public_consent": True})
    assert r.json()["status"] == "pending" and r.json()["is_public"] is False and r.json()["consent_withdrawn_at"] is None
    assert approve(env, adm, t["id"]).status_code == 200
    assert env.client.get(f"{U}/testimonials/public/{t['id']}").status_code == 200


def test_consent_false_via_patch_withdraws(env: Env) -> None:
    h = register(env)
    t = live(env, h)
    r = env.client.patch(f"{U}/testimonials/{t['id']}", headers=h, json={"public_consent": False})
    assert r.json()["is_public"] is False and r.json()["consent_withdrawn_at"]


def test_delete_scrubs_text_and_hides_everywhere(env: Env) -> None:
    h, adm = register(env), admin_headers(env)
    t = live(env, h)
    assert env.client.delete(f"{U}/testimonials/{t['id']}", headers=h).status_code == 204
    assert env.client.get(f"{U}/testimonials/public/{t['id']}").status_code == 404
    assert env.client.get(f"{U}/testimonials", headers=h).json() == []
    row = env.db.get(Testimonial, uuid.UUID(t["id"]))
    env.db.refresh(row)
    assert row is not None and "roadmap" not in row.text and row.deleted_at is not None
    assert env.client.get(f"{U}/admin/testimonials/{t['id']}", headers=adm).status_code == 404


# ---------------------------------------------------------------- public view
def test_public_view_exposes_no_identity(env: Env) -> None:
    h = register(env)
    t = live(env, h, success_story="Landed an interview after the 60 day plan.", would_recommend=True)
    blob = env.client.get(f"{U}/testimonials/public/{t['id']}").text
    assert "u@example.com" not in blob and "Jane Learner" not in blob and "user_id" not in blob
    assert set(env.client.get(f"{U}/testimonials/public/{t['id']}").json()) == {
        "id", "text", "feature", "rating", "would_recommend", "success_story", "display_name"}
    anon = live(env, h, display_name=None)
    assert env.client.get(f"{U}/testimonials/public/{anon['id']}").json()["display_name"] == "Anonymous learner"
    assert env.client.get(f"{U}/testimonials/public/not-a-uuid").status_code == 422
    assert env.client.get(f"{U}/testimonials/public/{uuid.uuid4()}").status_code == 404


def test_public_stats(env: Env) -> None:
    h = register(env)
    assert env.client.get(f"{U}/feedback/stats").json() == {
        "ratings_count": 0, "average_rating": None, "testimonials_count": 0}
    env.client.post(f"{U}/feedback", headers=h, json={"feature": "platform", "rating": 5})
    env.client.post(f"{U}/feedback", headers=h, json={"feature": "platform", "rating": 4})
    live(env, h)
    s = env.client.get(f"{U}/feedback/stats").json()
    assert s == {"ratings_count": 2, "average_rating": 4.5, "testimonials_count": 1}


# ---------------------------------------------------------------- moderation
def test_moderation_is_admin_only(env: Env) -> None:
    h = register(env)
    t = make(env, h, public_consent=True)
    for method, path, kw in (("get", "/admin/testimonials", {}), ("get", f"/admin/testimonials/{t['id']}", {}),
                             ("post", f"/admin/testimonials/{t['id']}/moderate", {"json": {"action": "approve"}}),
                             ("get", "/admin/feedback/analytics", {}), ("get", "/admin/feedback/export.csv", {})):
        assert getattr(env.client, method)(f"{U}{path}", headers=h, **kw).status_code == 403, path
        assert getattr(env.client, method)(f"{U}{path}", **kw).status_code == 401, path


def test_moderation_transitions_history_and_audit(env: Env) -> None:
    h, adm = register(env), admin_headers(env)
    t = make(env, h, public_consent=True)
    tid = t["id"]
    assert approve(env, adm, tid, "approve").json()["status"] == "approved"
    assert approve(env, adm, tid, "approve").status_code == 409  # already approved
    assert approve(env, adm, tid, "flag").json()["status"] == "flagged"
    assert env.client.get(f"{U}/testimonials/public/{tid}").status_code == 404
    r = env.client.post(f"{U}/admin/testimonials/{tid}/moderate", headers=adm,
                        json={"action": "reject", "note": "Contains a promotional claim"})
    assert r.json()["status"] == "rejected"
    assert approve(env, adm, tid, "approve").json()["status"] == "approved"
    assert approve(env, adm, tid, "remove").json()["status"] == "removed"
    assert approve(env, adm, tid, "approve").status_code == 409  # removal is final
    assert env.client.patch(f"{U}/testimonials/{tid}", headers=h, json={"rating": 1}).status_code == 409
    hist = env.client.get(f"{U}/admin/testimonials/{tid}", headers=adm).json()["history"]
    assert [x["action"] for x in hist] == ["approve", "flag", "reject", "approve", "remove"]
    assert hist[2]["note"] == "Contains a promotional claim"
    assert len(env.db.scalars(select(ModerationLog)).all()) == 5
    assert env.db.scalar(select(AuditLog).where(AuditLog.action == "testimonial.remove")) is not None
    assert approve(env, adm, str(uuid.uuid4())).status_code == 404
    assert env.client.post(f"{U}/admin/testimonials/{tid}/moderate", headers=adm,
                           json={"action": "delete"}).status_code == 422


def test_queue_filter_and_review_hints(env: Env) -> None:
    h, adm = register(env), admin_headers(env)
    make(env, h, text="Visit www.cheap-jobs.com or mail me at spam@example.org now, call +91 98765 43210 anytime.")
    live(env, h)
    q = env.client.get(f"{U}/admin/testimonials?status=pending", headers=adm).json()
    assert len(q) == 1
    assert {"contains a link", "contains an email address", "contains a phone-like number",
            "no active public-display consent"} <= set(q[0]["review_hints"])
    assert len(env.client.get(f"{U}/admin/testimonials?status=approved", headers=adm).json()) == 1
    assert env.client.get(f"{U}/admin/testimonials?status=bogus", headers=adm).status_code == 422
    # hints never change status
    assert q[0]["status"] == "pending"


# ---------------------------------------------------------------- sharing
def test_share_links_are_limited_to_three_platforms_and_open_dialogs_only(env: Env) -> None:
    h = register(env)
    t = live(env, h)
    s = env.client.get(f"{U}/testimonials/{t['id']}/share", headers=h).json()
    assert tuple(s["links"]) == SHARE_PLATFORMS == ("linkedin", "whatsapp", "facebook")
    assert urlparse(s["links"]["linkedin"]).netloc == "www.linkedin.com"
    assert urlparse(s["links"]["whatsapp"]).netloc == "wa.me"
    assert urlparse(s["links"]["facebook"]).netloc == "www.facebook.com"
    assert s["public_url"] == f"http://localhost:5173/testimonials/{t['id']}"
    assert parse_qs(urlparse(s["links"]["linkedin"]).query)["url"] == [s["public_url"]]
    wa = unquote(urlparse(s["links"]["whatsapp"]).query)
    assert "roadmap" in wa and s["public_url"] in wa
    assert "never posts" in s["note"]
    for banned in ("twitter", "x.com", "t.me", "telegram"):
        assert banned not in str(s).lower()


def test_share_requires_public_testimonial(env: Env) -> None:
    h = register(env)
    t = make(env, h, public_consent=True)  # not yet approved
    assert env.client.get(f"{U}/testimonials/{t['id']}/share", headers=h).status_code == 409


def test_share_events_are_aggregate_only(env: Env) -> None:
    h = register(env)
    t = live(env, h)
    p = f"{U}/testimonials/public/{t['id']}/events"
    assert env.client.post(p, json={"event_type": "share_click", "platform": "linkedin"}).status_code == 204
    assert env.client.post(p, json={"event_type": "share_click", "platform": "facebook"}).status_code == 204
    assert env.client.post(p, json={"event_type": "card_download"}).status_code == 204
    assert env.client.post(p, json={"event_type": "link_copy"}).status_code == 204
    for bad in ({"event_type": "share_click", "platform": "twitter"}, {"event_type": "share_click", "platform": "telegram"},
                {"event_type": "share_click"}, {"event_type": "posted", "platform": "linkedin"}):
        assert env.client.post(p, json=bad).status_code == 422, bad
    cols = {c.name for c in TestimonialShareEvent.__table__.columns}
    assert cols == {"id", "testimonial_id", "platform", "event_type", "created_at"}  # no user / IP / device
    assert len(env.db.scalars(select(TestimonialShareEvent)).all()) == 4
    # hidden testimonials accept no events
    env.client.post(f"{U}/testimonials/{t['id']}/withdraw-consent", headers=h)
    assert env.client.post(p, json={"event_type": "link_copy"}).status_code == 404


# ---------------------------------------------------------------- PNG card
def test_card_is_a_branded_png(env: Env) -> None:
    h = register(env)
    t = live(env, h, text="<b>Great</b> platform & plan, " + TEXT)
    r = env.client.get(f"{U}/testimonials/public/{t['id']}/card.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    pix = pymupdf.Pixmap(r.content)
    assert (pix.width, pix.height) == (1200, 630)
    assert "attachment" in r.headers["content-disposition"]
    assert env.client.get(f"{U}/testimonials/public/{uuid.uuid4()}/card.png").status_code == 404


def test_card_handles_long_text_and_unicode_without_error(env: Env) -> None:
    from app.services.testimonial_card import excerpt, render_card
    long = "word " * 400
    assert len(excerpt(long)) <= 324 and excerpt(long).endswith("...")
    assert excerpt("short text") == "short text"
    for rating in (None, 1, 5):
        assert render_card(long, "Zoë 中文 <script>", rating)[:4] == b"\x89PNG"


# ---------------------------------------------------------------- analytics and export
def test_analytics_and_aggregate_export(env: Env) -> None:
    h, adm = register(env), admin_headers(env)
    for f, r in (("career_match", 5), ("career_match", 3), ("resume_optimizer", 4)):
        env.client.post(f"{U}/feedback", headers=h, json={"feature": f, "rating": r, "comment": "private words"})
    t = live(env, h)
    env.client.post(f"{U}/testimonials/public/{t['id']}/events", json={"event_type": "share_click", "platform": "whatsapp"})
    env.client.post(f"{U}/testimonials/public/{t['id']}/events", json={"event_type": "card_download"})
    a = env.client.get(f"{U}/admin/feedback/analytics", headers=adm).json()
    assert a["total_ratings"] == 3 and a["average_rating"] == 4.0
    assert {f["feature"]: (f["count"], f["average"]) for f in a["by_feature"]} == {
        "career_match": (2, 4.0), "resume_optimizer": (1, 4.0)}
    assert a["rating_distribution"] == {"1": 0, "2": 0, "3": 1, "4": 1, "5": 1}
    assert a["testimonials_by_status"]["approved"] == 1
    assert a["share_events"] == {"share_click": {"whatsapp": 1}, "card_download": {"none": 1}}
    r = env.client.get(f"{U}/admin/feedback/export.csv", headers=adm)
    assert r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["section", "key", "subkey", "value"]
    assert ["share_events", "share_click", "whatsapp", "1"] in rows
    for leak in ("private words", "u@example.com", "Jane", TEXT[:20]):
        assert leak not in r.text
    assert env.db.scalar(select(AuditLog).where(AuditLog.action == "feedback.exported")) is not None


def test_analytics_with_no_data(env: Env) -> None:
    adm = admin_headers(env)
    a = env.client.get(f"{U}/admin/feedback/analytics", headers=adm).json()
    assert a["total_ratings"] == 0 and a["average_rating"] is None and a["by_feature"] == []
    assert env.client.get(f"{U}/admin/feedback/export.csv", headers=adm).status_code == 200


# ---------------------------------------------------------------- erasure and rate limits
def test_account_deletion_erases_feedback_testimonials_events_and_logs(env: Env) -> None:
    h = register(env)
    env.client.post(f"{U}/feedback", headers=h, json={"feature": "platform", "rating": 5})
    t = live(env, h)
    env.client.post(f"{U}/testimonials/public/{t['id']}/events", json={"event_type": "link_copy"})
    r = env.client.request("DELETE", f"{U}/users/me", headers=h, json={"password": "Str0ng-passw0rd", "confirm": True})
    assert r.status_code == 204, r.text
    assert env.db.scalars(select(Testimonial)).all() == []
    assert env.db.scalars(select(Feedback)).all() == []
    assert env.db.scalars(select(TestimonialShareEvent)).all() == []
    assert env.db.scalars(select(ModerationLog)).all() == []
    assert env.client.get(f"{U}/testimonials/public/{t['id']}").status_code == 404


def test_public_endpoints_are_rate_limited(env: Env) -> None:
    from tests.guest_fixtures import build_env
    e = next(build_env(public_feedback_requests_per_minute=3))
    codes = [e.client.get(f"{U}/testimonials/public").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]


def test_no_unsupported_share_platform_anywhere_in_new_code() -> None:
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "app"
    for f in ("schemas/feedback.py", "services/feedback_service.py", "api/routes/feedback.py",
              "services/testimonial_card.py"):
        text = (root / f).read_text(encoding="utf-8").lower()
        assert not re.search(r"twitter|telegram|t\.me|x\.com", text), f
