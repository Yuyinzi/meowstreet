from copy import deepcopy
from numbers import Real


def _is_number(value):
    return isinstance(value, Real) and not isinstance(value, bool)


def _get_path(payload, path):
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_path(payload, path, value):
    current = payload
    parts = path.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _compute_estimate_skew(observations):
    low = _get_path(observations, "estimates.next_year_eps_low")
    high = _get_path(observations, "estimates.next_year_eps_high")
    mean = _get_path(observations, "estimates.next_year_eps_mean")
    if not (_is_number(low) and _is_number(high) and _is_number(mean)):
        return
    midpoint = (low + high) / 2
    _set_path(observations, "estimates.next_year_eps_midpoint", midpoint)
    _set_path(observations, "estimates.next_year_eps_skew", mean - midpoint)


def _compute_pe_differential(observations):
    forward_pe = _get_path(observations, "valuation.forward_pe")
    peer_forward_pe = _get_path(observations, "valuation.peer_forward_pe")
    if not (_is_number(forward_pe) and _is_number(peer_forward_pe)):
        return
    if peer_forward_pe == 0:
        return
    _set_path(observations, "valuation.pe_differential", forward_pe / peer_forward_pe)


def _compute_abnormal_volume_ratio(observations):
    current = _get_path(observations, "volume.current")
    average = _get_path(observations, "volume.average")
    if not (_is_number(current) and _is_number(average)):
        return
    if average == 0:
        return
    _set_path(observations, "volume.abnormal_volume_ratio", current / average)


def apply_computed_indicators(observations):
    normalized = deepcopy(observations)
    _compute_estimate_skew(normalized)
    _compute_pe_differential(normalized)
    _compute_abnormal_volume_ratio(normalized)
    return normalized
