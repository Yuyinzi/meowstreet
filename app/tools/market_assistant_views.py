import re

_VIEW_VERSION_BY_TYPE = {
    "setup_explanation": "setup_explanation_v1",
    "indicator_explanation": "indicator_explanation_v1",
    "method_explanation": "method_explanation_v1",
    "evidence_detail": "evidence_detail_v1",
    "react_anchor": "react_anchor_v1",
}

_RESULT_LAYERS = (
    "macro_regime",
    "market_confirmation",
    "market_setup",
    "portfolio_posture",
)

_KNOWLEDGE_TYPES = frozenset(
    {"indicator_definition", "indicator_method", "indicator_source"}
)

_TEST_ID_BY_INDICATOR = {
    "sp500_close": "equity",
    "sp500_market_phase": "equity",
    "credit_conditions": "credit",
    "vix": "vix",
}

_INDICATOR_FAMILIES = {
    "vix": frozenset({"vix", "vix_level"}),
    "sp500_close": frozenset({"sp500_close", "sp500_market_phase"}),
    "credit_conditions": frozenset({"credit_conditions"}),
    "ism_manufacturing_pmi": frozenset({"ism_manufacturing_pmi", "ism_surveys"}),
    "m2_money_stock": frozenset({"m2_money_stock", "m2_liquidity"}),
    "initial_claims_sa": frozenset({"initial_claims_sa", "jobless_claims"}),
    "continuing_claims_sa": frozenset({"continuing_claims_sa", "jobless_claims"}),
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

_DISPLAY_LABELS = {
    "zh": {
        "rising": "上升",
        "slowing": "放缓",
        "falling": "下降",
        "improving": "改善",
        "stable": "稳定",
        "growth_accelerating": "增长加速",
        "growth_decelerating": "增长放缓",
        "contraction_risk_rising": "收缩风险上升",
        "early_recovery": "早期复苏",
        "growth_stable": "增长稳定",
        "insufficient_data": "数据不足",
        "confirming_upside": "上行方向已确认",
        "partially_confirming_upside": "上行方向部分确认",
        "not_confirming_upside": "上行方向未确认",
        "confirming_downside": "下行方向已确认",
        "partially_confirming_downside": "下行方向部分确认",
        "not_confirming_downside": "下行方向未确认",
        "not_applicable": "不适用",
        "macro_improving_market_confirming": "宏观改善且市场确认",
        "macro_improving_partially_confirmed": "宏观改善且部分确认",
        "macro_improving_price_not_confirming": "宏观改善但价格未确认",
        "macro_weakening_market_confirming": "宏观走弱且市场确认",
        "macro_weakening_partially_confirmed": "宏观走弱且部分确认",
        "macro_weakening_price_not_confirming": "宏观走弱但价格未确认",
        "mixed_or_transition": "方向不明确",
        "risk_on": "偏积极",
        "mild_risk_on": "轻度偏积极",
        "neutral_selective": "中性选择",
        "defensive": "防御",
        "mild_risk_off": "轻度偏防御",
        "long": "偏多",
        "modest_long": "小幅偏多",
        "neutral": "中性",
        "reduced": "降低",
        "modest_defensive": "小幅偏防御",
        "broad_and_selective_positions": "广泛而有选择的仓位",
        "selective_positions": "有选择地承担风险",
        "defensive_or_hedged_positions": "防御或对冲",
        "selective_defensive_positions": "有选择地防御",
        "permitted_with_risk_controls": "在风险控制下允许",
        "avoid_large_directional_exposure": "避免大规模方向性敞口",
        "avoid_long_broad_beta": "避免做多宽基",
        "reduce_large_directional_exposure": "降低大规模方向性敞口",
        "bull_market": "股票仍处于上涨趋势",
        "bear_market": "股票处于下跌趋势",
        "risk_rising": "信贷风险正在上升",
        "healthy": "信贷状况健康",
        "mixed_credit": "信贷状况分化",
        "weak_credit_warning": "信贷状况出现预警",
        "crisis_stress": "信贷危机承压",
        "risk_off": "风险规避",
        "serious_deterioration": "严重恶化",
        "stress": "承压",
        "supportive": "支持",
        "selective": "选择性",
        "supports": "与当前增长方向一致",
        "conflicts": "与当前增长方向不一致",
        "unavailable": "当前不可用",
        "applied": "已参与",
        "not_applied": "未参与",
        "partial": "部分一致",
        "conflicting": "相互冲突",
        "agrees": "一致",
        "expanding": "扩张",
        "shock": "冲击",
        "market_setup_and_posture_change": "市场设定与组合姿态改变",
        "confirmation_test_result_change": "确认测试结果改变",
        "maintain_modest_long_exposure": "保持小幅偏多敞口",
        "use_moderate_position_sizing": "使用适中仓位",
        "prefer_selective_positions": "优先有选择地建仓",
        "large_broad_beta_directional_exposure": "大规模宽基方向性敞口",
        "increasing_leverage_without_confirmation": "在未确认时加杠杆",
        "maintain_neutral_net_exposure": "保持中性敞口",
        "maintain_reduced_net_exposure": "保持降低的敞口",
        "use_reduced_position_sizing": "使用降低的仓位",
        "prefer_defensive_or_hedged_positions": "优先防御或对冲",
        "maintain_modest_defensive_exposure": "保持小幅偏防御敞口",
        "prefer_selective_defensive_positions": "优先有选择地防御",
        "defer_new_directional_exposure": "推迟新的方向性敞口",
        "ignoring_risk_controls": "忽视风险控制",
        "adding_leverage_without_position_limits": "在无仓位限制时加杠杆",
        "large_directional_long_exposure": "大规模方向性做多敞口",
        "unhedged_broad_beta_exposure": "未对冲的宽基敞口",
        "increasing_leverage_during_confirmed_risk_off": "在确认风险规避时加杠杆",
        "increasing_leverage_without_complete_evidence": "在证据不足时加杠杆",
        "indicator_current": "当前数值",
        "indicator_history": "历史走势",
        "period_comparison": "区间比较",
        "release_history": "发布历史",
        "available": "可用",
        "missing": "数据缺失",
        "stale": "数据已过期",
        "invalid": "数据无效",
        "unsupported": "暂不支持",
    },
    "en": {
        "rising": "rising",
        "slowing": "slowing",
        "falling": "falling",
        "improving": "improving",
        "stable": "stable",
        "growth_accelerating": "growth accelerating",
        "growth_decelerating": "growth decelerating",
        "contraction_risk_rising": "contraction risk rising",
        "early_recovery": "early recovery",
        "growth_stable": "growth stable",
        "insufficient_data": "insufficient data",
        "confirming_upside": "upside broadly confirmed",
        "partially_confirming_upside": "upside partially confirmed",
        "not_confirming_upside": "upside not confirmed",
        "confirming_downside": "downside broadly confirmed",
        "partially_confirming_downside": "downside partially confirmed",
        "not_confirming_downside": "downside not confirmed",
        "not_applicable": "not applicable",
        "macro_improving_market_confirming": "macro improving and market confirming",
        "macro_improving_partially_confirmed": "macro improving and partially confirmed",
        "macro_improving_price_not_confirming": "macro improving but price not confirming",
        "macro_weakening_market_confirming": "macro weakening and market confirming",
        "macro_weakening_partially_confirmed": "macro weakening and partially confirmed",
        "macro_weakening_price_not_confirming": "macro weakening but price not confirming",
        "mixed_or_transition": "mixed or transition",
        "risk_on": "risk-on",
        "mild_risk_on": "mildly risk-on",
        "neutral_selective": "neutral and selective",
        "defensive": "defensive",
        "mild_risk_off": "mildly risk-off",
        "long": "long",
        "modest_long": "modest long",
        "neutral": "neutral",
        "reduced": "reduced",
        "modest_defensive": "modestly defensive",
        "broad_and_selective_positions": "broad and selective positions",
        "selective_positions": "take risk selectively",
        "defensive_or_hedged_positions": "defensive or hedged positions",
        "selective_defensive_positions": "selective defensive positions",
        "permitted_with_risk_controls": "permitted with risk controls",
        "avoid_large_directional_exposure": "avoid large directional exposure",
        "avoid_long_broad_beta": "avoid long broad beta",
        "reduce_large_directional_exposure": "reduce large directional exposure",
        "bull_market": "stocks remain in an uptrend",
        "bear_market": "stocks are in a downtrend",
        "risk_rising": "credit risk is rising",
        "healthy": "credit is healthy",
        "mixed_credit": "credit is mixed",
        "weak_credit_warning": "weak credit warning",
        "crisis_stress": "credit crisis stress",
        "risk_off": "risk-off",
        "serious_deterioration": "serious deterioration",
        "stress": "stress",
        "supportive": "supportive",
        "selective": "selective",
        "supports": "consistent with the growth direction",
        "conflicts": "inconsistent with the growth direction",
        "unavailable": "currently unavailable",
        "applied": "applied",
        "not_applied": "not applied",
        "partial": "partially consistent",
        "conflicting": "conflicting",
        "agrees": "consistent",
        "expanding": "expanding",
        "shock": "shock",
        "market_setup_and_posture_change": "market setup and posture change",
        "confirmation_test_result_change": "confirmation test result change",
        "maintain_modest_long_exposure": "maintain modest long exposure",
        "use_moderate_position_sizing": "use moderate position sizing",
        "prefer_selective_positions": "prefer selective positions",
        "large_broad_beta_directional_exposure": "large broad-beta directional exposure",
        "increasing_leverage_without_confirmation": "increasing leverage without confirmation",
        "maintain_neutral_net_exposure": "maintain neutral net exposure",
        "maintain_reduced_net_exposure": "maintain reduced net exposure",
        "use_reduced_position_sizing": "use reduced position sizing",
        "prefer_defensive_or_hedged_positions": "prefer defensive or hedged positions",
        "maintain_modest_defensive_exposure": "maintain modest defensive exposure",
        "prefer_selective_defensive_positions": "prefer selective defensive positions",
        "defer_new_directional_exposure": "defer new directional exposure",
        "ignoring_risk_controls": "ignoring risk controls",
        "adding_leverage_without_position_limits": "adding leverage without position limits",
        "large_directional_long_exposure": "large directional long exposure",
        "unhedged_broad_beta_exposure": "unhedged broad-beta exposure",
        "increasing_leverage_during_confirmed_risk_off": "increasing leverage during confirmed risk-off",
        "increasing_leverage_without_complete_evidence": "increasing leverage without complete evidence",
        "indicator_current": "current value",
        "indicator_history": "history",
        "period_comparison": "period comparison",
        "release_history": "release history",
        "available": "available",
        "missing": "missing",
        "stale": "stale",
        "invalid": "invalid",
        "unsupported": "unsupported",
    },
}

_FALLBACK_LABELS = {"zh": "已确认状态", "en": "approved state"}


def build_explanation_view(route, artifacts, *, question, answer_language=None):
    if not isinstance(route, dict):
        raise ValueError("route is required")
    if not isinstance(artifacts, dict):
        raise ValueError("artifacts are required")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is required")
    view_type = route.get("view_type")
    if view_type not in _VIEW_VERSION_BY_TYPE:
        raise ValueError(f"route view type is unknown: {view_type}")
    version = _view_version(route, artifacts)
    if answer_language not in {None, "en", "zh"}:
        raise ValueError("answer language is invalid")
    language = answer_language or _question_language(question)
    object_map = _object_map(artifacts)
    as_of, evidence_through = _context_dates(artifacts)
    if version == "setup_explanation_v1":
        return _build_setup_view(object_map, language, as_of, evidence_through)
    if version == "indicator_explanation_v1":
        return _build_indicator_view(
            route, artifacts, object_map, language, as_of, evidence_through
        )
    if version == "method_explanation_v1":
        return _build_method_view(route, object_map, language, as_of, evidence_through)
    if version == "evidence_detail_v1":
        return _build_evidence_detail_view(
            route, artifacts, object_map, language, as_of, evidence_through
        )
    if version == "react_anchor_v1":
        return _build_react_anchor_view(
            route, artifacts, object_map, language, as_of, evidence_through
        )
    if version == "exploration_explanation_v1":
        return _build_exploration_view(artifacts, language, as_of, evidence_through)
    if version == "snapshot_comparison_v1":
        return _build_comparison_view(artifacts, language, as_of, evidence_through)
    raise ValueError(f"view version is unknown: {version}")


def _view_version(route, artifacts):
    view_type = route["view_type"]
    if view_type != "react_anchor":
        return _VIEW_VERSION_BY_TYPE[view_type]
    if _has_exploration_result(artifacts):
        return "exploration_explanation_v1"
    if _has_snapshot_delta(artifacts):
        return "snapshot_comparison_v1"
    return "react_anchor_v1"


def _question_language(question):
    return "zh" if _CJK_RE.search(question) else "en"


def _object_map(artifacts):
    index = {}
    for artifact_id in sorted(artifacts):
        artifact = artifacts[artifact_id]
        for obj in artifact.get("object_index") or []:
            key = (obj["object_type"], obj["object_id"])
            if key not in index:
                index[key] = {"artifact_id": artifact_id, "object": obj}
    return index


def _context_dates(artifacts):
    for artifact_id in sorted(artifacts):
        payload = artifacts[artifact_id].get("payload") or {}
        if "as_of" in payload:
            return payload.get("as_of"), payload.get("evidence_through")
    return None, None


def _context_id(artifacts):
    for artifact_id in sorted(artifacts):
        payload = artifacts[artifact_id].get("payload") or {}
        if "context_id" in payload:
            return payload.get("context_id")
    return None


def _has_exploration_result(artifacts):
    return any(
        artifact.get("artifact_kind") == "exploration_result"
        for artifact in artifacts.values()
    )


def _has_snapshot_delta(artifacts):
    for artifact in artifacts.values():
        for obj in artifact.get("object_index") or []:
            if obj.get("object_type") == "snapshot_delta":
                return True
    return False


def _display(code, language):
    if not isinstance(code, str) or not code:
        return None
    return _DISPLAY_LABELS[language].get(code, _FALLBACK_LABELS[language])


def _ref(entry):
    return {
        "artifact_id": entry["artifact_id"],
        "object_type": entry["object"]["object_type"],
        "object_id": entry["object"]["object_id"],
    }


def _audit_refs(entries):
    return [_ref(entry) for entry in entries]


def _result_object(object_map, layer):
    return object_map.get(("market_setup_result", layer))


def _evidence_facts(object_map):
    return [
        entry
        for (object_type, object_id), entry in sorted(object_map.items())
        if object_type == "evidence_fact"
    ]


def _confirmation_facts(object_map):
    return [
        entry
        for entry in _evidence_facts(object_map)
        if (entry["object"]["payload"].get("role") or {}).get("function")
        == "confirmation_test"
    ]


def _build_setup_view(object_map, language, as_of, evidence_through):
    results = {}
    result_entries = []
    for layer in _RESULT_LAYERS:
        entry = _result_object(object_map, layer)
        if entry is None:
            continue
        payload = entry["object"]["payload"]
        results[layer] = {
            "label": payload.get("label"),
            "meaning": _display(payload.get("code"), language),
        }
        result_entries.append(entry)

    selector = {}
    selector_entries = []
    for entry in _evidence_facts(object_map):
        payload = entry["object"]["payload"]
        if (payload.get("role") or {}).get("function") != "selector":
            continue
        decision_result = payload.get("decision_result") or {}
        selector = {
            "fact_id": payload.get("fact_id"),
            "label": payload.get("label"),
            "input_state": _display(decision_result.get("input_state"), language),
            "selected": _display(decision_result.get("selected"), language),
        }
        selector_entries.append(entry)
        break

    confirmation_entries = []
    for entry in _confirmation_facts(object_map):
        payload = entry["object"]["payload"]
        test_id = _TEST_ID_BY_INDICATOR.get(payload.get("indicator_id"))
        if test_id is None:
            continue
        confirmation_entries.append(entry)
    confirmation_tests = [
        _confirmation_test_projection(entry, language) for entry in confirmation_entries
    ]

    relationship_entries = []
    for entry in _evidence_facts(object_map):
        payload = entry["object"]["payload"]
        role = payload.get("role") or {}
        if role.get("function") != "contextual_relationship":
            continue
        if role.get("target_layer") != "macro_regime":
            continue
        relationship_entries.append(entry)
    relevant_relationships = [
        _relationship_projection(entry, language) for entry in relationship_entries
    ]

    posture_meaning = {}
    posture_entries = []
    posture_result = _result_object(object_map, "portfolio_posture")
    posture_contract = object_map.get(("method_contract", "posture_matrix"))
    if posture_result is not None:
        payload = posture_result["object"]["payload"]
        action_labels = {}
        if posture_contract is not None:
            explanation = (
                posture_contract["object"]["payload"].get("explanation_contract") or {}
            )
            action_labels = explanation.get("action_labels") or {}
        posture_meaning = {
            "label": payload.get("label"),
            "meaning": _display(payload.get("code"), language),
            "net_exposure": _display(payload.get("net_exposure"), language),
            "implementation": _display(payload.get("implementation"), language),
            "broad_beta": _display(payload.get("broad_beta"), language),
            "positioning": [
                _posture_action(item, action_labels, language)
                for item in payload.get("positioning") or []
            ],
            "avoid": [
                _posture_action(item, action_labels, language)
                for item in payload.get("avoid") or []
            ],
        }
        posture_entries.append(posture_result)
        if posture_contract is not None:
            posture_entries.append(posture_contract)

    counterfactual_entries = [
        entry
        for (object_type, object_id), entry in sorted(object_map.items())
        if object_type == "market_setup"
    ]
    counterfactuals = [
        _counterfactual_projection(entry, language) for entry in counterfactual_entries
    ]

    audit_entries = []
    for entry in (
        result_entries
        + selector_entries
        + confirmation_entries
        + relationship_entries
        + posture_entries
        + counterfactual_entries
    ):
        if entry not in audit_entries:
            audit_entries.append(entry)

    return {
        "view_version": "setup_explanation_v1",
        "question_language": language,
        "as_of": as_of,
        "evidence_through": evidence_through,
        "results": results,
        "macro_selector": selector,
        "confirmation_tests": confirmation_tests,
        "relevant_relationships": relevant_relationships,
        "posture_meaning": posture_meaning,
        "counterfactuals": counterfactuals,
        "audit_objects": _audit_refs(audit_entries),
    }


def _confirmation_test_projection(entry, language):
    payload = entry["object"]["payload"]
    test_id = _TEST_ID_BY_INDICATOR[payload["indicator_id"]]
    decision_result = payload.get("decision_result") or {}
    evaluation = decision_result.get("evaluation") or {}
    accepted = payload.get("accepted_values") or {}
    single_value = next(iter(accepted.values())) if len(accepted) == 1 else None
    if isinstance(single_value, (int, float)) and not isinstance(single_value, bool):
        value = single_value
    else:
        value = _display(single_value, language)
    return {
        "test_id": test_id,
        "label": payload.get("label"),
        "value": value,
        "confirms": evaluation.get("result"),
        "participation": _display(
            (payload.get("participation") or {}).get("state"), language
        ),
    }


def _relationship_projection(entry, language):
    payload = entry["object"]["payload"]
    decision_result = payload.get("decision_result") or {}
    relationship = decision_result.get("relationship")
    return {
        "fact_id": payload.get("fact_id"),
        "label": payload.get("label"),
        "relationship": _display(relationship, language),
    }


def _posture_action(item, action_labels, language):
    code = item.get("code") if isinstance(item, dict) else item
    if isinstance(item, dict) and item.get("label"):
        return item["label"]
    if code in action_labels:
        return action_labels[code]
    return _display(code, language)


def _counterfactual_projection(entry, language):
    payload = entry["object"]["payload"]
    confirmation_change = payload.get("confirmation_change") or {}
    posture_change = payload.get("posture_change") or {}
    return {
        "counterfactual_id": payload.get("object_id")
        or payload.get("counterfactual_id"),
        "setup_from": _display(payload.get("from_code"), language),
        "setup_to": _display(payload.get("to_code"), language),
        "confirmation_from": _display(confirmation_change.get("from"), language),
        "confirmation_to": _display(confirmation_change.get("to"), language),
        "posture_from": _display(posture_change.get("from"), language),
        "posture_to": _display(posture_change.get("to"), language),
        "decision_effect": _display(payload.get("decision_effect"), language),
    }


def _focus_indicator(route):
    for operation in route.get("initial_operations") or []:
        indicator_id = operation.get("indicator_id")
        if indicator_id:
            return indicator_id
    return None


def _indicator_family(focus):
    return _INDICATOR_FAMILIES.get(focus, frozenset({focus}))


def _build_indicator_view(
    route, artifacts, object_map, language, as_of, evidence_through
):
    focus = _focus_indicator(route)
    family = _indicator_family(focus)
    confirmation_tests = []
    method_objects = []
    observation_objects = []
    audit_entries = []
    for entry in _confirmation_facts(object_map):
        payload = entry["object"]["payload"]
        if payload.get("indicator_id") not in family:
            continue
        confirmation_tests.append(_confirmation_test_projection(entry, language))
        audit_entries.append(entry)
    for (object_type, object_id), entry in sorted(object_map.items()):
        if object_type not in _KNOWLEDGE_TYPES:
            continue
        payload = entry["object"]["payload"]
        if payload.get("indicator_id") not in family:
            continue
        method_objects.append(_method_object_projection(entry))
        audit_entries.append(entry)
    for artifact_id in sorted(artifacts):
        artifact = artifacts[artifact_id]
        if artifact.get("artifact_kind") != "exploration_result":
            continue
        query = (artifact.get("payload") or {}).get("query_contract") or {}
        if query.get("indicator_id") not in family:
            continue
        for obj in artifact.get("object_index") or []:
            observation_objects.append(_observation_object_projection(obj))
            audit_entries.append(
                {
                    "artifact_id": artifact_id,
                    "object": obj,
                }
            )
    return {
        "view_version": "indicator_explanation_v1",
        "question_language": language,
        "as_of": as_of,
        "evidence_through": evidence_through,
        "indicator_id": focus,
        "confirmation_tests": confirmation_tests,
        "method_objects": method_objects,
        "observation_objects": observation_objects,
        "audit_objects": _audit_refs(audit_entries),
    }


def _method_object_projection(entry):
    payload = entry["object"]["payload"]
    projection = {
        "record_id": payload.get("record_id"),
        "object_type": payload.get("object_type"),
        "indicator_id": payload.get("indicator_id"),
        "title": payload.get("title"),
        "explanation": payload.get("explanation"),
    }
    if payload.get("formula"):
        projection["formula"] = payload.get("formula")
    return projection


def _observation_object_projection(obj):
    payload = obj.get("payload") or {}
    projection = {
        "object_type": obj["object_type"],
        "object_id": obj["object_id"],
    }
    for key in ("date", "value", "period", "statistic_id"):
        if key in payload:
            projection[key] = payload[key]
    return projection


def _build_method_view(route, object_map, language, as_of, evidence_through):
    focus = _focus_indicator(route)
    family = _indicator_family(focus)
    method_objects = []
    audit_entries = []
    for (object_type, object_id), entry in sorted(object_map.items()):
        if object_type not in _KNOWLEDGE_TYPES:
            continue
        payload = entry["object"]["payload"]
        if payload.get("indicator_id") not in family:
            continue
        method_objects.append(_method_object_projection(entry))
        audit_entries.append(entry)
    return {
        "view_version": "method_explanation_v1",
        "question_language": language,
        "as_of": as_of,
        "evidence_through": evidence_through,
        "indicator_id": focus,
        "method_objects": method_objects,
        "audit_objects": _audit_refs(audit_entries),
    }


def _build_evidence_detail_view(
    route, artifacts, object_map, language, as_of, evidence_through
):
    for artifact_id in sorted(artifacts):
        artifact = artifacts[artifact_id]
        payload = artifact.get("payload") or {}
        if payload.get("fact_id") is None:
            continue
        detail = payload.get("detail") or {}
        topics = payload.get("topics") or []
        view = {
            "view_version": "evidence_detail_v1",
            "question_language": language,
            "as_of": as_of,
            "evidence_through": evidence_through,
            "fact_id": payload["fact_id"],
            "label": detail.get("label"),
            "detail_kind": detail.get("detail_kind"),
            "status": _display(detail.get("status"), language),
            "topics": list(topics),
        }
        for topic in topics:
            if topic in detail:
                view[topic] = detail[topic]
        view["audit_objects"] = [
            {
                "artifact_id": artifact_id,
                "object_type": obj["object_type"],
                "object_id": obj["object_id"],
            }
            for obj in artifact.get("object_index") or []
        ]
        return view
    raise ValueError("evidence detail artifact is not available")


def _build_react_anchor_view(
    route, artifacts, object_map, language, as_of, evidence_through
):
    results = {}
    audit_entries = []
    for layer in _RESULT_LAYERS:
        entry = _result_object(object_map, layer)
        if entry is None:
            continue
        results[layer] = (entry["object"]["payload"] or {}).get("label")
        audit_entries.append(entry)
    return {
        "view_version": "react_anchor_v1",
        "question_language": language,
        "as_of": as_of,
        "evidence_through": evidence_through,
        "context_id": _context_id(artifacts),
        "results": results,
        "budget": route.get("budget") or {},
        "audit_objects": _audit_refs(audit_entries),
    }


def _build_exploration_view(artifacts, language, as_of, evidence_through):
    for artifact_id in sorted(artifacts):
        artifact = artifacts[artifact_id]
        if artifact.get("artifact_kind") != "exploration_result":
            continue
        payload = artifact.get("payload") or {}
        query = payload.get("query_contract") or {}
        return {
            "view_version": "exploration_explanation_v1",
            "question_language": language,
            "as_of": as_of,
            "evidence_through": evidence_through,
            "indicator_id": query.get("indicator_id"),
            "query_kind": _display(query.get("query_kind"), language),
            "observed_window": payload.get("observed_window"),
            "data_through": payload.get("data_through"),
            "statistics": payload.get("deterministic_statistics") or {},
            "rows": payload.get("rows") or [],
            "audit_objects": [
                {
                    "artifact_id": artifact_id,
                    "object_type": obj["object_type"],
                    "object_id": obj["object_id"],
                }
                for obj in artifact.get("object_index") or []
            ],
        }
    raise ValueError("exploration artifact is not available")


def _build_comparison_view(artifacts, language, as_of, evidence_through):
    for artifact_id in sorted(artifacts):
        artifact = artifacts[artifact_id]
        payload = artifact.get("payload") or {}
        delta = payload.get("delta") or {}
        if not delta and not any(
            obj.get("object_type") == "snapshot_delta"
            for obj in artifact.get("object_index") or []
        ):
            continue
        return {
            "view_version": "snapshot_comparison_v1",
            "question_language": language,
            "as_of": as_of,
            "evidence_through": evidence_through,
            "context_a_id": payload.get("context_a_id"),
            "context_b_id": payload.get("context_b_id"),
            "results_changed": delta.get("results_changed"),
            "changes": delta.get("changes") or [],
            "audit_objects": [
                {
                    "artifact_id": artifact_id,
                    "object_type": obj["object_type"],
                    "object_id": obj["object_id"],
                }
                for obj in artifact.get("object_index") or []
            ],
        }
    raise ValueError("comparison artifact is not available")
