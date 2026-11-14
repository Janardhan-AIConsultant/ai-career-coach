"""Practical project endpoints (registered users)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.dependencies import CurrentUser, DbSession, SettingsDep, state_singleton
from app.projects.catalog import TEMPLATES
from app.projects.github import GitHubFetcher, RepoFetcher
from app.schemas.projects import RecommendationOut, SubmissionIn, SubmissionOut, TemplateOut
from app.services.project_service import ProjectService, template_out

router = APIRouter(prefix="/projects", tags=["projects"])


def get_repo_fetcher(request: Request, settings: SettingsDep) -> RepoFetcher:
    return state_singleton(  # type: ignore[no-any-return]
        request, "repo_fetcher", lambda: GitHubFetcher(settings.github_token.get_secret_value()))


def _svc(db: DbSession, settings: SettingsDep, user: CurrentUser,
         fetcher: Annotated[RepoFetcher, Depends(get_repo_fetcher)]) -> ProjectService:
    return ProjectService(db, settings, user, fetcher)


Svc = Annotated[ProjectService, Depends(_svc)]


@router.get("/catalog", response_model=list[TemplateOut])
def catalog(user: CurrentUser) -> list[TemplateOut]:
    return [template_out(t) for t in TEMPLATES]


@router.get("/recommendations", response_model=list[RecommendationOut])
def recommendations(
    svc: Svc, roadmap_id: Annotated[uuid.UUID | None, Query()] = None,
    resume_document_id: Annotated[uuid.UUID | None, Query()] = None,
    job_description_document_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[RecommendationOut]:
    return svc.recommend(roadmap_id, resume_document_id, job_description_document_id)


@router.post("/submissions", response_model=SubmissionOut, status_code=201)
def submit(body: SubmissionIn, svc: Svc) -> SubmissionOut:
    return svc.submit(body)


@router.get("/submissions", response_model=list[SubmissionOut])
def list_submissions(svc: Svc) -> list[SubmissionOut]:
    return svc.list_submissions()


@router.get("/submissions/{submission_id}", response_model=SubmissionOut)
def get_submission(submission_id: uuid.UUID, svc: Svc) -> SubmissionOut:
    return svc.get(submission_id)


@router.post("/submissions/{submission_id}/evaluate", response_model=SubmissionOut)
def evaluate(submission_id: uuid.UUID, svc: Svc) -> SubmissionOut:
    return svc.evaluate(submission_id)


@router.delete("/submissions/{submission_id}", status_code=204)
def delete_submission(submission_id: uuid.UUID, svc: Svc) -> Response:
    svc.delete(submission_id)
    return Response(status_code=204)
