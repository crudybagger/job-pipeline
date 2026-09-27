"""Stage 1 orchestrator tests: classify, dry-run, error isolation."""

import pytest

from src.config import SourceConfig
from src.models import JobStatus
from src.stage1 import _classify, run_stage1
from src.queues.store import JobsStore

from .conftest import load_fixture


def test_classify_routes_below_threshold_to_rejected():
    assert _classify(10, 40, auto_accept=False) == JobStatus.REJECTED
    assert _classify(10, 40, auto_accept=True) == JobStatus.REJECTED


def test_classify_routes_above_threshold_to_new_or_accepted():
    assert _classify(80, 40, auto_accept=False) == JobStatus.NEW
    assert _classify(80, 40, auto_accept=True) == JobStatus.ACCEPTED


def _patch_registry(monkeypatch, payload, error_source=None):
    """Patch FETCHER_REGISTRY entries with canned payloads / errors."""
    from src.ingestion import ingest as ingest_module

    class FakeFetcher:
        def __init__(self, name):
            self.name = name

        def fetch(self, source):
            if error_source is not None and source.name == error_source:
                raise RuntimeError("network down")
            return payload

    registry = {
        "remoteok": FakeFetcher("remoteok"),
        "arbeitnow": FakeFetcher("arbeitnow"),
    }
    monkeypatch.setattr(ingest_module, "FETCHER_REGISTRY", registry)


def test_run_stage1_queues_entries(pipeline_config, store, monkeypatch):
    _patch_registry(monkeypatch, [load_fixture("arbeitnow_job.json")])
    pipeline_config.sources = [SourceConfig(name="arbeitnow", url="x")]
    summary = run_stage1(pipeline_config, store)
    assert summary["dry_run"] is False
    assert summary["ingested"] == 1
    assert summary["rejected"] + summary["new"] + summary["accepted"] == 1
    entries = store.list_by_status("new") + store.list_by_status("rejected")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.metadata["score"] >= 0
    assert entry.metadata["base_resume_path"] == pipeline_config.base_resume_path


def test_run_stage1_location_gate_rejects_far_jobs(
    pipeline_config, store, monkeypatch
):
    raw = load_fixture("remoteok_job.json")
    raw["location"] = "Melbourne"
    _patch_registry(monkeypatch, [raw])
    pipeline_config.sources = [SourceConfig(name="remoteok", url="x")]
    summary = run_stage1(pipeline_config, store)
    assert summary["rejected"] == 1
    rejected = store.list_by_status("rejected")
    assert rejected[0].metadata["score_breakdown"]["location_fit"] is False


def test_run_stage1_dry_run_persists_nothing(pipeline_config, store, monkeypatch):
    _patch_registry(monkeypatch, [load_fixture("arbeitnow_job.json")])
    pipeline_config.sources = [SourceConfig(name="arbeitnow", url="x")]
    summary = run_stage1(pipeline_config, store, dry_run=True)
    assert summary["dry_run"] is True
    assert summary["ingested"] == 1
    assert store.count_by_status() == {}


def test_run_stage1_limit(pipeline_config, store, monkeypatch):
    _patch_registry(
        monkeypatch,
        [load_fixture("arbeitnow_job.json"), load_fixture("remoteok_job.json")],
    )
    pipeline_config.sources = [SourceConfig(name="arbeitnow", url="x")]
    summary = run_stage1(pipeline_config, store, limit=1)
    assert summary["ingested"] == 1


def test_run_stage1_source_error_is_isolated(pipeline_config, store, monkeypatch):
    _patch_registry(
        monkeypatch,
        [load_fixture("arbeitnow_job.json")],
        error_source="remoteok",
    )
    pipeline_config.sources = [
        SourceConfig(name="remoteok", url="x"),
        SourceConfig(name="arbeitnow", url="x"),
    ]
    summary = run_stage1(pipeline_config, store)
    assert summary["sources"][0]["error"] == "network down"
    assert summary["sources"][0]["ingested"] == 0
    assert summary["ingested"] == 1  # the healthy source still ran


def test_run_stage1_unknown_source_raises(pipeline_config, store):
    pipeline_config.sources = []
    with pytest.raises(ValueError):
        run_stage1(pipeline_config, store, source_name="no-such-source")


def test_run_stage1_is_idempotent(pipeline_config, store, monkeypatch):
    _patch_registry(monkeypatch, [load_fixture("arbeitnow_job.json")])
    pipeline_config.sources = [SourceConfig(name="arbeitnow", url="x")]
    run_stage1(pipeline_config, store)
    run_stage1(pipeline_config, store)
    total = sum(store.count_by_status().values())
    assert total == 1
