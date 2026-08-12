import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CreateRepositoryRequest(BaseModel):
    url: str


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    status: str
    commit_sha: str | None
    error_message: str | None
    files_seen: int
    files_indexed: int
    files_skipped: int
    chunks_created: int
    created_at: datetime
    finished_at: datetime | None

class SearchResult(BaseModel):
    symbol_name: str | None
    file_path: str
    start_line: int
    end_line: int
    distance: float