"""Stage 1 ingestion: per-source fetchers for JSON-API job boards.

Dispatch table keyed by source name (FETCHER_REGISTRY); a new source is
one class plus one registry entry. The HtmlFetcherStub exists purely as
the plugin seam for later HTML scraping (design decision #1). The legacy
fetch_job_listings placeholder signature and behavior are preserved.
"""

import os
from typing import List, Protocol

import httpx

from src.config import SourceConfig, SourceType


class Fetcher(Protocol):
    """Protocol shared by all source fetchers."""

    name: str

    def fetch(self, source: SourceConfig) -> List[dict]:
        """Fetch raw job listings from the source."""
        ...


REQUEST_TIMEOUT_SECONDS = 30.0


class RemotiveFetcher:
    """Remotive public JSON API (remotive.com/api/remote-jobs)."""

    name = "remotive"

    def fetch(self, source: SourceConfig) -> List[dict]:
        payload = _get_json(source.url)
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        return [dict(job, source=self.name) for job in jobs if isinstance(job, dict)]


class RemoteOKFetcher:
    """RemoteOK public JSON API (remoteok.com/api)."""

    name = "remoteok"

    def fetch(self, source: SourceConfig) -> List[dict]:
        payload = _get_json(source.url)
        jobs = payload if isinstance(payload, list) else []
        return [
            dict(job, source=self.name)
            for job in jobs
            if isinstance(job, dict) and job.get("position")
        ]


class ArbeitnowFetcher:
    """Arbeitnow German job board API (arbeitnow.com/api/job-board-api)."""

    name = "arbeitnow"

    def fetch(self, source: SourceConfig) -> List[dict]:
        payload = _get_json(source.url)
        jobs = payload.get("data", []) if isinstance(payload, dict) else []
        return [dict(job, source=self.name) for job in jobs if isinstance(job, dict)]


BA_DEFAULT_API_KEY = "jobboerse-jobsuche"


class BundesagenturFetcher:
    """Bundesagentur für Arbeit Jobsuche API (rest.arbeitsagentur.de).

    The search query (was/wo/umkreis/...) lives in the source URL — one
    search per source entry. Authenticated via the public API key header
    `X-API-Key` (overridable through the BA_API_KEY env var). Note: the
    endpoint blocks datacenter IPs with 403; it works from residential
    networks.
    """

    name = "bundesagentur"

    def fetch(self, source: SourceConfig) -> List[dict]:
        api_key = os.environ.get("BA_API_KEY", BA_DEFAULT_API_KEY)
        headers = {"X-API-Key": api_key}
        payload = _get_json(source.url, headers=headers)
        embedded = payload.get("embedded", []) if isinstance(payload, dict) else []
        return [
            dict(job, source=self.name) for job in embedded if isinstance(job, dict)
        ]



class HtmlFetcherStub:
    """Placeholder for future HTML scraping (Indeed, Dice, LinkedIn, StepStone)."""

    name = "html-stub"

    def fetch(self, source: SourceConfig) -> List[dict]:
        raise NotImplementedError(
            "HTML scraping is not implemented yet; add a real fetcher class "
            "and register it in FETCHER_REGISTRY (see docs/design/)"
        )


def _get_json(url: str, headers: dict | None = None):
    response = httpx.get(
        url, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True, headers=headers
    )
    response.raise_for_status()
    return response.json()


FETCHER_REGISTRY: dict[str, Fetcher] = {
    RemotiveFetcher.name: RemotiveFetcher(),
    RemoteOKFetcher.name: RemoteOKFetcher(),
    ArbeitnowFetcher.name: ArbeitnowFetcher(),
    BundesagenturFetcher.name: BundesagenturFetcher(),
    HtmlFetcherStub.name: HtmlFetcherStub(),
}


def fetch_from_source(source_config: SourceConfig) -> List[dict]:
    """Dispatch to the registered fetcher for the given source config.

    Raises NotImplementedError for html sources (plugin seam) and ValueError
    for unregistered source names.
    """
    if source_config.type == SourceType.HTML:
        raise NotImplementedError(
            "Source is type html: HTML scraping is not implemented yet "
            "(plugin seam for later)"
        )
    fetcher = FETCHER_REGISTRY.get(source_config.name.lower())
    if fetcher is None:
        raise ValueError(f"No fetcher registered for source: {source_config.name}")
    return fetcher.fetch(source_config)


def fetch_job_listings(source_url: str) -> List[dict]:
    """Preserved placeholder: raw listings for the given URL.

    Kept for backwards compatibility with the original scaffolding tests;
    the real Stage 1 flow goes through fetch_from_source.
    """
    return []
