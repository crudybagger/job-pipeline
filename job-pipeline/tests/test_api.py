"""Stage 1 API tests via TestClient over a temp store."""

import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from src.models import JobEntry, JobStatus
from src.queues import store as store_module


@pytest.fixture
def client(store, monkeypatch):
    """TestClient with the DB path patched to the temp store."""
    monkeypatch.setattr(store_module, "DB_PATH", store.path)
    # get_store() reads the module constant at call time.
    return TestClient(app_main.app)


def _seed(store, job_id="abc123def456", status=JobStatus.NEW):
    entry = JobEntry(
        id=job_id,
        title="Werkstudent Softwareentwicklung",
        company_name="Example GmbH",
        location="Aachen",
        source="arbeitnow",
        status=status,
        metadata={"score": 62, "notes": ""},
    )
    store.save(entry)
    return entry


def test_health(client):
    assert client.get("/").json() == {"status": "ok"}


def test_ui_served(client):
    response = client.get("/ui")
    assert response.status_code == 200
    assert "Job Pipeline" in response.text


def test_status_summary(client, store):
    _seed(store)
    data = client.get("/status").json()
    assert data["queues"] == {"new": 1}
    assert data["stages"]["stage1"]["implemented"] is True
    assert data["stages"]["stage1"]["pending_review"] == 1


def test_ingest_unknown_source_returns_400(client):
    response = client.post("/ingest", json={"source": "no-such-source"})
    assert response.status_code == 400


def test_ingest_full_flow(client, monkeypatch):
    """POST /ingest runs fetch -> parse -> score -> queue."""
    from src.ingestion import ingest as ingest_module
    from .conftest import load_fixture

    class FakeFetcher:
        name = "arbeitnow"

        def fetch(self, source):
            return [load_fixture("arbeitnow_job.json")]

    monkeypatch.setattr(
        ingest_module, "FETCHER_REGISTRY", {"arbeitnow": FakeFetcher()}
    )
    response = client.post("/ingest", json={"source": "arbeitnow"})
    assert response.status_code == 200
    summary = response.json()
    assert summary["ingested"] == 1
    assert summary["dry_run"] is False


def test_ingest_dry_run(client, monkeypatch):
    from src.ingestion import ingest as ingest_module
    from .conftest import load_fixture

    class FakeFetcher:
        name = "arbeitnow"

        def fetch(self, source):
            return [load_fixture("arbeitnow_job.json")]

    monkeypatch.setattr(
        ingest_module, "FETCHER_REGISTRY", {"arbeitnow": FakeFetcher()}
    )
    response = client.post(
        "/ingest", json={"source": "arbeitnow", "dry_run": True}
    )
    assert response.status_code == 200
    assert response.json()["ingested"] == 1


def test_stage1_run_batch(client, monkeypatch):
    from src.ingestion import ingest as ingest_module
    from .conftest import load_fixture

    class FakeFetcher:
        name = "arbeitnow"

        def fetch(self, source):
            return [load_fixture("arbeitnow_job.json")]

    monkeypatch.setattr(
        ingest_module, "FETCHER_REGISTRY", {"arbeitnow": FakeFetcher()}
    )
    response = client.post("/stage1/run?dry_run=true")
    assert response.status_code == 200
    assert response.json()["dry_run"] is True


def test_jobs_list_and_show(client, store):
    _seed(store)
    jobs = client.get("/jobs", params={"status": "new"}).json()
    assert jobs[0]["id"] == "abc123def456"
    job = client.get("/jobs/abc123def456").json()
    assert job["title"] == "Werkstudent Softwareentwicklung"
    assert client.get("/jobs/missing").status_code == 404


def test_accept_and_transition_guard(client, store):
    _seed(store)
    assert client.post("/jobs/abc123def456/accept").status_code == 200
    assert store.get("abc123def456").status == JobStatus.ACCEPTED
    # accepted -> rejected is allowed pre-resume_ready.
    assert client.post("/jobs/abc123def456/reject").status_code == 200
    assert store.get("abc123def456").status == JobStatus.REJECTED
    assert client.post("/jobs/missing/accept").status_code == 404


def test_reject_guarded_after_resume_ready(client, store):
    _seed(store, status=JobStatus.RESUME_READY)
    assert store.get("abc123def456").status == JobStatus.RESUME_READY
    # resume_ready -> rejected is not allowed (reject only pre-resume_ready).
    response = client.post("/jobs/abc123def456/reject")
    assert response.status_code == 409
    # resume_ready -> sent remains Stage 4's transition (also guarded here).
    response = client.post("/jobs/abc123def456/accept")
    assert response.status_code == 409


def test_reject_and_manual_accept(client, store):
    _seed(store)
    assert client.post("/jobs/abc123def456/reject").status_code == 200
    assert store.get("abc123def456").status == JobStatus.REJECTED
    # rejected -> accepted (manual accept) is allowed.
    assert client.post("/jobs/abc123def456/accept").status_code == 200


def test_note_endpoint(client, store):
    _seed(store)
    response = client.post(
        "/jobs/abc123def456/note", json={"note": "interesting role"}
    )
    assert response.status_code == 200
    assert "interesting role" in store.get("abc123def456").metadata["notes"]


def test_patch_whitelist(client, store):
    _seed(store)
    response = client.patch(
        "/jobs/abc123def456", json={"updates": {"location": "Remote"}}
    )
    assert response.status_code == 200
    assert store.get("abc123def456").location == "Remote"
    # Stage-owned keys and status are immutable via PATCH.
    response = client.patch(
        "/jobs/abc123def456", json={"updates": {"metadata.score": 100}}
    )
    assert response.status_code == 422
    response = client.patch(
        "/jobs/abc123def456", json={"updates": {"status": "accepted"}}
    )
    assert response.status_code == 422
