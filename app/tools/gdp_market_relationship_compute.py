from datetime import datetime
from math import sqrt


LAG_MONTHS = [0, 3, 6, 9, 12]
PRIMARY_LAG_MONTHS = 6


def _parse_date(date_iso):
    return datetime.strptime(date_iso, "%Y-%m-%d").date()


def _quarter_index(date_iso):
    parsed = _parse_date(date_iso)
    return parsed.year * 4 + ((parsed.month - 1) // 3)


def _period_label(date_iso):
    parsed = _parse_date(date_iso)
    quarter = ((parsed.month - 1) // 3) + 1
    return f"{parsed.year} Q{quarter}"


def _pct_change(current, prior):
    if current is None or prior in {None, 0}:
        return None
    return current / prior - 1


def _direction(current, prior):
    if current is None or prior is None:
        return None
    return 1 if current >= prior else 0


def _workbook_quad_index_direction(current, prior):
    if current is None:
        return None
    if prior is None:
        prior = 0
    return 1 if current >= prior else 0


def _quad_case(index_direction, gdp_direction):
    if index_direction is None or gdp_direction is None:
        return None
    return f"{index_direction},{gdp_direction}"


def _correlation(xs, ys):
    pairs = [(x_value, y_value) for x_value, y_value in zip(xs, ys) if x_value is not None and y_value is not None]
    if len(pairs) < 2:
        return None
    x_mean = sum(x_value for x_value, _ in pairs) / len(pairs)
    y_mean = sum(y_value for _, y_value in pairs) / len(pairs)
    numerator = sum(
        (x_value - x_mean) * (y_value - y_mean) for x_value, y_value in pairs
    )
    x_denominator = sum((x_value - x_mean) ** 2 for x_value, _ in pairs)
    y_denominator = sum((y_value - y_mean) ** 2 for _, y_value in pairs)
    if x_denominator == 0 or y_denominator == 0:
        return None
    return numerator / sqrt(x_denominator * y_denominator)


def _levels_by_quarter(raw_rows, key):
    return {_quarter_index(row["date"]): row.get(key) for row in raw_rows}


def _date_by_quarter(raw_rows):
    return {_quarter_index(row["date"]): row["date"] for row in raw_rows}


def _rolling_correlation_quarters(correlation_window_years):
    return correlation_window_years * 4 + 1


def compute_lag_rows(raw_rows, source, correlation_window_years=10):
    sorted_rows = sorted(raw_rows, key=lambda row: row["date"])
    dates_by_quarter = _date_by_quarter(sorted_rows)
    gdp_levels = _levels_by_quarter(sorted_rows, "gdp_level")
    index_levels = _levels_by_quarter(sorted_rows, "index_level")
    yoy_by_quarter_lag = {}
    rolling_correlation_quarters = _rolling_correlation_quarters(
        correlation_window_years
    )
    quarter_indexes = sorted(dates_by_quarter)
    for quarter_index in quarter_indexes:
        gdp_yoy = _pct_change(
            gdp_levels.get(quarter_index),
            gdp_levels.get(quarter_index - 4),
        )
        for lag_months in LAG_MONTHS:
            lag_quarters = lag_months // 3
            yoy_by_quarter_lag[(quarter_index, lag_months)] = {
                "index_yoy": _pct_change(
                    index_levels.get(quarter_index - lag_quarters),
                    index_levels.get(quarter_index - lag_quarters - 4),
                ),
                "gdp_yoy": gdp_yoy,
            }
    lag_rows = []
    for quarter_index in quarter_indexes:
        for lag_months in LAG_MONTHS:
            window_indexes = list(
                range(
                    quarter_index - rolling_correlation_quarters + 1,
                    quarter_index + 1,
                )
            )
            current_values = yoy_by_quarter_lag[(quarter_index, lag_months)]
            window_values = [
                yoy_by_quarter_lag.get((window_index, lag_months))
                for window_index in window_indexes
            ]
            has_full_window = all(
                values is not None
                and values["index_yoy"] is not None
                and values["gdp_yoy"] is not None
                for values in window_values
            )
            lag_rows.append(
                {
                    "date": dates_by_quarter[quarter_index],
                    "lag_months": lag_months,
                    "index_yoy": current_values["index_yoy"],
                    "gdp_yoy": current_values["gdp_yoy"],
                    "rolling_correlation": _correlation(
                        [values["index_yoy"] for values in window_values],
                        [values["gdp_yoy"] for values in window_values],
                    )
                    if has_full_window
                    else None,
                    "source_workbook": source,
                    "source_sheet": "computed",
                }
            )
    return lag_rows


def compute_quad_rows(raw_rows, source):
    sorted_rows = sorted(raw_rows, key=lambda row: row["date"])
    dates_by_quarter = _date_by_quarter(sorted_rows)
    gdp_levels = _levels_by_quarter(sorted_rows, "gdp_level")
    index_levels = _levels_by_quarter(sorted_rows, "index_level")
    quad_rows = []
    for quarter_index in sorted(dates_by_quarter):
        index_direction = _workbook_quad_index_direction(
            index_levels.get(quarter_index - 2),
            index_levels.get(quarter_index - 3),
        )
        gdp_direction = _direction(
            gdp_levels.get(quarter_index),
            gdp_levels.get(quarter_index - 1),
        )
        quad_case = _quad_case(index_direction, gdp_direction)
        if quad_case is None:
            continue
        date_iso = dates_by_quarter[quarter_index]
        quad_rows.append(
            {
                "date": date_iso,
                "period_label": _period_label(date_iso),
                "primary_lag_months": PRIMARY_LAG_MONTHS,
                "index_level": index_levels.get(quarter_index - 2),
                "gdp_level": gdp_levels.get(quarter_index),
                "index_direction": index_direction,
                "gdp_direction": gdp_direction,
                "quad_case": quad_case,
                "source_workbook": source,
                "source_sheet": "computed",
            }
        )
    return quad_rows


def recompute_rolling_correlations(
    lag_rows,
    affected_dates,
    source,
    correlation_window_years=10,
):
    rolling_correlation_quarters = _rolling_correlation_quarters(
        correlation_window_years
    )
    rows_by_quarter_lag = {
        (_quarter_index(row["date"]), row["lag_months"]): row
        for row in lag_rows
    }
    affected_date_set = {str(date_value) for date_value in affected_dates}
    recomputed_rows = []
    for row in sorted(lag_rows, key=lambda value: (value["date"], value["lag_months"])):
        if row["date"] not in affected_date_set:
            continue
        quarter_index = _quarter_index(row["date"])
        window_indexes = list(
            range(
                quarter_index - rolling_correlation_quarters + 1,
                quarter_index + 1,
            )
        )
        window_rows = [
            rows_by_quarter_lag.get((window_index, row["lag_months"]))
            for window_index in window_indexes
        ]
        has_full_window = all(
            window_row is not None
            and window_row.get("index_yoy") is not None
            and window_row.get("gdp_yoy") is not None
            for window_row in window_rows
        )
        recomputed_rows.append(
            {
                **row,
                "rolling_correlation": _correlation(
                    [window_row["index_yoy"] for window_row in window_rows],
                    [window_row["gdp_yoy"] for window_row in window_rows],
                )
                if has_full_window
                else None,
                "source_workbook": source,
                "source_sheet": "computed",
            }
        )
    return recomputed_rows
