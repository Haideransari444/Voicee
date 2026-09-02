from src.qualification.engine import evaluate_qualification


def test_qualification_passes_required_and_numeric_rules():
    result = evaluate_qualification(
        {
            "decision_maker": True,
            "interested": "yes",
            "company_size": 25,
            "budget": "750",
        },
        {
            "required": {"decision_maker": True, "interested": True},
            "numeric": {
                "company_size": {"gte": 10},
                "budget": {"gte": 500},
            },
        },
    )

    assert result["qualified"] is True
    assert result["score"] == 100
    assert result["failed_rules"] == []
    assert result["missing_fields"] == []


def test_qualification_reports_failed_and_missing_rules_deterministically():
    result = evaluate_qualification(
        {"decision_maker": False, "company_size": 4},
        {
            "required": {"decision_maker": True, "interested": True},
            "numeric": {"company_size": {"gte": 10}, "budget": {"gte": 500}},
        },
    )

    assert result["qualified"] is False
    assert result["score"] == 0
    assert result["missing_fields"] == ["budget", "interested"]
    assert [item["field"] for item in result["failed_rules"]] == [
        "decision_maker",
        "interested",
        "budget",
        "company_size",
    ]


def test_qualification_fails_closed_when_no_rules_are_configured():
    result = evaluate_qualification({"interested": True}, {})

    assert result["qualified"] is False
    assert result["score"] == 0
    assert result["evaluated_rule_count"] == 0


def test_unknown_rule_group_fails_closed():
    result = evaluate_qualification(
        {"interested": True},
        {"required": {"interested": True}, "model_score": {"gte": 0.5}},
    )

    assert result["qualified"] is False
    assert result["score"] == 50
    assert result["failed_rules"][0]["field"] == "model_score"
