from datetime import datetime

import pytest

from app.tools.macro_data_freshness_quarterly import evaluate_quarterly_policy


@pytest.mark.parametrize('at,label,target,status', [
    ('2026-04-01T03:59:59Z', '2026-03-31', '2026-03-31', 'current'),
    ('2026-04-01T04:00:00Z', '2026-03-31', '2026-06-30', 'unknown'),
    ('2026-04-01T04:00:00Z', '2026-06-30', '2026-06-30', 'current'),
    ('2026-11-19T12:00:00Z', 'invalid', '2026-12-31', 'unknown'),
])
def test_quarter_coverage_is_timezone_bound_and_does_not_assert_complete_release(at, label, target, status):
    row = {'freshness_policy': {'kind': 'current_quarter', 'timezone': 'America/New_York'}}
    result = evaluate_quarterly_policy(row, {'current_period': label}, datetime.fromisoformat(at))
    assert result['status'] == status
    assert result['expected_quarter'] == target
    if status == 'current':
        assert result['period_note'] == 'Quarter in progress'
        assert 'latest upstream revision' in result['reason']
