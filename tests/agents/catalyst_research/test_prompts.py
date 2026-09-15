from app.agents.catalyst_research.config import PROMPT_VERSIONS
from app.agents.catalyst_research.prompts import registry_selection_prompt, source_selection_prompt


def test_source_selection_requires_archive_pages_instead_of_detail_pages():
    prompt = source_selection_prompt(
        {"ticker": "ACME", "company_name": "Acme Corporation"},
        [{"result_id": 1, "url": "https://ir.acme.example/news", "title": "News archive"}],
    )

    instructions = prompt[0]["content"]

    assert "archive or list page" in instructions
    assert "individual release, article, event, or presentation detail page" in instructions


def test_registry_selection_requires_official_endpoints_and_current_evidence():
    prompt = registry_selection_prompt(
        {"ticker": "NVDA", "company_name": "NVIDIA Corporation"},
        [{"result_id": 1, "url": "https://nvidianews.nvidia.com/", "title": "NVIDIA Newsroom"}],
    )

    instructions = prompt[0]["content"]

    assert PROMPT_VERSIONS["registry_selection"] in instructions
    assert "official" in instructions
    assert "rss" in instructions
    assert "search_domain" in instructions
    assert "archive" in instructions
    assert "Do not invent URLs or evidence IDs" in instructions
    assert "evidence_result_ids refer to those current results" in instructions
    assert "not registry endpoints" in instructions
    assert "third-party" in instructions


def test_registry_selection_bumps_only_its_own_prompt_version():
    prompt_versions = dict(PROMPT_VERSIONS)
    del prompt_versions["registry_selection"]

    assert prompt_versions == {
        "source_selection": "source_selection_v2",
        "adapter_generation": "adapter_generation_v1",
        "classification": "classification_v1",
        "catalyst_assessment": "catalyst_assessment_v1",
    }
