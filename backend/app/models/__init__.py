"""Import all models so ``Base.metadata`` is complete (used by Alembic and tests)."""

from app.models.accounts import GuestSession, User, UserProfile, UserSession
from app.models.achievements import (
    Certificate,
    Portfolio,
    PortfolioAchievement,
    ProjectEvaluation,
    ProjectSubmission,
)
from app.models.base import Base
from app.models.documents import (
    CareerAnalysis,
    Document,
    JobDescription,
    Report,
    Resume,
    SkillGapAnalysis,
)
from app.models.feedback import (
    AuditLog,
    Feedback,
    ModerationLog,
    Testimonial,
    TestimonialShareEvent,
)
from app.models.interview import InterviewAnswer, InterviewSession
from app.models.learning import (
    Assessment,
    AssessmentAttempt,
    AssessmentQuestion,
    Conversation,
    LearningActivity,
    LearningModule,
    LearningRoadmap,
    Message,
)

__all__ = [
    "Assessment",
    "AssessmentAttempt",
    "AssessmentQuestion",
    "AuditLog",
    "Base",
    "CareerAnalysis",
    "Certificate",
    "Conversation",
    "Document",
    "Feedback",
    "GuestSession",
    "InterviewAnswer",
    "InterviewSession",
    "JobDescription",
    "LearningActivity",
    "LearningModule",
    "LearningRoadmap",
    "Message",
    "ModerationLog",
    "Portfolio",
    "PortfolioAchievement",
    "ProjectEvaluation",
    "ProjectSubmission",
    "Report",
    "Resume",
    "SkillGapAnalysis",
    "Testimonial",
    "TestimonialShareEvent",
    "User",
    "UserProfile",
    "UserSession",
]
