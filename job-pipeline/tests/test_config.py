"""Stage 1 config layer tests."""

from pathlib import Path

from src.config import PipelineConfig, load_config


def test_missing_file_yields_empty_default(tmp_path, monkeypatch):
    """A missing config file yields an empty default config, not an error."""
    import src.config as config_module

    monkeypatch.delenv("PIPELINE_CONFIG", raising=False)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH",
                        tmp_path / "missing.json")
    monkeypatch.setattr(config_module, "EXAMPLE_CONFIG_PATH",
                        tmp_path / "also-missing.json")
    config = load_config()
    assert isinstance(config, PipelineConfig)
    assert config.sources == []
    assert config.matching.match_threshold == 70


def test_explicit_path_loads_and_validates(tmp_path):
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        '{"sources": [{"name": "remotive", "url": "https://remotive.com/api"}],'
        '"matching": {"match_threshold": 55}}',
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.sources[0].name == "remotive"
    assert config.sources[0].enabled is True
    assert config.matching.match_threshold == 55


def test_example_config_is_full_shape():
    """The example config ships the full shape incl. Stage 2-4 sections."""
    example = Path(__file__).resolve().parent.parent / "config" / "pipeline.example.json"
    config = load_config(example)
    assert config.sources
    assert config.matching.match_threshold
    assert config.candidate_profile.skills
    assert config.stage2.ats_ready_threshold == 80
    assert config.stage3.narrative_pattern == ""
    assert config.stage4.message_template == ""


def test_real_config_carries_stage1_instance():
    """The real (gitignored) config carries the candidate profile + sources."""
    real = Path(__file__).resolve().parent.parent / "config" / "pipeline.json"
    if not real.is_file():
        # The real config is optional (gitignored); skip when absent.
        return
    config = load_config(real)
    names = {source.name for source in config.sources}
    assert {"remotive", "remoteok", "arbeitnow", "bundesagentur"} <= names
    assert config.search_keywords
    assert config.base_resume_path
    assert config.candidate_profile.location
