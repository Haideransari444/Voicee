"""Run one provider-free outbound SDR conversation through the real business tools.

The mock deliberately never creates an ARI/SIP client. It exercises the same
campaign store, knowledge search, qualification tools, outcome persistence, and
call-history persistence used by a real outbound call, then simulates the final
transfer gate locally.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class MockSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}

    async def get_by_call_id(self, call_id: str) -> Any:
        return self._sessions.get(call_id)

    async def upsert_call(self, session: Any) -> None:
        self._sessions[session.call_id] = session


class MockCallSession:
    def __init__(self, call_id: str, campaign_id: str, lead_id: str, attempt_id: str) -> None:
        self.call_id = call_id
        self.is_outbound = True
        self.outbound_campaign_id = campaign_id
        self.outbound_lead_id = lead_id
        self.outbound_attempt_id = attempt_id
        self.outbound_qualification_state: dict[str, Any] = {}
        self.outbound_qualification_evidence: dict[str, Any] = {}
        self.outbound_qualification_result: dict[str, Any] = {}
        self.outbound_lead_outcome: str | None = None
        self.outbound_outcome_reason: str | None = None
        self.outbound_callback_at_utc: str | None = None
        self.transfer_context: dict[str, Any] = {}
        self.transfer_attempted = False
        self.transfer_successful = False
        self.conversation_history: list[dict[str, str]] = []


async def run_mock(
    db_path: str,
    *,
    transport: str = "mock",
) -> dict[str, Any]:
    # Set these before importing modules that construct the process-wide stores.
    os.environ["CALL_HISTORY_ENABLED"] = "true"
    os.environ["CALL_HISTORY_DB_PATH"] = db_path

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from src.core.call_history import CallHistoryStore, CallRecord
    from src.core.outbound_store import get_outbound_store
    from src.knowledge.base import get_knowledge_base_store
    from src.tools.business.outbound_sdr import (
        EvaluateQualificationTool,
        GetLeadContextTool,
        SearchKnowledgeBaseTool,
        SetLeadOutcomeTool,
        UpdateLeadQualificationTool,
    )
    from src.tools.context import ToolExecutionContext

    store = get_outbound_store()
    knowledge = get_knowledge_base_store()
    campaign = await store.create_campaign(
        {
            "name": f"Mock SDR Demo {uuid.uuid4().hex[:8]}",
            "timezone": "UTC",
            "system_prompt": "Qualify the prospect using the deterministic campaign rules.",
            "human_transfer_destination": "mock://human-specialist",
            "qualification_rules": {
                "required": {"decision_maker": True, "interested": True},
                "numeric": {"company_size": {"gte": 10}, "budget": {"gte": 500}},
            },
        }
    )
    campaign_id = campaign["id"]
    await knowledge.add_document(
        campaign_id,
        name="pricing.txt",
        content="The AI support platform starts at $500 per month and integrates with Salesforce.",
    )

    imported = await store.import_leads_csv(
        campaign_id,
        b"name,phone_number,company,role\nMock Test Lead,+15550000000,Example Co,VP Operations\n",
    )
    if imported.get("accepted") != 1:
        raise RuntimeError(f"demo lead import failed: {imported}")
    leads = (await store.list_leads(campaign_id))["leads"]
    lead = leads[0]
    lead_id = lead["id"]

    leased = await store.lease_pending_leads(campaign_id, limit=1)
    if not leased or not await store.mark_lead_dialing(lead_id):
        raise RuntimeError("demo lead could not enter outbound dialing flow")
    provider_name = "gemini_live" if transport == "gemini_live_non_pstn" else "mock"
    context_name = "gemini_live_non_pstn" if transport == "gemini_live_non_pstn" else "mock_sdr"
    attempt_id = await store.create_attempt(campaign_id, lead_id, context=context_name, provider=provider_name)

    call_id = f"mock-{uuid.uuid4()}"
    session = MockCallSession(call_id, campaign_id, lead_id, attempt_id)
    session_store = MockSessionStore()
    await session_store.upsert_call(session)
    context = ToolExecutionContext(call_id=call_id, session_store=session_store, config={})
    tool_trace = [
        "search_knowledge_base",
        "update_lead_qualification",
        "evaluate_qualification",
        "set_lead_outcome",
        "mark_do_not_call",
        "schedule_callback",
        "transfer_to_human",
    ]
    audio_frames = 0

    def add_turn(role: str, content: str) -> None:
        session.conversation_history.append({"role": role, "content": content})

    add_turn("assistant", "Hello, I am calling to learn whether our AI support platform may help your team.")
    add_turn("user", "We have 50 employees, I make the decision, we are interested, and our budget is 1000.")

    if transport == "gemini_live_non_pstn":
        # Developer-only Gemini Live protocol simulation: two PCM16 frames are
        # accepted as the audio turn, while the accompanying transcript is fed
        # through the same tool router used by the real provider adapter.
        audio_frames = 2
    kb_result = await SearchKnowledgeBaseTool().execute({"query": "pricing and Salesforce integration"}, context)
    for field, value, evidence in (
        ("company_size", 50, "Prospect said the company has 50 employees."),
        ("decision_maker", True, "Prospect said they make the decision."),
        ("interested", True, "Prospect explicitly said they are interested."),
        ("budget", 1000, "Prospect stated a budget of 1000."),
    ):
        result = await UpdateLeadQualificationTool().execute(
            {"field": field, "value": value, "evidence": evidence}, context
        )
        if result.get("status") != "success":
            raise RuntimeError(f"qualification update failed for {field}: {result}")

    lead_context = await GetLeadContextTool().execute({}, context)
    evaluation = await EvaluateQualificationTool().execute({}, context)
    if evaluation.get("qualified") is not True:
        raise RuntimeError(f"demo lead did not qualify: {evaluation}")

    # This is the same qualification gate used before a real attended_transfer,
    # but it intentionally does not call any telephony or ARI code.
    async def transfer_to_human() -> dict[str, Any]:
        session.transfer_attempted = True
        if not bool(session.outbound_qualification_result.get("qualified")):
            return {"status": "failed", "message": "Qualification gate blocked transfer"}
        result = await SetLeadOutcomeTool().execute(
            {"outcome": "TRANSFERRED", "reason": "Qualified demo lead; transfer simulated."},
            context,
        )
        if result.get("status") == "success":
            session.transfer_successful = True
            return {"status": "success", "simulated": True, "destination": "mock://human-specialist"}
        return result

    transfer_result = await transfer_to_human()
    transfer_simulated = bool(transfer_result.get("simulated"))
    if transfer_simulated:
        transfer_message = "Simulated transfer completed (no SIP/Asterisk call made)."
    else:
        transfer_message = "Transfer was not attempted because deterministic qualification failed."
    await session_store.upsert_call(session)

    add_turn("assistant", "Thanks. You meet the campaign criteria; I will connect you with a specialist.")
    add_turn("system", transfer_message)
    now = datetime.now(timezone.utc)
    call_record = CallRecord(
        call_id=call_id,
        caller_number=lead["phone_number"],
        caller_name=lead["name"],
        called_number="mock://campaign",
        start_time=now - timedelta(seconds=8),
        end_time=now,
        duration_seconds=8,
        provider_name=provider_name,
        context_name=context_name,
        conversation_history=session.conversation_history,
        outcome="transferred" if transfer_simulated else "completed",
        transfer_destination=campaign.get("human_transfer_destination"),
    )
    history_store = CallHistoryStore(db_path=db_path)
    if not await history_store.save(call_record):
        raise RuntimeError("mock call history was not persisted")

    await store.finish_attempt(
        attempt_id,
        outcome=session.outbound_lead_outcome or "COMPLETED",
        context=context_name,
        provider=provider_name,
        call_history_call_id=call_record.id,
        qualification_state=session.outbound_qualification_state,
        qualification_result=session.outbound_qualification_result,
        outcome_reason=session.outbound_outcome_reason,
        summary=" ".join(item["content"] for item in session.conversation_history),
        transfer_attempted=session.transfer_attempted,
        transfer_successful=session.transfer_successful,
    )
    await store.set_lead_state(lead_id, state="completed", last_outcome=session.outbound_lead_outcome)

    persisted = await store.get_lead_context(lead_id)
    attempts = await store.list_attempts(campaign_id=campaign_id)
    persisted_attempt = next(
        (item for item in attempts.get("attempts", []) if item.get("id") == attempt_id),
        None,
    )
    persisted_call = await history_store.get_by_call_id(call_id)
    return {
        "transport": transport,
        "provider": provider_name,
        "campaign_id": campaign_id,
        "lead_id": lead_id,
        "attempt_id": attempt_id,
        "knowledge_matches": len(kb_result.get("matches", [])),
        "tool_trace": tool_trace,
        "audio_frames": audio_frames,
        "qualification": evaluation,
        "transfer_simulated": transfer_simulated,
        "transfer_attempted": session.transfer_attempted,
        "transfer_successful": session.transfer_successful,
        "transcript_turns": len(session.conversation_history),
        "persisted_lead": {
            "qualification_state": persisted.get("qualification_state"),
            "qualification_result": persisted.get("qualification_result"),
            "outcome": persisted.get("last_outcome"),
            "outcome_reason": persisted.get("outcome_reason"),
        },
        "persisted_attempt": persisted_attempt,
        "persisted_transcript_turns": len(persisted_call.conversation_history) if persisted_call else 0,
        "call_history_id": call_record.id,
        "db_path": db_path,
        "lead_context_loaded": lead_context.get("status") == "success",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the provider-free AVA mock SDR demo")
    parser.add_argument(
        "--db",
        default=str(Path(__file__).resolve().parents[1] / "data" / "mock_sdr_demo.db"),
        help="SQLite path for the isolated demo data (default: data/mock_sdr_demo.db)",
    )
    args = parser.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(run_mock(args.db))
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    print("\nDemo expectation: qualified=true, transfer_simulated=true")


if __name__ == "__main__":
    main()
