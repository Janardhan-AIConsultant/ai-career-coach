"""Career Achievement Portfolio.

The portfolio is *derived*, never typed in: ``sync_portfolio`` rebuilds achievement items from
verified platform records (completed roadmaps, passed assessments, valid certificates, passed
project reviews). There is deliberately no endpoint to add a custom item, so nothing - and in
particular no employment history - can be fabricated. Every skill is classified as
``learned`` (completed learning), ``assessed`` (passed an assessment) or ``demonstrated`` (a passed
project review), and every output repeats that this is learning evidence, not employment experience.

Privacy: portfolios start private. Publishing needs explicit consent, a display name chosen by the
owner and produces a random, unguessable slug. Items and sections can be hidden individually;
withdrawing consent makes the public URL 404 immediately. The public view never contains an email,
user id or internal id.
"""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assessments.bank import ASSESSMENT_SKILLS
from app.core.config import Settings
from app.core.exceptions import ConflictError, InputValidationError, NotFoundError
from app.models import (
    Assessment,
    AssessmentAttempt,
    AuditLog,
    Certificate,
    LearningActivity,
    LearningModule,
    LearningRoadmap,
    Portfolio,
    PortfolioAchievement,
    ProjectEvaluation,
    ProjectSubmission,
    User,
)
from app.projects.catalog import BY_ID as PROJECT_TEMPLATES
from app.schemas.portfolio import (
    SECTIONS,
    ItemOut,
    LinkedInCertification,
    LinkedInOut,
    PortfolioOut,
    PublicItem,
    PublicPortfolio,
    SettingsIn,
    SettingsOut,
    SkillEvidenceOut,
    StatsOut,
)

RANK = {"learned": 0, "assessed": 1, "demonstrated": 2}
LEVEL_LABEL = {"learned": "learned", "assessed": "assessed", "demonstrated": "practically demonstrated"}
KIND_SECTION = {"learning_path": "learning_paths", "assessment": "assessments",
                "certificate": "certificates", "project": "projects"}
CERT_LEVEL = {"learning_completion": "learned", "assessment": "assessed", "project_completion": "demonstrated"}
_SLUG_ALPHABET = "abcdefghjkmnpqrstvwxyz23456789"
SLUG_RE = re.compile(r"^[a-z0-9]{10}$")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MARKUP = re.compile(r"[<>]")


def _norm(skill: str) -> str:
    return " ".join(skill.lower().replace("_", " ").split())


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def clean_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(_MARKUP.sub("", _CTRL.sub(" ", value)).split())[:limit]
    return text or None


def new_slug(db: Session) -> str:
    while True:
        slug = "".join(secrets.choice(_SLUG_ALPHABET) for _ in range(10))
        if db.scalar(select(Portfolio.id).where(Portfolio.public_slug == slug)) is None:
            return slug


# ====================================================================== derivation (no settings needed)
def _cert_skills(db: Session, c: Certificate) -> list[str]:
    if c.roadmap_id:
        r = db.get(LearningRoadmap, c.roadmap_id)
        return [_norm(s) for s in (r.focus_skills or [])] if r else []
    if c.attempt_id:
        a = db.get(AssessmentAttempt, c.attempt_id)
        asm = db.get(Assessment, a.assessment_id) if a else None
        return list(ASSESSMENT_SKILLS.get(asm.slug or "", [])) if asm else []
    if c.evaluation_id:
        ev = db.get(ProjectEvaluation, c.evaluation_id)
        sub = db.get(ProjectSubmission, ev.submission_id) if ev else None
        tpl = PROJECT_TEMPLATES.get(sub.template_id or "") if sub else None
        return [_norm(s) for s in tpl.skills] if tpl else []
    return []


def _desired(db: Session, user_id: uuid.UUID) -> dict[tuple[str, uuid.UUID], dict[str, Any]]:
    out: dict[tuple[str, uuid.UUID], dict[str, Any]] = {}
    for r in db.scalars(select(LearningRoadmap).where(
            LearningRoadmap.user_id == user_id, LearningRoadmap.status == "completed",
            LearningRoadmap.deleted_at.is_(None))).all():
        done = db.scalar(select(func.count()).select_from(LearningActivity).join(
            LearningModule, LearningActivity.module_id == LearningModule.id).where(
            LearningModule.roadmap_id == r.id, LearningActivity.completed_at.is_not(None))) or 0
        out[("learning_path", r.id)] = {
            "title": r.title, "level": "learned", "skills": [_norm(s) for s in (r.focus_skills or [])],
            "achieved_at": _aware(r.completed_at or r.updated_at),
            "details": {"duration_days": r.duration_days, "activities_completed": done,
                        "estimated_hours": r.estimated_hours}}
    best: dict[uuid.UUID, AssessmentAttempt] = {}
    for a in db.scalars(select(AssessmentAttempt).where(
            AssessmentAttempt.user_id == user_id, AssessmentAttempt.passed.is_(True))).all():
        if a.assessment_id not in best or a.score > best[a.assessment_id].score:
            best[a.assessment_id] = a
    for aid, a in best.items():
        asm = db.get(Assessment, aid)
        if asm:
            out[("assessment", aid)] = {
                "title": asm.title, "level": "assessed", "skills": list(ASSESSMENT_SKILLS.get(asm.slug or "", [_norm(asm.topic)])),
                "achieved_at": _aware(a.submitted_at),
                "details": {"score": a.score, "pass_score": asm.pass_score, "assessment": asm.slug}}
    for c in db.scalars(select(Certificate).where(Certificate.user_id == user_id, Certificate.status == "valid")).all():
        out[("certificate", c.id)] = {
            "title": f"{c.title}: {c.topic}", "level": CERT_LEVEL[c.certificate_type], "skills": _cert_skills(db, c),
            "achieved_at": _aware(c.issued_at),
            "details": {"certificate_id": c.certificate_code, "certificate_type": c.certificate_type, "score": c.score}}
    for sub in db.scalars(select(ProjectSubmission).where(
            ProjectSubmission.user_id == user_id, ProjectSubmission.deleted_at.is_(None))).all():
        ev = db.scalar(select(ProjectEvaluation).where(
            ProjectEvaluation.submission_id == sub.id, ProjectEvaluation.passed.is_(True))
            .order_by(ProjectEvaluation.created_at.desc()).limit(1))
        tpl = PROJECT_TEMPLATES.get(sub.template_id or "")
        if ev and tpl:
            out[("project", sub.id)] = {
                "title": sub.title, "level": "demonstrated", "skills": [_norm(s) for s in tpl.skills],
                "achieved_at": _aware(ev.created_at),
                "details": {"score": ev.overall_score, "repo_url": sub.repo_url, "documentation_url": sub.documentation_url,
                            "review": "Automated static review of the submitted evidence; the code was not executed."}}
    return out


def get_or_create(db: Session, user_id: uuid.UUID) -> Portfolio:
    pf = db.scalar(select(Portfolio).where(Portfolio.user_id == user_id, Portfolio.deleted_at.is_(None)))
    if pf is None:
        pf = Portfolio(user_id=user_id, visibility="private", section_visibility={s: True for s in SECTIONS},
                       resume_integration_approved=False)
        db.add(pf)
        db.flush()
    return pf


def sync_portfolio(db: Session, pf: Portfolio) -> None:
    """Rebuild items from verified records; keeps the owner's per-item visibility choices."""
    desired = _desired(db, pf.user_id)
    existing = {(a.source_type, a.source_id): a for a in db.scalars(
        select(PortfolioAchievement).where(PortfolioAchievement.portfolio_id == pf.id)).all()}
    for key, d in desired.items():
        row = existing.get(key)
        if row is None:
            row = PortfolioAchievement(portfolio_id=pf.id, kind=key[0], source_type=key[0], source_id=key[1],
                                       is_visible=True, title="", evidence_level="learned",
                                       achieved_at=d["achieved_at"])
            db.add(row)
        row.kind, row.title, row.evidence_level = key[0], d["title"][:200], d["level"]
        row.skill = (d["skills"][0] if d["skills"] else None)
        row.achieved_at = d["achieved_at"]
        row.details = {**d["details"], "skills": d["skills"]}
    for old_key, row in existing.items():
        if old_key not in desired:  # source no longer qualifies (certificate revoked, project deleted, ...)
            db.delete(row)
    db.flush()


def touch_portfolio(db: Session, user_id: uuid.UUID) -> None:
    """Automatic update hook: refresh the user's portfolio, if they have one, after a qualifying event."""
    pf = db.scalar(select(Portfolio).where(Portfolio.user_id == user_id, Portfolio.deleted_at.is_(None)))
    if pf is not None:
        sync_portfolio(db, pf)


# ====================================================================== views
def _skills_from(items: list[ItemOut] | list[PublicItem]) -> list[SkillEvidenceOut]:
    acc: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        for s in it.skills:
            acc.setdefault(s, []).append({"kind": it.kind, "title": it.title, "level": it.evidence_level,
                                          "achieved_at": it.achieved_at.isoformat()})
    out = []
    for skill, ev in acc.items():
        levels = sorted({e["level"] for e in ev}, key=lambda lv: RANK[lv])
        out.append(SkillEvidenceOut(skill=skill, levels=levels, highest=levels[-1],
                                    evidence=sorted(ev, key=lambda e: e["achieved_at"], reverse=True)))
    return sorted(out, key=lambda s: (-RANK[s.highest], s.skill))


class PortfolioService:
    def __init__(self, db: Session, settings: Settings, user: User) -> None:
        self._db, self._s, self._user = db, settings, user

    def _url(self, slug: str) -> str:
        return f"{self._s.frontend_url.rstrip('/')}/portfolio/{slug}"

    def _cert_url(self, code: str) -> str:
        return f"{self._s.frontend_url.rstrip('/')}/verify/{code}"

    def _details(self, row: PortfolioAchievement) -> dict[str, Any]:
        d = {k: v for k, v in (row.details or {}).items() if k != "skills"}
        if row.kind == "certificate":
            d["verification_url"] = self._cert_url(d["certificate_id"])
        return d

    def _item(self, row: PortfolioAchievement) -> ItemOut:
        return ItemOut(id=row.id, kind=row.kind, title=row.title, evidence_level=row.evidence_level,
                       skills=list((row.details or {}).get("skills", [])), achieved_at=row.achieved_at,
                       is_visible=row.is_visible, details=self._details(row))

    def _rows(self, pf: Portfolio) -> list[PortfolioAchievement]:
        return list(self._db.scalars(select(PortfolioAchievement).where(
            PortfolioAchievement.portfolio_id == pf.id).order_by(PortfolioAchievement.achieved_at.desc())).all())

    def _settings_out(self, pf: Portfolio) -> SettingsOut:
        return SettingsOut(
            visibility=pf.visibility, public_slug=pf.public_slug,
            public_url=self._url(pf.public_slug) if pf.visibility == "public" and pf.public_slug else None,
            display_name=pf.display_name, headline=pf.headline, summary=pf.summary,
            section_visibility={**{s: True for s in SECTIONS}, **(pf.section_visibility or {})},
            resume_integration_approved=pf.resume_integration_approved,
            consent_at=pf.consent_at and _aware(pf.consent_at))

    def _stats(self, items: list[ItemOut]) -> StatsOut:
        acts = self._db.execute(
            select(func.count(), func.coalesce(func.sum(LearningActivity.estimated_minutes), 0))
            .select_from(LearningActivity).join(LearningModule, LearningActivity.module_id == LearningModule.id)
            .join(LearningRoadmap, LearningModule.roadmap_id == LearningRoadmap.id)
            .where(LearningRoadmap.user_id == self._user.id, LearningRoadmap.deleted_at.is_(None),
                   LearningActivity.completed_at.is_not(None))).one()

        def count(kind: str) -> int:
            return sum(i.kind == kind for i in items)

        return StatsOut(learning_paths_completed=count("learning_path"), activities_completed=int(acts[0] or 0),
                        estimated_learning_hours=round(int(acts[1] or 0) / 60, 1), assessments_passed=count("assessment"),
                        certificates=count("certificate"), projects_passed=count("project"))

    def view(self) -> PortfolioOut:
        pf = get_or_create(self._db, self._user.id)
        sync_portfolio(self._db, pf)
        self._db.commit()
        items = [self._item(r) for r in self._rows(pf)]
        return PortfolioOut(settings=self._settings_out(pf), timeline=items,
                            skills=_skills_from([i for i in items if i.is_visible]), stats=self._stats(items))

    # ------------------------------------------------------------ settings
    def update_settings(self, body: SettingsIn) -> PortfolioOut:
        pf = get_or_create(self._db, self._user.id)
        name = clean_text(body.display_name, 80) if body.display_name is not None else pf.display_name
        publishing = body.visibility == "public" and pf.visibility != "public"
        if publishing:  # validate everything BEFORE changing anything
            if not body.consent_public:
                raise InputValidationError("Explicit consent is required to publish your portfolio")
            if not name:
                raise InputValidationError("Choose a public display name before publishing")
        pf.display_name = name
        if body.headline is not None:
            pf.headline = clean_text(body.headline, 160)
        if body.summary is not None:
            pf.summary = clean_text(body.summary, 1000)
        if body.section_visibility:
            pf.section_visibility = {**{s: True for s in SECTIONS}, **(pf.section_visibility or {}), **body.section_visibility}
        if publishing:
            pf.visibility, pf.consent_at = "public", datetime.now(UTC)
            pf.public_slug = pf.public_slug or new_slug(self._db)
            self._audit("portfolio.published", pf)
        elif body.visibility == "private" and pf.visibility != "private":
            pf.visibility = "private"  # consent withdrawn: the public URL stops working at once
            self._audit("portfolio.unpublished", pf)
        self._db.commit()
        return self.view()

    def rotate_slug(self) -> PortfolioOut:
        pf = get_or_create(self._db, self._user.id)
        pf.public_slug = new_slug(self._db)
        self._audit("portfolio.slug_rotated", pf)
        self._db.commit()
        return self.view()

    def set_item_visibility(self, item_id: uuid.UUID, visible: bool) -> PortfolioOut:
        pf = get_or_create(self._db, self._user.id)
        row = self._db.scalar(select(PortfolioAchievement).where(
            PortfolioAchievement.id == item_id, PortfolioAchievement.portfolio_id == pf.id))
        if row is None:
            raise NotFoundError()
        row.is_visible = visible
        self._db.commit()
        return self.view()

    def set_resume_integration(self, approve: bool) -> None:
        pf = get_or_create(self._db, self._user.id)
        pf.resume_integration_approved = approve
        self._audit("portfolio.resume_integration_approved" if approve else "portfolio.resume_integration_withdrawn", pf)
        self._db.commit()

    def _audit(self, action: str, pf: Portfolio) -> None:
        self._db.add(AuditLog(actor_user_id=self._user.id, action=action, entity_type="portfolio", entity_id=str(pf.id)))

    # ------------------------------------------------------------ outputs for the owner
    def _visible_items(self) -> list[ItemOut]:
        return [i for i in self.view().timeline if i.is_visible]

    def resume_section(self) -> str:
        pf = get_or_create(self._db, self._user.id)
        if not pf.resume_integration_approved:
            raise ConflictError("Portfolio-to-resume integration has not been approved")
        lines = ["LEARNING AND CERTIFICATIONS (platform-based learning - not employment experience)"]
        for i in sorted(self._visible_items(), key=lambda i: i.achieved_at, reverse=True):
            d = i.details
            if i.kind == "certificate":
                lines.append(f"- {i.title} (ID {d['certificate_id']}; verify at {d['verification_url']})")
            elif i.kind == "assessment":
                lines.append(f"- Passed assessment: {i.title} (score {d['score']:g}%)")
            elif i.kind == "project":
                lines.append(f"- Practical project: {i.title}" + (f" - {d['repo_url']}" if d.get("repo_url") else ""))
            else:
                lines.append(f"- Completed learning plan: {i.title}")
        return "\n".join(lines)

    def linkedin(self) -> LinkedInOut:
        items = self._visible_items()
        stats = self._stats(items)
        skills = _skills_from(items)
        about = [(
            "Learning highlights from the AI Career Coach platform (platform-based learning, not employment): "
            f"{stats.learning_paths_completed} learning plan(s) completed ({stats.estimated_learning_hours:g} study hours), "
            f"{stats.assessments_passed} assessment(s) passed, {stats.certificates} platform certificate(s), "
            f"{stats.projects_passed} practical project(s) reviewed."
        )]
        if skills:
            about.append("Skills with evidence: " + "; ".join(
                f"{s.skill} ({', '.join(LEVEL_LABEL[lv] for lv in s.levels)})" for s in skills[:20]) + ".")
        certs = [LinkedInCertification(
            name=i.title[:100], issuing_organization="AI Career Coach (platform-issued)",
            issue_date=i.achieved_at.strftime("%Y-%m"), credential_id=i.details["certificate_id"],
            credential_url=i.details["verification_url"]) for i in items if i.kind == "certificate"]
        return LinkedInOut(
            about=" ".join(about)[:2600], certifications=certs,
            notes=["Nothing is posted to LinkedIn automatically; copy this text yourself.",
                   "Certificates are platform-issued, not externally accredited qualifications.",
                   "These are learning achievements, not job experience: do not add them under Experience."])

    # ------------------------------------------------------------ public view
    @staticmethod
    def public_view(db: Session, settings: Settings, slug: str) -> PublicPortfolio:
        if not SLUG_RE.match(slug or ""):
            raise NotFoundError()
        pf = db.scalar(select(Portfolio).where(Portfolio.public_slug == slug, Portfolio.deleted_at.is_(None)))
        owner = db.get(User, pf.user_id) if pf else None
        if pf is None or pf.visibility != "public" or not pf.display_name or owner is None or owner.deleted_at is not None:
            raise NotFoundError()  # private, withdrawn, deleted and unknown look identical
        svc = PortfolioService(db, settings, owner)
        sections = {**{s: True for s in SECTIONS}, **(pf.section_visibility or {})}
        shown: list[PublicItem] = []
        for row in svc._rows(pf):
            if not row.is_visible or not sections.get(KIND_SECTION[row.kind], False):
                continue
            d = svc._details(row)
            if not sections["scores"]:
                d.pop("score", None)
            shown.append(PublicItem(kind=row.kind, title=row.title, evidence_level=row.evidence_level,
                                    skills=list((row.details or {}).get("skills", [])),
                                    achieved_at=row.achieved_at, details=d))
        return PublicPortfolio(
            display_name=pf.display_name, headline=pf.headline,
            summary=pf.summary if sections["summary"] else None,
            timeline=shown if sections["timeline"] else [],
            skills=_skills_from(shown) if sections["skills"] else [])
