"""Domain constants. Single source of truth for closed value sets (also used in DB CHECKs)."""

from __future__ import annotations

# Only these roadmap durations (days) are supported anywhere in the system.
ROADMAP_DURATIONS: tuple[int, ...] = (7, 15, 60)

# Only these social platforms are supported for testimonial sharing.
SHARE_PLATFORMS: tuple[str, ...] = ("linkedin", "whatsapp", "facebook")
SHARE_EVENT_TYPES: tuple[str, ...] = ("share_click", "card_download", "link_copy")

USER_ROLES: tuple[str, ...] = ("user", "admin")
DOCUMENT_KINDS: tuple[str, ...] = ("resume", "job_description")
MESSAGE_ROLES: tuple[str, ...] = ("user", "assistant")
QUESTION_TYPES: tuple[str, ...] = ("mcq", "multi_select", "technical", "scenario", "practical")
DIFFICULTIES: tuple[str, ...] = ("beginner", "intermediate", "advanced")
CERTIFICATE_TYPES: tuple[str, ...] = ("learning_completion", "assessment", "project_completion")
CERTIFICATE_STATUSES: tuple[str, ...] = ("valid", "revoked")
EVIDENCE_LEVELS: tuple[str, ...] = ("learned", "assessed", "demonstrated")
PORTFOLIO_VISIBILITY: tuple[str, ...] = ("private", "public")
FEEDBACK_FEATURES: tuple[str, ...] = (
    "platform",
    "resume_analyzer",
    "job_description_analyzer",
    "career_match",
    "resume_optimizer",
    "interview_preparation",
    "ai_career_coach",
    "learning_roadmap",
)
TESTIMONIAL_STATUSES: tuple[str, ...] = ("pending", "approved", "rejected", "flagged", "removed")
MODERATION_ACTIONS: tuple[str, ...] = ("approve", "reject", "flag", "remove")

REPORT_TYPES: tuple[str, ...] = (
    "resume_analysis",
    "job_description_analysis",
    "career_match",
    "skill_gap",
    "resume_optimization",
    "interview_preparation",
    "learning_roadmap",
    "assessment",
    "certificate",
    "portfolio",
)
REPORT_FORMATS: tuple[str, ...] = ("pdf", "docx")
