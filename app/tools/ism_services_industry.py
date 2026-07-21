CANONICAL_INDUSTRIES = (
    "Accommodation & Food Services",
    "Agriculture, Forestry, Fishing & Hunting",
    "Arts, Entertainment & Recreation",
    "Construction",
    "Educational Services",
    "Finance & Insurance",
    "Health Care & Social Assistance",
    "Information",
    "Management of Companies & Support Services",
    "Mining",
    "Other Services",
    "Professional, Scientific & Technical Services",
    "Public Administration",
    "Real Estate, Rental & Leasing",
    "Retail Trade",
    "Transportation & Warehousing",
    "Utilities",
    "Wholesale Trade",
)

_CANONICAL_SET = frozenset(CANONICAL_INDUSTRIES)


def normalize_industry(name):
    if not name or not isinstance(name, str):
        raise ValueError("industry name is required")
    normalized = " ".join(name.split())
    if normalized in _CANONICAL_SET:
        return normalized
    raise ValueError(f"unknown services industry: {normalized}")


def _group_rankings(rankings):
    groups = {}
    for row in rankings:
        try:
            industry = normalize_industry(row["industry"])
        except ValueError:
            continue
        groups.setdefault(industry, []).append(row)
    for industry in groups:
        groups[industry].sort(key=lambda r: r["date"])
    return groups


def _direction_change(prev_direction, curr_direction):
    if prev_direction == curr_direction:
        return None
    return f"{prev_direction}_to_{curr_direction}"


def _month_diff(date1, date2):
    y1, m1, _ = date1.split("-")
    y2, m2, _ = date2.split("-")
    return (int(y1) * 12 + int(m1)) - (int(y2) * 12 + int(m2))


def _positive_streak(rows):
    streak = 0
    prev_date = None
    for row in reversed(rows):
        if row["direction"] != "growth":
            break
        if prev_date is not None and _month_diff(prev_date, row["date"]) != 1:
            break
        prev_date = row["date"]
        streak += 1
    return streak


def _negative_streak(rows):
    streak = 0
    prev_date = None
    for row in reversed(rows):
        if row["direction"] != "contraction":
            break
        if prev_date is not None and _month_diff(prev_date, row["date"]) != 1:
            break
        prev_date = row["date"]
        streak += 1
    return streak


def _match_comments(industry, comments):
    matched = []
    for comment in comments:
        try:
            if normalize_industry(comment["industry"]) == industry:
                matched.append(comment["comment_text"])
        except ValueError:
            pass
    return matched


def _direction_change_from_rows(rows):
    if len(rows) < 2:
        return None
    prev = rows[-2]
    curr = rows[-1]
    if prev["direction"] != curr["direction"]:
        return _direction_change(prev["direction"], curr["direction"])
    return None


def _rank_change_from_rows(rows):
    if len(rows) < 2:
        return None
    return rows[-1]["rank"] - rows[-2]["rank"]


def build_industry_payload(rankings, comments):
    groups = _group_rankings(rankings)
    industries = []
    for industry in sorted(groups):
        rows = groups[industry]
        latest = rows[-1]

        matched_comments = _match_comments(industry, comments)

        industries.append(
            {
                "industry": industry,
                "latest_date": latest["date"],
                "direction": latest["direction"],
                "rank": latest["rank"],
                "direction_change": _direction_change_from_rows(rows),
                "rank_change": _rank_change_from_rows(rows),
                "positive_streak": _positive_streak(rows),
                "negative_streak": _negative_streak(rows),
                "comments": matched_comments,
            }
        )
    return {"industries": industries}


def _latest_month_date(rankings):
    return max(row["date"] for row in rankings) if rankings else None


def build_breadth(rankings, max_date=None):
    latest = max_date or _latest_month_date(rankings)
    if latest is None or (
        max_date and not any(row["date"] == max_date for row in rankings)
    ):
        return {
            "growth_count": 0,
            "contraction_count": 0,
            "neutral_count": 0,
            "total_count": 0,
            "status": None,
        }

    growth_count = 0
    contraction_count = 0
    neutral_count = 0
    for row in rankings:
        if row["date"] != latest:
            continue
        try:
            normalize_industry(row["industry"])
        except ValueError:
            continue
        if row["direction"] == "growth":
            growth_count += 1
        elif row["direction"] == "contraction":
            contraction_count += 1
        else:
            neutral_count += 1

    total_count = growth_count + contraction_count + neutral_count

    if growth_count > contraction_count:
        status = "supportive"
    elif contraction_count > growth_count:
        status = "warning"
    else:
        status = "mixed"

    return {
        "growth_count": growth_count,
        "contraction_count": contraction_count,
        "neutral_count": neutral_count,
        "total_count": total_count,
        "status": status,
    }
