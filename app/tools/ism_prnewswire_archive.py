import re
from html.parser import HTMLParser
from urllib.parse import urljoin


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


def is_manufacturing_report_title(title):
    normalized = re.sub(r"\s+", " ", title)
    return (
        "Manufacturing PMI" in normalized
        and "ISM" in normalized
        and "Report" in normalized
        and "Services" not in normalized
        and "Hospital" not in normalized
    )


def parse_archive_listing(html):
    parser = LinkExtractor()
    parser.feed(html)
    result = []
    seen = set()
    for link in parser.links:
        if link["url"] in seen:
            continue
        if not is_manufacturing_report_title(link["title"]):
            continue
        seen.add(link["url"])
        result.append(link)
    return result
