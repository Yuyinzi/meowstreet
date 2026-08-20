import csv

import pytest

from app.data_sources import gics_reference
from app.db import ticker_context
from scripts import import_gics_industry_tags


FIELDNAMES = [
    "record_type",
    "source",
    "source_value",
    "industry",
    "industry_group",
    "sector",
    "official_industry",
    "cycle_tag",
    "tag_source",
    "source_vintage",
    "resource_version",
]


def write_csv(tmp_path, rows):
    path = tmp_path / "gics_reference.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return path


def valid_rows():
    return [
        {
            "record_type": "industry",
            "source": "",
            "source_value": "",
            "industry": "Media",
            "industry_group": "Media & Entertainment",
            "sector": "Communication Services",
            "official_industry": "Media",
            "cycle_tag": "cyclical",
            "tag_source": "method_workbook",
            "source_vintage": "2021-gics",
            "resource_version": "gics_reference_v1",
        },
        {
            "record_type": "alias",
            "source": "yahoo",
            "source_value": "Advertising Agencies",
            "industry": "Media",
            "industry_group": "",
            "sector": "",
            "official_industry": "",
            "cycle_tag": "",
            "tag_source": "",
            "source_vintage": "",
            "resource_version": "gics_reference_v1",
        },
    ]


def test_load_gics_reference_normalizes_industries_and_aliases(tmp_path):
    path = write_csv(tmp_path, valid_rows())

    payload = gics_reference.load_gics_reference(path)

    assert payload == {
        "version": "gics_reference_v1",
        "industries": [
            {
                "industry": "Media",
                "industry_group": "Media & Entertainment",
                "sector": "Communication Services",
                "official_industry": "Media",
                "cycle_tag": "cyclical",
                "tag_source": "method_workbook",
                "source_vintage": "2021-gics",
            }
        ],
        "aliases": [
            {
                "source": "yahoo",
                "source_industry": "Advertising Agencies",
                "gics_industry": "Media",
            }
        ],
    }


def test_bundled_gics_reference_has_stable_counts():
    payload = gics_reference.load_gics_reference()

    assert len(payload["industries"]) == 69
    assert len(payload["aliases"]) == 151


def test_import_cli_uses_bundled_reference_without_workbook(tmp_path):
    db_path = tmp_path / "ticker_context.sqlite"

    result = import_gics_industry_tags.main(["--db", str(db_path)])

    con = ticker_context.connect(db_path)
    try:
        assert result == 0
        assert len(ticker_context.load_industry_tags(con)) == 69
        assert ticker_context.load_industry_alias(
            con, "yahoo", "Advertising Agencies"
        ) == {
            "source": "yahoo",
            "source_industry": "Advertising Agencies",
            "gics_industry": "Media",
        }
    finally:
        con.close()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda rows: [dict(rows[0], record_type="unknown"), rows[1]],
            "gics reference record type unknown is invalid",
        ),
        (
            lambda rows: [dict(rows[0], industry=""), rows[1]],
            "gics reference industry is required",
        ),
        (
            lambda rows: [dict(rows[0], cycle_tag="growth"), rows[1]],
            "gics reference cycle tag growth is invalid for Media",
        ),
        (
            lambda rows: [rows[0], dict(rows[0]), rows[1]],
            "gics reference industry Media is duplicated",
        ),
        (
            lambda rows: [rows[0], dict(rows[1], source_value="")],
            "gics reference alias fields are required",
        ),
        (
            lambda rows: [rows[0], rows[1], dict(rows[1])],
            "gics reference alias yahoo Advertising Agencies is duplicated",
        ),
        (
            lambda rows: [rows[0], dict(rows[1], industry="Missing")],
            "gics reference alias industry Missing is unknown",
        ),
        (
            lambda rows: [rows[0], dict(rows[1], resource_version="v2")],
            "gics reference versions are inconsistent",
        ),
    ],
)
def test_load_gics_reference_rejects_invalid_rows(tmp_path, mutation, message):
    path = write_csv(tmp_path, mutation(valid_rows()))

    with pytest.raises(ValueError, match=message):
        gics_reference.load_gics_reference(path)


@pytest.mark.parametrize("contents", ["record_type,industry\n", ""])
def test_load_gics_reference_rejects_invalid_headers(tmp_path, contents):
    path = tmp_path / "gics_reference.csv"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match="gics reference csv headers are invalid"):
        gics_reference.load_gics_reference(path)


def test_load_gics_reference_rejects_surplus_row_fields(tmp_path):
    path = write_csv(tmp_path, valid_rows())
    with path.open("a", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(
            [*valid_rows()[1].values(), "unexpected"]
        )

    with pytest.raises(ValueError, match="gics reference csv row fields are invalid"):
        gics_reference.load_gics_reference(path)
