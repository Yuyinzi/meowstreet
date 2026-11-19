from calendar import monthrange
from datetime import date
from zoneinfo import ZoneInfo


def evaluate_quarterly_policy(dataset, observation, as_of):
    timezone = dataset['freshness_policy']['timezone']
    today = as_of.astimezone(ZoneInfo(timezone)).date()
    month = ((today.month - 1) // 3 + 1) * 3
    target = date(today.year, month, monthrange(today.year, month)[1]).isoformat()
    result = {'comparison_basis': 'Current-quarter coverage', 'policy_timezone': timezone, 'expected_quarter': target}
    try:
        observed = date.fromisoformat(observation['current_period'])
    except (KeyError, TypeError, ValueError):
        return {**result, 'status': 'unknown', 'reason': 'A valid quarterly period label is required'}
    current = (today.year, (today.month - 1) // 3)
    stored = (observed.year, (observed.month - 1) // 3)
    if stored != current:
        return {**result, 'status': 'unknown', 'reason': 'The stored quarter is not the current quarter; a verified publication calendar is required to assess timeliness'}
    return {**result, 'status': 'current', 'period_note': 'Quarter in progress', 'reason': 'Data is present for the current quarter; complete-quarter coverage and the latest upstream revision are not independently verified'}
