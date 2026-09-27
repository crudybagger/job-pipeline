"""Shared domain models for the job pipeline.

Defines the forward-complete JobStatus enum, the JobEntry pydantic
model, the stable job ID scheme, and the metadata key registry documented in
docs/design/pipeline-integration.md. Stages 2-4 reuse everything defined
here; metadata registry keys are extended, never repurposed.
"""

import hashlib
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Forward-complete pipeline status (docs/design/pipeline-integration.md)."""

    NEW = "new"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RESUME_READY = "resume_ready"
    SENT = "sent"

# --- Metadata key registry (docs/design/pipeline-integration.md) ------------
META_SCORE = "score"
META_SCORE_BREAKDOWN = "score_breakdown"
META_BASE_RESUME_PATH = "base_resume_path"
META_NOTES = "notes"
META_ATS = "ats"
META_RESUME = "resume"
META_RESEARCH = "research"
META_COVERLETTER = "coverletter"
META_DELIVERY = "delivery"
META_APPLICATION = "application"

# Keys only the owning stage code path may write (PATCH /jobs/{id} rejects these).
STAGE_OWNED_METADATA_KEYS = frozenset(
    {
        META_SCORE,
        META_SCORE_BREAKDOWN,
        META_ATS,
        META_RESUME,
        META_RESEARCH,
        META_COVERLETTER,
        META_DELIVERY,
        META_APPLICATION,
    }
)


def job_id(title: str, company_name: str, source: str) -> str:
    """Return the stable job ID used as the store primary key.

    Scheme (docs/design/pipeline-integration.md): sha256 hex digest of the
    pipe-joined title, company name and source, truncated to 12 characters.
    """
    payload = f"{title}|{company_name}|{source}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


class JobEntry(BaseModel):
    """A single job posting flowing through the pipeline."""

    id: str
    title: str
    description: str = ""
    company_name: str = ""
    company_website: str = ""
    contact_info: str = ""
    source_url: str = ""
    source: str = ""
    status: JobStatus = JobStatus.NEW
    tags: list[str] = Field(default_factory=list)
    job_type: str = ""
    location: str = ""
    salary: str = ""
    publication_date: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
