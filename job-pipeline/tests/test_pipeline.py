import pytest
from src.ingestion.ingest import fetch_job_listings


def test_fetch_job_listings_returns_list():
    result = fetch_job_listings("https://example.com/jobs")
    assert isinstance(result, list)
