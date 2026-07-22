"""Survey-aware PR Newswire archive discovery for ISM reports.

Exports survey-neutral HTML helpers and survey-aware listing parsing
that uses the config module for title matching and report ID generation.
"""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from app.tools import ism_report_config


MONTH_NUMBER_BY_NAME = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
}

BASE_URL = "https://www.prnewswire.com"
ARCHIVE_URL = (
    "https://www.prnewswire.com/news/institute-for-supply-management/"
    "?page={page}&pagesize={pagesize}"
)


class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_href = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.current_href = href
            self.current_text = []

    def handle_data(self, data):
        if self.current_href:
            text = data.strip()
            if text:
                self.current_text.append(text)

    def handle_endtag(self, tag):
        if tag != "a" or not self.current_href:
            return
        title = " ".join(self.current_text).strip()
        if title:
            self.links.append(
                {"url": urljoin(BASE_URL, self.current_href), "title": title}
            )
        self.current_href = None
        self.current_text = []


def archive_listing_url(page, pagesize=25):
    return ARCHIVE_URL.format(page=page, pagesize=pagesize)


def report_month_from_title(title):
    match = re.search(
        r"\b(" + "|".join(MONTH_NUMBER_BY_NAME) + r")\s+(20\d{2})\b",
        title,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"ism archive title report month is missing: {title}")
    month_name = match.group(1).lower()
    year = match.group(2)
    return f"{year}-{MONTH_NUMBER_BY_NAME[month_name]}-01"


def report_month_from_url(url):
    match = re.search(
        r"(?:^|[-/])(" + "|".join(MONTH_NUMBER_BY_NAME) + r")[-_](20\d{2})(?:[-_.]|$)",
        url,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"ism archive url report month is missing: {url}")
    month_name = match.group(1).lower()
    year = match.group(2)
    return f"{year}-{MONTH_NUMBER_BY_NAME[month_name]}-01"


def report_id(report_month, survey_type):
    config = ism_report_config.load_survey_config(survey_type)
    year, month, _day = report_month.split("-")
    return f"{config['report_id_prefix']}_{year}_{month}"


def extract_all_links(html):
    """Return all links from an archive listing page, unfiltered by survey."""
    parser = LinkExtractor()
    parser.feed(html)
    return parser.links


def parse_archive_listing(html, survey_type):
    config = ism_report_config.load_survey_config(survey_type)
    matcher = config["prnewswire_title_matcher"]

    parser = LinkExtractor()
    parser.feed(html)
    result = []
    seen = set()
    for link in parser.links:
        if link["url"] in seen:
            continue
        if not matcher(link["title"]):
            continue
        seen.add(link["url"])
        try:
            link["report_month"] = report_month_from_title(link["title"])
        except ValueError:
            try:
                link["report_month"] = report_month_from_url(link["url"])
            except ValueError:
                continue
        link["report_id"] = report_id(link["report_month"], survey_type)
        result.append(link)
    return result
