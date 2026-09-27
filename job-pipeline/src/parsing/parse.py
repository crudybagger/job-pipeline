"""Stage 1 parsing: raw source dict -> validated JobEntry.

Per-source field mapping with safe fallbacks for missing contact details
(JSON-API boards often omit contact emails). The description is stripped
to plain text so the deterministic scorer works on clean prose, and a
company website is salvaged from visible description links when the board
does not provide one.


"""
import html as html_module
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from src.models import JobEntry, JobStatus, job_id

TAG_RE = re.compile("<[^>]+>")
EMAIL_RE = re.compile("[A-Za-z0-9._%+-]+[@][A-Za-z0-9.-]+[.][A-Za-z]{2,}")
BOARD_HOSTS = ("remotive.com", "remoteok.com", "remoteok.io", "arbeitnow.com")


def strip_html(text: str) -> str:
    """Convert an HTML job description into collapsed plain text."""
    if not text:
        return ""
    without_tags = TAG_RE.sub(" ", str(text))
    unescaped = html_module.unescape(without_tags)
    return " ".join(unescaped.split()).strip()


def extract_email(text: str) -> str:
    """Return the first email address found in the text, or an empty string."""
    match = EMAIL_RE.search(text or "")
    return match.group(0) if match else ""


def extract_company_website(text: str, source_url: str = "") -> str:
    """Return the first non-board http link visible in the text, or empty."""
    source_host = urlparse(source_url or "").hostname or ""
    for candidate in (text or "").split():
        candidate = candidate.strip(",;):")
        if not (candidate.startswith("http://") or candidate.startswith("https://")):
            continue
        host = urlparse(candidate).hostname or ""
        if not host or any(board in host for board in BOARD_HOSTS):
            continue
        if host == source_host:
            continue
        return candidate
    return ""


def _unix_to_iso(value) -> str:
    """Convert a unix timestamp to an ISO-8601 UTC string (empty on failure)."""
    if not value:
        return ""
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return ""


def _parse_remotive(raw: dict) -> dict:
    description_text = strip_html(raw.get("description") or "")
    source_url = str(raw.get("url") or "").strip()
    return {
        "title": str(raw.get("title") or "").strip(),
        "description": description_text,
        "company_name": str(raw.get("company_name") or "").strip(),
        "company_website": extract_company_website(raw.get("description") or "", source_url),
        "contact_info": extract_email(raw.get("description") or ""),
        "source_url": source_url,
        "source": str(raw.get("source") or "remotive").strip(),
        "tags": [str(tag) for tag in (raw.get("tags") or [])],
        "job_type": str(raw.get("job_type") or "").strip(),
        "location": str(raw.get("candidate_required_location") or "").strip(),
        "salary": str(raw.get("salary") or "").strip(),
        "publication_date": str(raw.get("publication_date") or "").strip(),
    }


def _parse_remoteok(raw: dict) -> dict:
    description_text = strip_html(raw.get("description") or "")
    source_url = str(raw.get("url") or raw.get("apply_url") or "").strip()
    salary_min = raw.get("salary_min")
    salary_max = raw.get("salary_max")
    if salary_min and salary_max:
        salary = str(salary_min) + " - " + str(salary_max)
    elif salary_min or salary_max:
        salary = str(salary_min or salary_max)
    else:
        salary = ""
    return {
        "title": str(raw.get("position") or "").strip(),
        "description": description_text,
        "company_name": str(raw.get("company") or "").strip(),
        "company_website": extract_company_website(raw.get("description") or "", source_url),
        "contact_info": extract_email(raw.get("description") or ""),
        "source_url": source_url,
        "source": str(raw.get("source") or "remoteok").strip(),
        "tags": [str(tag) for tag in (raw.get("tags") or [])],
        "job_type": "",
        "location": str(raw.get("location") or "").strip(),
        "salary": salary,
        "publication_date": str(raw.get("date") or "").strip(),
    }


def _parse_arbeitnow(raw: dict) -> dict:
    """Arbeitnow German board: remote flag, German locations, unix created_at."""
    description_text = strip_html(raw.get("description") or "")
    source_url = str(raw.get("url") or "").strip()
    location = str(raw.get("location") or "").strip()
    tags = [str(tag) for tag in (raw.get("tags") or [])]
    if bool(raw.get("remote")):
        tags = ["remote"] + [tag for tag in tags if tag.lower() != "remote"]
        location = "remote" if not location else f"remote / {location}"
    job_types = raw.get("job_types") or []
    return {
        "title": str(raw.get("title") or "").strip(),
        "description": description_text,
        "company_name": str(raw.get("company_name") or "").strip(),
        "company_website": extract_company_website(raw.get("description") or "", source_url),
        "contact_info": extract_email(raw.get("description") or ""),
        "source_url": source_url,
        "source": str(raw.get("source") or "arbeitnow").strip(),
        "tags": tags,
        "job_type": ", ".join(str(job_type) for job_type in job_types),
        "location": location,
        "salary": "",
        "publication_date": _unix_to_iso(raw.get("created_at")),
    }


def _parse_bundesagentur(raw: dict) -> dict:
    """Bundesagentur für Arbeit Jobsuche API v4 search response entry."""
    arbeitsort = raw.get("arbeitsort") or {}
    location_parts = []
    for key in ("ort", "region", "land"):
        value = str(arbeitsort.get(key) or "").strip()
        if value and value not in location_parts:
            location_parts.append(value)
    location = ", ".join(location_parts)
    distanz = raw.get("distanz")
    if distanz and location:
        try:
            location = f"{location} ({float(distanz):.0f} km)"
        except (TypeError, ValueError):
            pass
    tags = []
    refnr = str(raw.get("refnr") or "").strip()
    if refnr:
        tags.append(f"refnr:{refnr}")
    beruf = str(raw.get("beruf") or "").strip()
    if beruf:
        tags.append(beruf)
    return {
        "title": str(raw.get("titel") or raw.get("beruf") or "").strip(),
        "description": "",  # full description requires the jobdetails endpoint
        "company_name": str(raw.get("arbeitgeber") or "").strip(),
        "company_website": "",
        "contact_info": "",
        "source_url": str(raw.get("externeUrl") or raw.get("jobDetailURL") or "").strip(),
        "source": str(raw.get("source") or "bundesagentur").strip(),
        "tags": tags,
        "job_type": "",
        "location": location,
        "salary": "",
        "publication_date": str(raw.get("eintrittsdatum") or "").strip(),
    }


PARSER_REGISTRY = {
    "remotive": _parse_remotive,
    "remoteok": _parse_remoteok,
    "arbeitnow": _parse_arbeitnow,
    "bundesagentur": _parse_bundesagentur,
}


def parse_job_listing(raw: dict, base_resume_path: str = "") -> JobEntry:
    """Normalize a raw source dict into a validated JobEntry.

    Dispatches on the source-stamped field (raw["source"], added by the
    fetchers). Fields map per source with safe fallbacks for missing
    contact details. The stable job ID (sha256(title|company|source)[:12])
    is computed here and metadata is seeded with the base resume path and
    an empty notes section. Unknown sources raise ValueError.
    """
    source = str(raw.get("source") or "").strip().lower()
    mapper = PARSER_REGISTRY.get(source)
    if mapper is None:
        raise ValueError(f"No parser registered for source: {source or '<missing>'}")
    fields = mapper(raw)
    entry_id = job_id(fields["title"], fields["company_name"], fields["source"])
    return JobEntry(
        id=entry_id,
        metadata={"base_resume_path": base_resume_path, "notes": ""},
        **fields,
    )

