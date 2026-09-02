"""Provider-neutral tools for campaign knowledge and lead qualification."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

import structlog

from src.knowledge.base import get_knowledge_base_store
from src.qualification.engine import evaluate_qualification
from src.qualification.schemas import LeadOutcome, normalize_outcome
from src.tools.base import Tool, ToolCategory, ToolDefinition, ToolParameter
from src.tools.context import ToolExecutionContext

logger = structlog.get_logger(__name__)


async def _outbound_session(context: ToolExecutionContext):
    session = await context.get_session()
    campaign_id = str(getattr(session, "outbound_campaign_id", "") or "").strip()
    lead_id = str(getattr(session, "outbound_lead_id", "") or "").strip()
    attempt_id = str(getattr(session, "outbound_attempt_id", "") or "").strip() or None
    if not bool(getattr(session, "is_outbound", False)) or not campaign_id or not lead_id:
        raise RuntimeError("This tool is only available during an outbound campaign call")
    return session, campaign_id, lead_id, attempt_id


def _coerce_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    raw = value.strip()
    lowered = raw.casefold()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    if lowered in {"null", "none", "unknown"}:
        return None
    if re.fullmatch(r"[-+]?\d+", raw):
        try:
            return int(raw)
        except ValueError:
            return raw
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)", raw):
        try:
            return float(raw)
        except ValueError:
            return raw
    return raw


def _conversation_summary(session: Any) -> str:
    lines = []
    for item in list(getattr(session, "conversation_history", []) or [])[-8:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "unknown").strip()
        content = str(item.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return " ".join(lines)[:1200]


def _public_lead_context(data: Dict[str, Any]) -> Dict[str, Any]:
    custom = data.get("custom_vars") if isinstance(data.get("custom_vars"), dict) else {}
    return {
        "lead_id": data.get("id"),
        "campaign_id": data.get("campaign_id"),
        "campaign_name": data.get("campaign_name"),
        "name": data.get("name") or custom.get("name"),
        "company": custom.get("company"),
        "role": custom.get("role"),
        "custom_vars": custom,
        "qualification_state": data.get("qualification_state") or {},
        "qualification_result": data.get("qualification_result") or {},
        "last_outcome": data.get("last_outcome"),
        "human_transfer_destination": data.get("human_transfer_destination"),
    }


class SearchKnowledgeBaseTool(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_knowledge_base",
            description=(
                "Search only the current outbound campaign's knowledge base. Use this for "
                "product, pricing, policy, or factual questions instead of guessing."
            ),
            category=ToolCategory.BUSINESS,
            max_execution_time=10,
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="A concise factual search query based on the prospect's question.",
                    required=True,
                )
            ],
        )

    async def execute(self, parameters: Dict[str, Any], context: ToolExecutionContext) -> Dict[str, Any]:
        _, campaign_id, _, _ = await _outbound_session(context)
        query = str(parameters.get("query") or "").strip()
        if not query:
            return {"status": "failed", "message": "A knowledge search query is required"}
        matches = await get_knowledge_base_store().search(campaign_id, query)
        return {
            "status": "success",
            "message": (
                "Use only the returned relevant context to answer. Say you do not know if it is insufficient."
                if matches
                else "No relevant campaign knowledge was found. Do not invent an answer."
            ),
            "matches": matches,
        }


class GetLeadContextTool(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_lead_context",
            description="Get the current outbound lead's known profile and latest qualification state.",
            category=ToolCategory.BUSINESS,
            max_execution_time=5,
        )

    async def execute(self, parameters: Dict[str, Any], context: ToolExecutionContext) -> Dict[str, Any]:
        _, _, lead_id, _ = await _outbound_session(context)
        from src.core.outbound_store import get_outbound_store

        data = await get_outbound_store().get_lead_context(lead_id)
        return {"status": "success", "lead": _public_lead_context(data)}


class UpdateLeadQualificationTool(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="update_lead_qualification",
            description=(
                "Store one qualification fact immediately after the prospect provides it. "
                "Include brief direct evidence; never infer facts the prospect did not provide."
            ),
            category=ToolCategory.BUSINESS,
            max_execution_time=5,
            parameters=[
                ToolParameter(
                    name="field",
                    type="string",
                    description="Snake_case field such as decision_maker, interested, company_size, budget, pain_point, timeline, or current_solution.",
                    required=True,
                ),
                ToolParameter(
                    name="value",
                    type="string",
                    description="The structured scalar value. Use true/false or a plain number where appropriate.",
                    required=True,
                ),
                ToolParameter(
                    name="evidence",
                    type="string",
                    description="Short paraphrase or excerpt supporting this value.",
                    required=True,
                ),
            ],
        )

    async def execute(self, parameters: Dict[str, Any], context: ToolExecutionContext) -> Dict[str, Any]:
        session, _, lead_id, attempt_id = await _outbound_session(context)
        from src.core.outbound_store import get_outbound_store

        updated = await get_outbound_store().update_lead_qualification(
            lead_id,
            field=str(parameters.get("field") or ""),
            value=_coerce_scalar(parameters.get("value")),
            evidence=str(parameters.get("evidence") or ""),
            attempt_id=attempt_id,
        )
        session.outbound_qualification_state = updated["qualification_state"]
        session.outbound_qualification_evidence = updated["qualification_evidence"]
        await context.session_store.upsert_call(session)
        logger.info(
            "Lead qualification field updated",
            call_id=context.call_id,
            lead_id=lead_id,
            field=str(parameters.get("field") or ""),
        )
        return {"status": "success", **updated}


class EvaluateQualificationTool(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="evaluate_qualification",
            description=(
                "Run the campaign's deterministic Python qualification rules against stored lead facts. "
                "This tool, not the AI, makes the final qualification decision."
            ),
            category=ToolCategory.BUSINESS,
            max_execution_time=5,
        )

    async def execute(self, parameters: Dict[str, Any], context: ToolExecutionContext) -> Dict[str, Any]:
        session, _, lead_id, attempt_id = await _outbound_session(context)
        from src.core.outbound_store import get_outbound_store

        store = get_outbound_store()
        data = await store.get_lead_context(lead_id)
        state = data.get("qualification_state") or {}
        rules = data.get("qualification_rules") or {}
        result = evaluate_qualification(state, rules)
        await store.save_qualification_result(lead_id, result, attempt_id=attempt_id)
        outcome = "QUALIFIED" if result["qualified"] else "NOT_QUALIFIED"
        await store.set_lead_outcome(
            lead_id,
            outcome=outcome,
            reason=(
                "All deterministic qualification rules passed"
                if result["qualified"]
                else "Deterministic qualification rules did not pass"
            ),
            attempt_id=attempt_id,
        )
        session.outbound_qualification_state = state
        session.outbound_qualification_result = result
        session.outbound_lead_outcome = outcome
        session.outbound_outcome_reason = (
            "All deterministic qualification rules passed"
            if result["qualified"]
            else "Deterministic qualification rules did not pass"
        )
        custom = data.get("custom_vars") if isinstance(data.get("custom_vars"), dict) else {}
        session.transfer_context = {
            "name": data.get("name") or custom.get("name"),
            "company": custom.get("company"),
            "role": custom.get("role"),
            "pain_point": state.get("pain_point"),
            "budget": state.get("budget"),
            "timeline": state.get("timeline"),
            "qualification_score": result.get("score"),
            "conversation_summary": _conversation_summary(session),
        }
        await context.session_store.upsert_call(session)
        logger.info(
            "Lead qualification evaluated",
            call_id=context.call_id,
            lead_id=lead_id,
            qualified=result["qualified"],
            score=result["score"],
        )
        return {
            "status": "success",
            **result,
            "outcome": outcome,
            "human_transfer_destination": data.get("human_transfer_destination"),
            "instruction": (
                "Ask whether the prospect wants to speak with a specialist; if they agree, use attended_transfer with the configured destination."
                if result["qualified"] and data.get("human_transfer_destination")
                else "Do not transfer unless the deterministic result is qualified and a destination is configured."
            ),
        }


class SetLeadOutcomeTool(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="set_lead_outcome",
            description=(
                "Record a standardized call outcome. QUALIFIED/TRANSFERRED are accepted only after "
                "the deterministic qualification engine has qualified the lead. Use mark_do_not_call for DNC."
            ),
            category=ToolCategory.BUSINESS,
            max_execution_time=5,
            parameters=[
                ToolParameter(
                    name="outcome",
                    type="string",
                    description="Standardized lead outcome.",
                    required=True,
                    enum=[item.value for item in LeadOutcome],
                ),
                ToolParameter(
                    name="reason",
                    type="string",
                    description="Concise factual reason for the outcome.",
                    required=False,
                ),
            ],
        )

    async def execute(self, parameters: Dict[str, Any], context: ToolExecutionContext) -> Dict[str, Any]:
        session, _, lead_id, attempt_id = await _outbound_session(context)
        normalized = normalize_outcome(parameters.get("outcome"))
        if normalized is None:
            return {"status": "failed", "message": "Invalid standardized lead outcome"}
        if normalized is LeadOutcome.DO_NOT_CALL:
            return {
                "status": "failed",
                "message": "Use mark_do_not_call so backend DNC enforcement is applied.",
            }
        if normalized in {LeadOutcome.QUALIFIED, LeadOutcome.TRANSFERRED}:
            result = getattr(session, "outbound_qualification_result", {}) or {}
            if not bool(result.get("qualified", False)):
                return {
                    "status": "failed",
                    "message": "The deterministic qualification engine has not qualified this lead.",
                }
        from src.core.outbound_store import get_outbound_store

        reason = str(parameters.get("reason") or "").strip() or None
        await get_outbound_store().set_lead_outcome(
            lead_id,
            outcome=normalized.value,
            reason=reason,
            attempt_id=attempt_id,
        )
        session.outbound_lead_outcome = normalized.value
        session.outbound_outcome_reason = reason
        await context.session_store.upsert_call(session)
        return {"status": "success", "outcome": normalized.value, "reason": reason}


class ScheduleCallbackTool(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="schedule_callback",
            description="Schedule this lead for a future callback using an ISO 8601 datetime with timezone.",
            category=ToolCategory.BUSINESS,
            max_execution_time=5,
            parameters=[
                ToolParameter(
                    name="datetime",
                    type="string",
                    description="Future ISO 8601 datetime, preferably including an explicit timezone offset.",
                    required=True,
                ),
                ToolParameter(
                    name="reason",
                    type="string",
                    description="Why and when the prospect requested a callback.",
                    required=False,
                ),
            ],
        )

    async def execute(self, parameters: Dict[str, Any], context: ToolExecutionContext) -> Dict[str, Any]:
        session, _, lead_id, attempt_id = await _outbound_session(context)
        from src.core.outbound_store import get_outbound_store

        reason = str(parameters.get("reason") or "").strip() or None
        callback_at = await get_outbound_store().schedule_callback(
            lead_id,
            str(parameters.get("datetime") or ""),
            reason=reason,
            attempt_id=attempt_id,
        )
        session.outbound_lead_outcome = LeadOutcome.CALLBACK.value
        session.outbound_outcome_reason = reason
        session.outbound_callback_at_utc = callback_at
        await context.session_store.upsert_call(session)
        return {"status": "success", "outcome": "CALLBACK", "callback_at_utc": callback_at}


class MarkDoNotCallTool(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="mark_do_not_call",
            description=(
                "Immediately place this lead on the backend-enforced do-not-call list. "
                "Use whenever the prospect asks not to be contacted again."
            ),
            category=ToolCategory.BUSINESS,
            max_execution_time=5,
            parameters=[
                ToolParameter(
                    name="reason",
                    type="string",
                    description="The prospect's do-not-contact request.",
                    required=True,
                )
            ],
        )

    async def execute(self, parameters: Dict[str, Any], context: ToolExecutionContext) -> Dict[str, Any]:
        session, _, lead_id, attempt_id = await _outbound_session(context)
        from src.core.outbound_store import get_outbound_store

        reason = str(parameters.get("reason") or "").strip()
        await get_outbound_store().mark_do_not_call(
            lead_id,
            reason=reason,
            attempt_id=attempt_id,
        )
        session.outbound_lead_outcome = LeadOutcome.DO_NOT_CALL.value
        session.outbound_outcome_reason = reason
        await context.session_store.upsert_call(session)
        logger.info("Lead marked do not call", call_id=context.call_id, lead_id=lead_id)
        return {
            "status": "success",
            "outcome": "DO_NOT_CALL",
            "message": "The lead is now blocked from all future campaign dialing.",
        }
