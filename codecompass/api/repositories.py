import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from codecompass.api.schemas import CreateRepositoryRequest, JobResponse
from codecompass.db import get_session
from codecompass.repositories.job_store import JobStore
from codecompass.repositories.repository_store import RepositoryStore
from codecompass.services.indexing_service import run_indexing_job
from codecompass.services.repo_url import InvalidRepositoryUrl, normalize

from codecompass.embedding.client import QuotaExhausted
from codecompass.services.search_service import search_repository
from codecompass.api.schemas import (
    CreateRepositoryRequest,
    JobResponse,
    SearchResult,
)

router = APIRouter(tags=["repositories"])


@router.post("/repositories", status_code=status.HTTP_202_ACCEPTED, response_model=JobResponse)
def index_repository(
    body: CreateRepositoryRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> JobResponse:
    try:
        url, name = normalize(body.url)
    except InvalidRepositoryUrl as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    repos, jobs = RepositoryStore(session), JobStore(session)
    repo = repos.get_by_url(url) or repos.create(url=url, name=name)

    # The partial unique index makes a duplicate impossible; this check makes the
    # refusal legible — a 409 with the running job's id, not an IntegrityError.
    if active := jobs.active_for_repository(repo.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Already indexing. Job id: {active.id}"
        )

    job = jobs.create(repo.id)
    session.commit()   # the row must exist before the task can look it up

    background.add_task(run_indexing_job, job.id, repo.id)
    return JobResponse.model_validate(job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: uuid.UUID, session: Session = Depends(get_session)) -> JobResponse:
    job = JobStore(session).get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job.")
    return JobResponse.model_validate(job)

@router.get(
    "/repositories/{repository_id}/search",
    response_model=list[SearchResult],
)
def search(
    repository_id: uuid.UUID,
    q: str,
    session: Session = Depends(get_session),
) -> list[SearchResult]:
    repo = RepositoryStore(session).get(repository_id)

    if repo is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No such repository.",
        )

    if not q.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Query must not be empty.",
        )

    results = search_repository(
        session=session,
        repository_id=repository_id,
        query=q,
    )

    return [
        SearchResult(
            symbol_name=chunk.symbol_name,
            file_path=chunk.source_file.path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            distance=float(distance),
        )
        for chunk, distance in results
    ]

@router.get(
    "/repositories/{repository_id}/search",
    response_model=list[SearchResult],
)
def search(
    repository_id: uuid.UUID,
    q: str,
    session: Session = Depends(get_session),
) -> list[SearchResult]:

    repo = RepositoryStore(session).get(repository_id)

    if repo is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No such repository.",
        )

    if not q.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Query must not be empty.",
        )

    try:
        results = search_repository(
            session=session,
            repository_id=repository_id,
            query=q,
        )
    except QuotaExhausted as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            str(exc),
        ) from exc

    return [
        SearchResult(
            symbol_name=chunk.symbol_name,
            file_path=chunk.source_file.path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            distance=float(distance),
        )
        for chunk, distance in results
    ]