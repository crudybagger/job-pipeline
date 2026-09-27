"""Stage 1 config layer: pydantic-validated PipelineConfig.

One config file shape from day one (docs/design/pipeline-integration.md):
config/pipeline.example.json ships the full shape with Stage 2-4 sections
present so later stages never change the format. The real config lives at
config/pipeline.json (gitignored). .env overrides via python-dotenv are
loaded for secrets (LLM key, Telegram token, research provider keys).


"""
import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "pipeline.json"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "config" / "pipeline.example.json"


class SourceType(str, Enum):
    """Job source types: api (JSON endpoints) and html (scraper plugin seam)."""

    API = "api"
    HTML = "html"


class SourceConfig(BaseModel):
    """One scrapeable source (name, type, url, enabled)."""

    name: str
    type: SourceType = SourceType.API
    url: str
    enabled: bool = True


class ScoreWeights(BaseModel):
    """Per-factor score weights for the deterministic matcher."""

    experience: float = 1.0
    prospects: float = 1.0
    education: float = 1.0


class MatchingConfig(BaseModel):
    """Match score weights, threshold and re-tuning knobs (plan.md)."""

    score_weights: ScoreWeights = Field(default_factory=ScoreWeights)
    match_threshold: int = 70
    auto_accept_above_threshold: bool = False
    in_demand_technologies: list[str] = Field(default_factory=list)
    role_keywords: list[str] = Field(default_factory=list)
    location_keywords: list[str] = Field(default_factory=list)
    remote_indicators: list[str] = Field(default_factory=list)
    require_location_fit: bool = True


class CandidateProfile(BaseModel):
    """Candidate skills, experience entries, education and language skills."""

    skills: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    location: str = ""
    languages: list[str] = Field(default_factory=list)


class Stage2Config(BaseModel):
    """Stage 2 knobs: ATS threshold, iteration cap, LaTeX section markers."""

    ats_ready_threshold: int = 80
    max_iterations: int = 5
    latex_section_markers: dict[str, str] = Field(default_factory=dict)


class Stage3Config(BaseModel):
    """Stage 3 knobs: research providers, story context, narrative pattern."""

    research_providers: list[dict[str, Any]] = Field(default_factory=list)
    story_context: dict[str, Any] = Field(default_factory=dict)
    narrative_pattern: str = ""


class Stage4Config(BaseModel):
    """Stage 4 knobs: messaging provider credentials and message template."""

    messaging: dict[str, Any] = Field(default_factory=dict)
    message_template: str = ""


class PipelineConfig(BaseModel):
    """Full pipeline config; Stage 2-4 sections ship empty/defaults from day one."""

    sources: list[SourceConfig] = Field(default_factory=list)
    search_keywords: list[str] = Field(default_factory=list)
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    candidate_profile: CandidateProfile = Field(default_factory=CandidateProfile)
    base_resume_path: str = ""
    stage2: Stage2Config = Field(default_factory=Stage2Config)
    stage3: Stage3Config = Field(default_factory=Stage3Config)
    stage4: Stage4Config = Field(default_factory=Stage4Config)


def load_config(path: str | Path | None = None) -> PipelineConfig:
    """Load and validate the pipeline config.

    Resolution order: explicit path argument, PIPELINE_CONFIG env var,
    config/pipeline.json, config/pipeline.example.json. .env is loaded
    first so secret overrides are available for later stages. A missing
    file yields an empty default config rather than an error.
    """
    load_dotenv()
    candidates: list[Path] = []
    if path is not None:
        candidates.append(Path(path))
    env_path = os.environ.get("PIPELINE_CONFIG")
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend([DEFAULT_CONFIG_PATH, EXAMPLE_CONFIG_PATH])
    for candidate in candidates:
        if candidate.is_file():
            with open(candidate, "r", encoding="utf-8") as handle:
                return PipelineConfig.model_validate(json.load(handle))
    return PipelineConfig()
