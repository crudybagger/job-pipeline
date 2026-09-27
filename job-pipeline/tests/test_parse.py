"""Stage 1 parsing tests: per-source normalization from recorded fixtures."""

import pytest

from src.models import JobEntry, JobStatus
from src.parsing.parse import (
    extract_company_website,
    extract_email,
    parse_job_listing,
    strip_html,
)

from .conftest import load_fixture


def test_strip_html_collapses_to_plain_text():
    assert strip_html("<p>Hello <strong>world</strong></p>") == "Hello world"
    assert strip_html("") == ""


def test_extract_email():
    assert extract_email("apply to jobs@example.com now") == "jobs@example.com"
    assert extract_email("no contact here") == ""


def test_extract_company_website_skips_board_links():
    text = "see https://example-gmbh.de and https://www.arbeitnow.com"
    assert extract_company_website(text, "https://www.arbeitnow.com/jobs/x") == (
        "https://example-gmbh.de"
    )


def test_parse_remotive_from_fixture():
    raw = load_fixture("remotive_job.json")
    entry = parse_job_listing(raw, base_resume_path="../data/Resume.tex")
    assert isinstance(entry, JobEntry)
    assert entry.title == "Senior Backend Developer (Python)"
    assert entry.company_name == "Sanctuary Computer Inc"
    assert entry.location == "Worldwide"
    assert entry.job_type == "contract"
    assert entry.salary == "$80k - $150k"
    assert "backend developer" in entry.description
    assert entry.contact_info == "jobs@example.com"
    assert entry.company_website == "https://example-gmbh.de/careers."
    assert entry.source == "remotive"
    assert entry.status == JobStatus.NEW
    assert entry.metadata["base_resume_path"] == "../data/Resume.tex"
    assert entry.metadata["notes"] == ""
    assert len(entry.id) == 12


def test_parse_remoteok_from_fixture():
    raw = load_fixture("remoteok_job.json")
    entry = parse_job_listing(raw)
    assert entry.title == "Backend Engineer (Python/AWS)"
    assert entry.company_name == "Example Cloud Services"
    assert entry.location == "Worldwide"
    assert entry.salary == "60000 - 90000"
    assert entry.publication_date == "2026-09-26T16:00:26+00:00"
    assert entry.source == "remoteok"


def test_parse_arbeitnow_from_fixture():
    raw = load_fixture("arbeitnow_job.json")
    entry = parse_job_listing(raw)
    assert entry.title == "Werkstudent Softwareentwicklung (m/w/d)"
    assert entry.company_name == "Example GmbH"
    assert entry.location == "remote / Aachen"
    assert "remote" in entry.tags
    assert entry.job_type == "internship, working student"
    assert entry.publication_date.startswith("2026-")
    assert entry.contact_info == "jobs@example-gmbh.de"


def test_parse_bundesagentur_from_fixture():
    raw = load_fixture("bundesagentur_job.json")
    entry = parse_job_listing(raw)
    assert entry.title == "Werkstudent Softwareentwicklung (m/w/d)"
    assert entry.company_name == "RWTH Example Chair"
    assert entry.location.startswith("Aachen")
    assert "(12 km)" in entry.location
    assert "refnr:10000-1000000001-B" in entry.tags
    assert entry.publication_date == "2026-11-01"
    assert entry.source_url == "https://example-rwth.de/jobs/werkstudent-sw"
    assert entry.description == ""


def test_parse_uses_stable_job_id():
    raw = load_fixture("arbeitnow_job.json")
    first = parse_job_listing(raw)
    second = parse_job_listing(raw)
    assert first.id == second.id


def test_parse_unknown_source_raises():
    with pytest.raises(ValueError):
        parse_job_listing({"title": "x", "source": "unknown-board"})
    with pytest.raises(ValueError):
        parse_job_listing({"title": "x"})
