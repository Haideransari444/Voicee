"""Typed schemas shared by the outbound qualification engine and tools."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class LeadOutcome(str, Enum):
    PENDING = "PENDING"
    DIALING = "DIALING"
    RINGING = "RINGING"
    IN_CALL = "IN_CALL"
    QUALIFIED = "QUALIFIED"
    TRANSFERRED = "TRANSFERRED"
    NOT_QUALIFIED = "NOT_QUALIFIED"
    NOT_INTERESTED = "NOT_INTERESTED"
    NO_BUDGET = "NO_BUDGET"
    WRONG_PERSON = "WRONG_PERSON"
    CALLBACK = "CALLBACK"
    NO_ANSWER = "NO_ANSWER"
    BUSY = "BUSY"
    VOICEMAIL = "VOICEMAIL"
    FAILED = "FAILED"
    DO_NOT_CALL = "DO_NOT_CALL"
    COMPLETED = "COMPLETED"

    @classmethod
    def terminal_values(cls) -> set[str]:
        return {
            cls.QUALIFIED.value,
            cls.TRANSFERRED.value,
            cls.NOT_QUALIFIED.value,
            cls.NOT_INTERESTED.value,
            cls.NO_BUDGET.value,
            cls.WRONG_PERSON.value,
            cls.NO_ANSWER.value,
            cls.BUSY.value,
            cls.VOICEMAIL.value,
            cls.FAILED.value,
            cls.DO_NOT_CALL.value,
            cls.COMPLETED.value,
        }


@dataclass(frozen=True)
class RuleEvaluation:
    field: str
    rule: str
    expected: Any
    actual: Any
    passed: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QualificationResult:
    qualified: bool
    score: int
    passed_rules: List[Dict[str, Any]] = field(default_factory=list)
    failed_rules: List[Dict[str, Any]] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)
    evaluated_rule_count: int = 0
    required_rule_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


QualificationState = Dict[str, Any]
QualificationRules = Dict[str, Any]


def normalize_outcome(value: Any) -> Optional[LeadOutcome]:
    raw = str(value or "").strip().upper()
    if not raw:
        return None
    try:
        return LeadOutcome(raw)
    except ValueError:
        return None
