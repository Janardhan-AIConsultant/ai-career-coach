"""Learning roadmaps (7, 15 or 60 days) and assessments for registered users."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import CurrentUser, DbSession, SettingsDep, get_object_storage
from app.schemas.learning import (
    AssessmentDetail,
    AssessmentSummary,
    AttemptSummary,
    DashboardOut,
    ReportCreated,
    ReportRequest,
    RoadmapCreateIn,
    RoadmapOut,
    RoadmapSummary,
    SubmitIn,
    SubmitOut,
)
from app.services.assessment_service import AssessmentService
from app.services.learning_service import LearningService
from app.services.object_storage import ObjectStorage

router = APIRouter(tags=["learning"])
Storage = Annotated[ObjectStorage, Depends(get_object_storage)]


def _learning(db: DbSession, storage: Storage, settings: SettingsDep, user: CurrentUser) -> LearningService:
    return LearningService(db, storage, settings, user)


Learning = Annotated[LearningService, Depends(_learning)]


def _assessments(db: DbSession, user: CurrentUser, learning: Learning) -> AssessmentService:
    return AssessmentService(db, user, learning)


Assess = Annotated[AssessmentService, Depends(_assessments)]


# ------------------------------------------------------------------ roadmaps
@router.post("/learning/roadmaps", response_model=RoadmapOut, status_code=201)
def create_roadmap(body: RoadmapCreateIn, svc: Learning) -> RoadmapOut:
    return svc.create(body)


@router.get("/learning/roadmaps", response_model=list[RoadmapSummary])
def list_roadmaps(svc: Learning) -> list[RoadmapSummary]:
    return svc.list_roadmaps()


@router.get("/learning/dashboard", response_model=DashboardOut)
def dashboard(svc: Learning) -> DashboardOut:
    return svc.dashboard()


@router.get("/learning/roadmaps/{roadmap_id}", response_model=RoadmapOut)
def get_roadmap(roadmap_id: uuid.UUID, svc: Learning) -> RoadmapOut:
    return svc.get(roadmap_id)


@router.post("/learning/roadmaps/{roadmap_id}/start", response_model=RoadmapOut)
def start_roadmap(roadmap_id: uuid.UUID, svc: Learning) -> RoadmapOut:
    return svc.start(roadmap_id)


@router.post("/learning/roadmaps/{roadmap_id}/activities/{activity_id}/complete", response_model=RoadmapOut)
def complete_activity(roadmap_id: uuid.UUID, activity_id: uuid.UUID, svc: Learning) -> RoadmapOut:
    return svc.set_activity(roadmap_id, activity_id, True)


@router.post("/learning/roadmaps/{roadmap_id}/activities/{activity_id}/reopen", response_model=RoadmapOut)
def reopen_activity(roadmap_id: uuid.UUID, activity_id: uuid.UUID, svc: Learning) -> RoadmapOut:
    return svc.set_activity(roadmap_id, activity_id, False)


@router.delete("/learning/roadmaps/{roadmap_id}", status_code=204)
def delete_roadmap(roadmap_id: uuid.UUID, svc: Learning) -> Response:
    svc.delete(roadmap_id)
    return Response(status_code=204)


@router.post("/learning/roadmaps/{roadmap_id}/report", response_model=ReportCreated, status_code=201)
def roadmap_report(roadmap_id: uuid.UUID, body: ReportRequest, svc: Learning) -> ReportCreated:
    return ReportCreated(report_id=svc.report(roadmap_id, body.report_format))


# ------------------------------------------------------------------ assessments
@router.get("/assessments", response_model=list[AssessmentSummary])
def list_assessments(svc: Assess) -> list[AssessmentSummary]:
    return svc.list_assessments()


@router.get("/assessments/attempts", response_model=list[AttemptSummary])
def attempts(svc: Assess, slug: Annotated[str | None, Query(max_length=60)] = None,
             limit: Annotated[int, Query(ge=1, le=50)] = 20,
             offset: Annotated[int, Query(ge=0)] = 0) -> list[AttemptSummary]:
    return svc.history(slug, limit, offset)


@router.get("/assessments/attempts/{attempt_id}")
def attempt_detail(attempt_id: uuid.UUID, svc: Assess) -> dict[str, Any]:
    return svc.attempt_detail(attempt_id)


@router.get("/assessments/{slug}", response_model=AssessmentDetail)
def assessment_detail(slug: str, svc: Assess) -> AssessmentDetail:
    return svc.detail(slug)


@router.post("/assessments/{slug}/attempts", response_model=SubmitOut, status_code=201)
def submit_attempt(slug: str, body: SubmitIn, svc: Assess) -> SubmitOut:
    return svc.submit(slug, body.answers)
