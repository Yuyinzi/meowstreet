from app.agents.catalyst_research.prompts import source_selection_prompt


def test_source_selection_requires_archive_pages_instead_of_detail_pages():
    prompt = source_selection_prompt(
        {"ticker": "ACME", "company_name": "Acme Corporation"},
        [{"result_id": 1, "url": "https://ir.acme.example/news", "title": "News archive"}],
    )

    instructions = prompt[0]["content"]

    assert "archive or list page" in instructions
    assert "individual release, article, event, or presentation detail page" in instructions
