"""Shared test fixtures for the job-pipeline test suite.

Introduced with Stage 1 and reused by Stages 2-4 (testing contract in
docs/design/pipeline-integration.md): temp-dir SQLite store (monkey-
patched store module constant, matching the existing isolated-tests
pattern), sample JobEntry, candidate/matching dicts and fixture loaders.
No live network anywhere in the test suite.
"""

import json
from pathlib import Path

import pytest

from src.config import PipelineConfig
from src.models import JobEntry, JobStatus
from src.queues import store as store_module
from src.queues.store import JobsStore

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Load a recorded raw source payload from tests/fixtures/."""
    with open(FIXTURES_DIR / name, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the recorded fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def tmp_db_path(tmp_path) -> Path:
    """Temp SQLite path (not yet patched into the store module)."""
    return tmp_path / "queues-test.db"


@pytest.fixture
def store(tmp_db_path, monkeypatch) -> JobsStore:
    """JobsStore over a temp DB with the module constant monkey-patched."""
    monkeypatch.setattr(store_module, "DB_PATH", tmp_db_path)
    db = JobsStore()
    yield db
    db.close()


@pytest.fixture
def sample_job_entry() -> JobEntry:
    """A scored Werkstudent job ready to be saved."""
    return JobEntry(
        id="abc123def456",
        title="Werkstudent Softwareentwicklung (m/w/d)",
        description="Backend-Team support with Python, Java, AWS, Docker.",
        company_name="Example GmbH",
        company_website="https://example-gmbh.de",
        contact_info="jobs@example-gmbh.de",
        source_url="https://www.arbeitnow.com/jobs/werkstudent-77234",
        source="arbeitnow",
        status=JobStatus.NEW,
        tags=["werkstudent", "python"],
        job_type="internship",
        location="Aachen",
        metadata={
            "score": 62,
            "score_breakdown": {"experience": 40.0, "prospects": 33.3, "education": 100.0},
            "base_resume_path": "../data/Resume.tex",
            "notes": "",
        },
    )


@pytest.fixture
def candidate_profile() -> dict:
    """Candidate profile dict mirroring config/pipeline.json."""
    return {
        "skills": ["java", "golang", "python", "aws", "kubernetes", "docker", "kafka",
                   "redis", "microservices"],
        "experience": [
            "Software Engineer at Amazon in the UPI payments team",
            "AI Inferencing Platform Engineer at Visa",
        ],
        "education": ["B.Tech Computer Science, NIT Warangal (2023)"],
        "location": "Aachen",
        "languages": ["english", "german"],
    }


@pytest.fixture
def matching() -> dict:
    """Matching config dict mirroring config/pipeline.json."""
    return {
        "score_weights": {"experience": 1.0, "prospects": 0.6, "education": 1.2},
        "match_threshold": 40,
        "auto_accept_above_threshold": False,
        "in_demand_technologies": ["aws", "kubernetes", "kafka", "redis", "golang",
                                   "python", "java", "docker"],
        "role_keywords": ["werkstudent", "hiwi", "working student",
                          "studentische hilfskraft", "student assistant", "student",
                          "praktikum", "intern", "internship", "thesis",
                          "abschlussarbeit"],
        "location_keywords": ["aachen", "köln", "koeln", "cologne", "düsseldorf",
                              "duesseldorf", "dusseldorf", "bonn", "nordrhein-westfalen",
                              "nrw"],
        "remote_indicators": ["remote", "worldwide", "anywhere", "homeoffice",
                              "home office", "home-office", "work from home"],
        "require_location_fit": True,
    }


@pytest.fixture
def pipeline_config(matching, candidate_profile) -> PipelineConfig:
    """A PipelineConfig with one fake-enabled source and test knobs."""
    from src.config import CandidateProfile, MatchingConfig

    config = PipelineConfig()
    config.matching = MatchingConfig(**matching)
    config.candidate_profile = CandidateProfile(**candidate_profile)
    config.base_resume_path = "../data/Resume.tex"
    return config


class FakeLLMClient:
    """Scripted stand-in for LLMClient (no network); records calls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, system, user, schema=None):
        self.calls.append({"system": system, "user": user, "schema": schema})
        if not self.responses:
            raise AssertionError("Unexpected LLM call (scripted responses exhausted)")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, str) else json.dumps(item)


BASE_RESUME_FIXTURE = FIXTURES_DIR / "base_resume.tex"


@pytest.fixture
def base_resume_tex() -> str:
    """Mini LaTeX base resume with rSection/tableEnv blocks."""
    return BASE_RESUME_FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def fake_llm(monkeypatch):
    """Install a scripted LLM client; returns an installer function."""
    from src.llm import provider

    installed = []

    def _install(responses):
        client = FakeLLMClient(responses)
        installed.append(client)
        provider.set_client(client)
        return client

    yield _install
    provider.set_client(None)
    installed.clear()
