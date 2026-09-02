"""Run a real Gemini Live non-PSTN SDR verification.

The provider, tool adapter, campaign store, qualification engine, and call
history are AVA's existing implementations. Only ``transfer_to_human`` is a
test-only in-memory tool; it applies the same qualification gate and records a
simulated transfer without an ARI/SIP/Asterisk client.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "gemini-2.5-flash-native-audio-latest"


def _load_dotenv() -> None:
    for path in (REPO_ROOT / ".env", REPO_ROOT / ".env.local"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            name, value = raw.split("=", 1)
            name = name.strip()
            value = value.strip().strip("'\"")
            if name and value and name not in os.environ:
                os.environ[name] = value


class TransferToHumanSimulationTool:
    """Gemini-only developer tool; it never touches telephony."""

    @property
    def definition(self):
        from src.tools.base import ToolCategory, ToolDefinition, ToolParameter

        return ToolDefinition(
            name="transfer_to_human",
            description="Transfer a qualified prospect to a human specialist (simulated in this test).",
            category=ToolCategory.BUSINESS,
            parameters=[ToolParameter(name="reason", type="string", description="Reason for transfer")],
        )

    async def execute(self, parameters: dict[str, Any], context: Any) -> dict[str, Any]:
        session = await context.get_session()
        session.transfer_attempted = True
        if not bool((getattr(session, "outbound_qualification_result", {}) or {}).get("qualified")):
            return {"status": "failed", "message": "Qualification gate blocked transfer"}
        from src.core.outbound_store import get_outbound_store

        reason = str(parameters.get("reason") or "Gemini Live qualified lead; transfer simulated.")
        await get_outbound_store().set_lead_outcome(
            session.outbound_lead_id,
            outcome="TRANSFERRED",
            reason=reason,
            attempt_id=session.outbound_attempt_id,
        )
        session.outbound_lead_outcome = "TRANSFERRED"
        session.outbound_outcome_reason = reason
        session.transfer_successful = True
        await context.session_store.upsert_call(session)
        return {"status": "success", "simulated": True, "message": "No SIP/Asterisk call was made."}


async def run_real_gemini_test(db_path: str, *, api_key: str) -> dict[str, Any]:
    test_started = time.perf_counter()
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    os.environ["CALL_HISTORY_ENABLED"] = "true"
    os.environ["CALL_HISTORY_DB_PATH"] = db_path

    from src.config import GoogleProviderConfig
    from src.core.call_history import CallHistoryStore, CallRecord
    from src.core.outbound_store import get_outbound_store
    from src.knowledge.base import get_knowledge_base_store
    from src.providers.google_live import GoogleLiveProvider
    from src.tools.business.outbound_sdr import (
        EvaluateQualificationTool,
        GetLeadContextTool,
        MarkDoNotCallTool,
        ScheduleCallbackTool,
        SearchKnowledgeBaseTool,
        SetLeadOutcomeTool,
        UpdateLeadQualificationTool,
    )
    from src.tools.context import ToolExecutionContext
    from src.tools.registry import tool_registry
    from mock_sdr_conversation import MockCallSession, MockSessionStore

    store = get_outbound_store()
    knowledge = get_knowledge_base_store()
    campaign = await store.create_campaign({
        "name": f"Gemini Live SDR {uuid.uuid4().hex[:8]}",
        "timezone": "UTC",
        "system_prompt": "Use the SDR tools to collect facts and run deterministic qualification.",
        "human_transfer_destination": "gemini-live-test://human-specialist",
        "qualification_rules": {"required": {"decision_maker": True, "interested": True}, "numeric": {"company_size": {"gte": 10}, "budget": {"gte": 500}}},
    })
    campaign_id = campaign["id"]
    seeded_document = await knowledge.add_document(
        campaign_id,
        name="pricing.txt",
        content=(
            "The AI support platform starts at $500 per month and integrates with Salesforce. "
            "Enterprise plans include onboarding and analytics."
        ),
    )
    imported = await store.import_leads_csv(campaign_id, b"name,phone_number\nGemini Test Lead,+15550000001\n")
    if imported.get("accepted") != 1:
        raise RuntimeError(f"lead import failed: {imported}")
    lead = (await store.list_leads(campaign_id))["leads"][0]
    if not await store.lease_pending_leads(campaign_id, limit=1) or not await store.mark_lead_dialing(lead["id"]):
        raise RuntimeError("lead could not enter outbound dialing flow")
    attempt_id = await store.create_attempt(campaign_id, lead["id"], context="gemini_live_non_pstn", provider="gemini_live")

    session = MockCallSession(f"gemini-live-{uuid.uuid4()}", campaign_id, lead["id"], attempt_id)
    session.tool_calls = []
    session_store = MockSessionStore()
    await session_store.upsert_call(session)
    context = ToolExecutionContext(call_id=session.call_id, session_store=session_store, config={})

    # Register only the existing SDR tools plus the in-memory simulation tool.
    for tool_class in (SearchKnowledgeBaseTool, GetLeadContextTool, UpdateLeadQualificationTool, EvaluateQualificationTool, SetLeadOutcomeTool, MarkDoNotCallTool, ScheduleCallbackTool, TransferToHumanSimulationTool):
        if not tool_registry.has(tool_class().definition.name):
            tool_registry.register(tool_class)
    allowed_tools = [
        "search_knowledge_base", "get_lead_context", "update_lead_qualification",
        "evaluate_qualification", "set_lead_outcome", "mark_do_not_call",
        "schedule_callback", "transfer_to_human",
    ]

    # Verify the campaign-scoped KB before opening Gemini. This catches a
    # misconfigured DB path (or an unseeded campaign) independently of model
    # tool selection.
    kb_result = await SearchKnowledgeBaseTool().execute(
        {"query": "AI support platform pricing Salesforce"}, context
    )
    kb_matches = kb_result.get("matches") if isinstance(kb_result, dict) else None
    if not isinstance(kb_matches, list) or not kb_matches:
        raise RuntimeError(f"seeded campaign knowledge was not retrievable: {kb_result}")

    events: list[dict[str, Any]] = []
    first_response_monotonic: float | None = None

    async def on_event(event: dict[str, Any]) -> None:
        nonlocal first_response_monotonic
        event_type = event.get("type")
        event_time = time.perf_counter()
        if first_response_monotonic is None and event_type in {"AgentAudio", "AgentAudioDone"}:
            first_response_monotonic = event_time
        events.append({"type": event_type, "text": event.get("text"), "ts_monotonic": event_time})

    config = GoogleProviderConfig(
        api_key=api_key,
        llm_model=DEFAULT_MODEL,
        instructions=(
            "Use the provided SDR tools in this mandatory order: first call "
            "search_knowledge_base with the query 'AI support platform pricing Salesforce', "
            "then update_lead_qualification for every fact, then call evaluate_qualification. "
            "After evaluate_qualification returns qualified=true, you MUST immediately call "
            "transfer_to_human with a concise reason; do not end the session before that call. "
            "Facts: company_size=50, decision_maker=true, interested=true, budget=1000. "
            "Transfer is simulated in this developer test and never uses SIP/Asterisk."
        ),
        # Native-audio Live models require AUDIO-only responses. Text is
        # captured through the enabled outputAudioTranscription stream.
        response_modalities="audio",
        enable_input_transcription=True,
        enable_output_transcription=True,
    )
    provider = GoogleLiveProvider(config=config, on_event=on_event)
    provider._session_store = session_store
    provider._ari_client = None
    provider._full_config = {}
    provider._caller_channel_id = None
    provider._context_name = "gemini_live_non_pstn"
    session_started = time.perf_counter()
    connection_latency_ms: float | None = None
    first_response_reference: float | None = None
    api_errors: list[str] = []
    connected = False
    try:
        await provider.start_session(session.call_id, context={"tools": allowed_tools, "voice": "Aoede"})
        connected = True
        connection_latency_ms = round((time.perf_counter() - session_started) * 1000, 2)
        session.conversation_history.append({"role": "user", "content": "Company size is 50; I am the decision maker; we are interested; our budget is 1000."})
        await session_store.upsert_call(session)
        first_response_reference = time.perf_counter()
        await provider.send_audio(b"\x00" * 640, sample_rate=16000, encoding="linear16")
        await provider._send_message({"clientContent": {"turns": [{"role": "user", "parts": [{"text": "Company size is 50; I am the decision maker; we are interested; our budget is 1000. Follow the mandatory SDR tool order, and after evaluate_qualification returns qualified=true, immediately call transfer_to_human."}]}], "turnComplete": True}})
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            current = await session_store.get_by_call_id(session.call_id)
            if current and current.transfer_successful:
                session = current
                break
            await asyncio.sleep(0.25)

        # If Gemini completed qualification but did not select the final tool,
        # send one explicit continuation turn. The transfer tool itself remains
        # the same in-memory simulation above; no telephony path is reachable.
        current = await session_store.get_by_call_id(session.call_id)
        if not (current and current.transfer_successful) and current and (current.outbound_qualification_result or {}).get("qualified"):
            await provider._send_message({"clientContent": {"turns": [{"role": "user", "parts": [{"text": "The qualification result is qualified=true. You must now call transfer_to_human; transfer is simulated and must not use SIP/Asterisk."}]}], "turnComplete": True}})
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                current = await session_store.get_by_call_id(session.call_id)
                if current and current.transfer_successful:
                    session = current
                    break
                await asyncio.sleep(0.25)
    except Exception as exc:
        api_errors.append(str(exc))
    finally:
        try:
            await provider.stop_session()
        except Exception as exc:
            api_errors.append(f"stop_session: {exc}")

    session_finished = time.perf_counter()
    session = await session_store.get_by_call_id(session.call_id) or session
    now = datetime.now(timezone.utc)
    call_record = CallRecord(
        call_id=session.call_id,
        caller_number=lead["phone_number"],
        caller_name=lead["name"],
        called_number="gemini-live-non-pstn",
        start_time=now - timedelta(seconds=max(0, int(time.perf_counter() - session_started))),
        end_time=now,
        provider_name="gemini_live",
        context_name="gemini_live_non_pstn",
        conversation_history=session.conversation_history,
        outcome="transferred" if session.transfer_successful else "error",
    )
    history_store = CallHistoryStore(db_path=db_path)
    persisted_history = await history_store.save(call_record)
    await store.finish_attempt(
        attempt_id,
        outcome=session.outbound_lead_outcome or "FAILED",
        context="gemini_live_non_pstn",
        provider="gemini_live",
        call_history_call_id=call_record.id,
        qualification_state=session.outbound_qualification_state,
        qualification_result=session.outbound_qualification_result,
        outcome_reason=session.outbound_outcome_reason,
        summary=" ".join(item.get("content", "") for item in session.conversation_history)[-2000:],
        transfer_attempted=session.transfer_attempted,
        transfer_successful=session.transfer_successful,
        error_message="; ".join(api_errors) if api_errors else None,
    )
    await store.set_lead_state(lead["id"], state="completed" if session.transfer_successful else "failed", last_outcome=session.outbound_lead_outcome or "FAILED")
    persisted_lead = await store.get_lead_context(lead["id"])
    persisted_call = await history_store.get_by_call_id(session.call_id)
    return {
        "connection_status": "connected" if connected else "failed",
        "tool_calls": session.tool_calls,
        "events": events[-20:],
        "connection_latency_ms": connection_latency_ms,
        "first_response_latency_ms": (
            round((first_response_monotonic - first_response_reference) * 1000, 2)
            if first_response_monotonic is not None and first_response_reference is not None
            else None
        ),
        "tool_call_latency_ms": round(
            sum(float(item.get("duration_ms") or 0.0) for item in (session.tool_calls or [])), 2
        ),
        "tool_call_count": len(session.tool_calls or []),
        "session_duration_ms": round((session_finished - session_started) * 1000, 2),
        "total_test_duration_ms": round((time.perf_counter() - test_started) * 1000, 2),
        "knowledge_base": {
            "seeded_document": seeded_document.get("name"),
            "verification_matches": [
                {
                    "document_name": item.get("document_name"),
                    "content": item.get("content"),
                    "score": item.get("score"),
                }
                for item in kb_matches
            ],
        },
        "api_errors": api_errors,
        "final_qualification": persisted_lead.get("qualification_result") or {},
        "transfer_simulated": bool(session.transfer_successful),
        "transfer_attempted": bool(session.transfer_attempted),
        "transfer_successful": bool(session.transfer_successful),
        "persisted_transcript_turns": len(persisted_call.conversation_history) if persisted_call else 0,
        "persisted_history": bool(persisted_history),
        "pstn_call_made": False,
        "sip_or_asterisk_used": False,
        "db_path": db_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the real Gemini Live non-PSTN SDR test")
    parser.add_argument("--db", default=str(REPO_ROOT / "data" / "gemini_live_real_test.db"))
    parser.add_argument("--api-key", default=None, help="Optional one-run key; prefer GOOGLE_API_KEY or .env")
    args = parser.parse_args()
    _load_dotenv()
    api_key = (args.api_key or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        print(json.dumps({"connection_status": "not_run", "api_errors": ["GOOGLE_API_KEY not found in .env or environment"]}, indent=2))
        raise SystemExit(2)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    try:
        result = asyncio.run(run_real_gemini_test(args.db, api_key=api_key))
    except Exception as exc:
        print(json.dumps({"connection_status": "failed", "api_errors": [str(exc)], "pstn_call_made": False, "sip_or_asterisk_used": False}, indent=2))
        raise SystemExit(1)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    if result.get("final_qualification", {}).get("qualified") is not True or result.get("transfer_simulated") is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
