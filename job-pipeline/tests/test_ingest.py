"""Stage 1 ingestion tests: registry dispatch + BundesagenturFetcher."""

import httpx
import pytest

from src.config import SourceConfig, SourceType
from src.ingestion.ingest import (
    BA_DEFAULT_API_KEY,
    BundesagenturFetcher,
    FETCHER_REGISTRY,
    HtmlFetcherStub,
    RemoteOKFetcher,
    fetch_from_source,
    fetch_job_listings,
)

from .conftest import load_fixture


def test_registry_has_all_sources():
    assert set(FETCHER_REGISTRY) == {
        "remotive", "remoteok", "arbeitnow", "bundesagentur", "html-stub"
    }


def test_fetch_job_listings_placeholder_preserved():
    """Legacy scaffolding behavior: returns an empty list, no network."""
    assert fetch_job_listings("https://example.com/jobs") == []


def test_fetch_from_source_rejects_html(monkeypatch):
    source = SourceConfig(name="html-stub", type=SourceType.HTML, url="")
    with pytest.raises(NotImplementedError):
        fetch_from_source(source)


def test_fetch_from_source_rejects_unknown_name():
    source = SourceConfig(name="no-such-board", url="https://example.com")
    with pytest.raises(ValueError):
        fetch_from_source(source)


def test_remotive_fetch(monkeypatch):
    payload = {"jobs": [load_fixture("remotive_job.json")]}
    monkeypatch.setattr(
        "src.ingestion.ingest._get_json", lambda url, headers=None: payload
    )
    source = SourceConfig(
        name="remotive", url="https://remotive.com/api/remote-jobs"
    )
    listings = fetch_from_source(source)
    assert len(listings) == 1
    assert listings[0]["source"] == "remotive"


def test_remoteok_fetch_filters_legal_notice(monkeypatch):
    legal = {"legal": "API Terms of Service: ...", "last_updated": 1790438426}
    payload = [legal, load_fixture("remoteok_job.json")]
    monkeypatch.setattr(
        "src.ingestion.ingest._get_json", lambda url, headers=None: payload
    )
    listings = RemoteOKFetcher().fetch(SourceConfig(name="remoteok", url="x"))
    assert len(listings) == 1
    assert listings[0]["position"] == "Backend Engineer (Python/AWS)"


def test_bundesagentur_fetch(monkeypatch):
    payload = {"embedded": [load_fixture("bundesagentur_job.json")],
               "page": {"totalElements": 1}}
    seen = {}

    def fake_get_json(url, headers=None):
        seen["url"] = url
        seen["headers"] = headers
        return payload

    monkeypatch.setattr("src.ingestion.ingest._get_json", fake_get_json)
    fetcher = BundesagenturFetcher()
    source = SourceConfig(
        name="bundesagentur",
        url="https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
            "?was=werkstudent&wo=Aachen",
    )
    listings = fetcher.fetch(source)
    assert len(listings) == 1
    assert listings[0]["source"] == "bundesagentur"
    assert seen["headers"]["X-API-Key"] == BA_DEFAULT_API_KEY


def test_bundesagentur_api_key_env_override(monkeypatch):
    monkeypatch.setenv("BA_API_KEY", "custom-key")
    seen = {}

    def fake_get_json(url, headers=None):
        seen["headers"] = headers
        return {"embedded": []}

    monkeypatch.setattr("src.ingestion.ingest._get_json", fake_get_json)
    BundesagenturFetcher().fetch(SourceConfig(name="bundesagentur", url="x"))
    assert seen["headers"]["X-API-Key"] == "custom-key"


def test_bundesagentur_propagates_http_errors(monkeypatch):
    def fake_get_json(url, headers=None):
        response = httpx.Response(status_code=403, request=httpx.Request("GET", url))
        raise httpx.HTTPStatusError(
            "403", request=response.request, response=response
        )

    monkeypatch.setattr("src.ingestion.ingest._get_json", fake_get_json)
    with pytest.raises(httpx.HTTPStatusError):
        BundesagenturFetcher().fetch(SourceConfig(name="bundesagentur", url="x"))


def test_html_stub_raises():
    with pytest.raises(NotImplementedError):
        HtmlFetcherStub().fetch(SourceConfig(name="html-stub", type=SourceType.HTML, url=""))
