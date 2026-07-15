from app.tools import ism_prnewswire_archive


LISTING_HTML = """
<html><body>
<a href="/news-releases/manufacturing-pmi-at-53-3-june-2026-ism-manufacturing-pmi-report-302814991.html">
Jul 01, 2026, 10:00 ET Manufacturing PMI® at 53.3%; June 2026 ISM® Manufacturing PMI® Report
</a>
<a href="/news-releases/services-pmi-at-50-8-june-2026-services-ism-report-on-business.html">
Services PMI® at 50.8%; June 2026 Services ISM® Report On Business®
</a>
<a href="/news-releases/institute-for-supply-management-honors-award.html">
Institute for Supply Management® Honors Award Winner
</a>
</body></html>
"""


def test_parse_archive_listing_returns_report_month_metadata():
    html = """
    <a href="/news-releases/manufacturing-pmi-at-52-6-january-2026-ism-manufacturing-pmi-report-302700001.html">
      Manufacturing PMI at 52.6%; January 2026 ISM Manufacturing PMI Report
    </a>
    """

    reports = ism_prnewswire_archive.parse_archive_listing(html)

    assert reports == [
        {
            "url": "https://www.prnewswire.com/news-releases/manufacturing-pmi-at-52-6-january-2026-ism-manufacturing-pmi-report-302700001.html",
            "title": "Manufacturing PMI at 52.6%; January 2026 ISM Manufacturing PMI Report",
            "report_month": "2026-01-01",
            "report_id": "ism_manufacturing_2026_01",
        }
    ]


def test_parse_archive_listing_returns_manufacturing_report_urls_only():
    result = ism_prnewswire_archive.parse_archive_listing(LISTING_HTML)

    assert result == [
        {
            "title": "Jul 01, 2026, 10:00 ET Manufacturing PMI® at 53.3%; June 2026 ISM® Manufacturing PMI® Report",
            "url": "https://www.prnewswire.com/news-releases/manufacturing-pmi-at-53-3-june-2026-ism-manufacturing-pmi-report-302814991.html",
            "report_month": "2026-06-01",
            "report_id": "ism_manufacturing_2026_06",
        }
    ]


def test_archive_listing_url_uses_page_and_pagesize():
    assert ism_prnewswire_archive.archive_listing_url(3, 50) == (
        "https://www.prnewswire.com/news/institute-for-supply-management/?page=3&pagesize=50"
    )
