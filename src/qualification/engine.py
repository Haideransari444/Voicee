"""Pure, deterministic lead qualification rule evaluation.

The evaluator performs no I/O and never calls a model. A campaign may currently
define exact/required rules and numeric comparisons. Unknown rule groups or numeric
operators fail closed instead of silently qualifying a lead.
"""

from math import isfinite
from typing import Any, Dict, Iterable, List, Tuple

from .schemas import QualificationResult, RuleEvaluation


_NUMERIC_OPERATORS = {
    "gte": lambda actual, expected: actual >= expected,
    "gt": lambda actual, expected: actual > expected,
    "lte": lambda actual, expected: actual <= expected,
    "lt": lambda actual, expected: actual < expected,
    "eq": lambda actual, expected: actual == expected,
}


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _coerce_number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("booleans are not numeric qualification values")
    number = float(value)
    if not isfinite(number):
        raise ValueError("numeric qualification values must be finite")
    return number


def _exact_equal(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        if isinstance(actual, bool):
            return actual is expected
        if isinstance(actual, str):
            normalized = actual.strip().casefold()
            if normalized in {"true", "yes", "1"}:
                return expected is True
            if normalized in {"false", "no", "0"}:
                return expected is False
        return False
    if isinstance(expected, str) and isinstance(actual, str):
        return actual.strip().casefold() == expected.strip().casefold()
    return actual == expected


def _append_result(
    target_passed: List[Dict[str, Any]],
    target_failed: List[Dict[str, Any]],
    *,
    field: str,
    rule: str,
    expected: Any,
    actual: Any,
    passed: bool,
) -> None:
    item = RuleEvaluation(
        field=field,
        rule=rule,
        expected=expected,
        actual=actual,
        passed=passed,
    ).to_dict()
    (target_passed if passed else target_failed).append(item)


def evaluate_qualification(
    lead_state: Dict[str, Any] | None,
    campaign_rules: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Evaluate campaign rules against structured lead state.

    Supported rule shape::

        {
          "required": {"decision_maker": true, "interested": true},
          "equals": {"region": "north"},
          "numeric": {"company_size": {"gte": 10}, "budget": {"gte": 500}}
        }

    Qualification requires every configured rule to pass. Score is the rounded
    percentage of configured rule leaves that passed. With no rules, the result
    fails closed with score zero.
    """
    state = lead_state if isinstance(lead_state, dict) else {}
    rules = campaign_rules if isinstance(campaign_rules, dict) else {}
    passed: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    missing: set[str] = set()
    required_count = 0

    for group_name in ("required", "equals"):
        group = rules.get(group_name) or {}
        if not isinstance(group, dict):
            _append_result(
                passed,
                failed,
                field=group_name,
                rule="valid_group",
                expected="object",
                actual=type(group).__name__,
                passed=False,
            )
            continue
        for field_name in sorted(group):
            expected = group[field_name]
            actual = state.get(field_name)
            if group_name == "required":
                required_count += 1
            if _is_missing(actual):
                missing.add(str(field_name))
                rule_passed = False
            else:
                rule_passed = _exact_equal(actual, expected)
            _append_result(
                passed,
                failed,
                field=str(field_name),
                rule="equals",
                expected=expected,
                actual=actual,
                passed=rule_passed,
            )

    numeric = rules.get("numeric") or {}
    if not isinstance(numeric, dict):
        _append_result(
            passed,
            failed,
            field="numeric",
            rule="valid_group",
            expected="object",
            actual=type(numeric).__name__,
            passed=False,
        )
    else:
        for field_name in sorted(numeric):
            constraints = numeric[field_name]
            actual = state.get(field_name)
            if not isinstance(constraints, dict) or not constraints:
                _append_result(
                    passed,
                    failed,
                    field=str(field_name),
                    rule="valid_numeric_rules",
                    expected="non-empty object",
                    actual=constraints,
                    passed=False,
                )
                continue
            if _is_missing(actual):
                missing.add(str(field_name))
            for operator in sorted(constraints):
                expected = constraints[operator]
                comparator = _NUMERIC_OPERATORS.get(str(operator))
                rule_passed = False
                if comparator is not None and not _is_missing(actual):
                    try:
                        rule_passed = bool(
                            comparator(_coerce_number(actual), _coerce_number(expected))
                        )
                    except (TypeError, ValueError, OverflowError):
                        rule_passed = False
                _append_result(
                    passed,
                    failed,
                    field=str(field_name),
                    rule=str(operator),
                    expected=expected,
                    actual=actual,
                    passed=rule_passed,
                )

    known_groups = {"required", "equals", "numeric"}
    for unknown_group in sorted(set(rules) - known_groups):
        _append_result(
            passed,
            failed,
            field=str(unknown_group),
            rule="supported_group",
            expected=sorted(known_groups),
            actual=unknown_group,
            passed=False,
        )

    total = len(passed) + len(failed)
    score = int(round((len(passed) / total) * 100)) if total else 0
    result = QualificationResult(
        qualified=bool(total > 0 and not failed),
        score=score,
        passed_rules=passed,
        failed_rules=failed,
        missing_fields=sorted(missing),
        evaluated_rule_count=total,
        required_rule_count=required_count,
    )
    return result.to_dict()
