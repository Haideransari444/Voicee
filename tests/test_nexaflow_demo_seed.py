import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from scripts.seed_nexaflow_demo import (
    AGENT_SLUG,
    AGENT_TOOLS,
    CAMPAIGN_NAME,
    CAMPAIGN_SYSTEM_PROMPT,
    KNOWLEDGE_DOCUMENTS,
    MAYA_SYSTEM_PROMPT,
    QUALIFICATION_RULES,
    TRANSFER_DESTINATION,
    seed_nexaflow_demo,
)
from src.core.agent_store import EngineAgentStore
from src.core.models import CallSession
from src.core.outbound_store import OutboundStore
from src.engine import Engine
from src.knowledge.base import KnowledgeBaseStore
from src.qualification.engine import evaluate_qualification
from src.tools.runtime_config import resolve_agent_tool_config


@pytest.fixture
def demo_paths(tmp_path):
    return tmp_path / "agents.db", tmp_path / "call_history.db"


async def _seed(paths):
    agents_db, call_history_db = paths
    return await seed_nexaflow_demo(
        agents_db_path=str(agents_db),
        call_history_db_path=str(call_history_db),
    )


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_configures_runtime_agent_campaign_and_leads(demo_paths):
    first = await _seed(demo_paths)
    second = await _seed(demo_paths)
    agents_db, call_history_db = demo_paths

    assert first["agent"]["action"] == "created"
    assert first["campaign"]["action"] == "created"
    assert second["agent"]["action"] == "updated"
    assert second["campaign"]["action"] == "updated"
    assert second["lead_count"] == 5
    assert {item["action"] for item in second["knowledge_documents"]} == {"unchanged"}
    assert second["kb_verification"]["query"] == "What is the starting price?"
    assert second["kb_verification"]["expected_fact_found"] is True

    with sqlite3.connect(agents_db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM agents WHERE slug=?", (AGENT_SLUG,)
        ).fetchone()[0] == 1
    with sqlite3.connect(call_history_db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM outbound_campaigns WHERE name=?", (CAMPAIGN_NAME,)
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM knowledge_documents WHERE campaign_id=?",
            (second["campaign"]["id"],),
        ).fetchone()[0] == len(KNOWLEDGE_DOCUMENTS)
        assert conn.execute(
            "SELECT COUNT(*) FROM outbound_leads WHERE campaign_id=?",
            (second["campaign"]["id"],),
        ).fetchone()[0] == 5

    runtime_agent = EngineAgentStore(str(agents_db)).resolve(AGENT_SLUG)
    assert runtime_agent is not None
    assert runtime_agent.provider == "google_live"
    assert runtime_agent.prompt == MAYA_SYSTEM_PROMPT
    assert runtime_agent.voice == "Aoede"
    assert runtime_agent.tools == AGENT_TOOLS
    assert runtime_agent.tool_configs == {
        "transfer": {
            "destination_policy": "selected",
            "destination_keys": [TRANSFER_DESTINATION],
        }
    }

    outbound = OutboundStore(db_path=str(call_history_db))
    campaign = await outbound.get_campaign(second["campaign"]["id"])
    leads = await outbound.list_leads(campaign["id"], page_size=20)
    assert campaign["default_context"] == AGENT_SLUG
    assert campaign["agent_routing_method"] == "ai_agent"
    assert campaign["system_prompt"] == CAMPAIGN_SYSTEM_PROMPT
    assert campaign["qualification_rules"] == QUALIFICATION_RULES
    assert campaign["human_transfer_destination"] == TRANSFER_DESTINATION
    assert all(lead["context_override"] is None for lead in leads["leads"])
    assert all(lead["agent_routing_method"] == "ai_agent" for lead in leads["leads"])

    qualified = evaluate_qualification(
        {
            "company_size": 50,
            "decision_maker": True,
            "interested": True,
            "budget": 1000,
        },
        QUALIFICATION_RULES,
    )
    assert qualified["qualified"] is True
    assert qualified["score"] == 100


@pytest.mark.asyncio
async def test_seeded_campaign_kb_and_live_prompt_context_are_routed_together(demo_paths):
    result = await _seed(demo_paths)
    agents_db, call_history_db = demo_paths
    outbound = OutboundStore(db_path=str(call_history_db))
    knowledge = KnowledgeBaseStore(db_path=str(call_history_db))
    campaign = await outbound.get_campaign(result["campaign"]["id"])
    lead = (await outbound.list_leads(campaign["id"], page_size=20))["leads"][0]
    lead_context = await outbound.get_lead_context(lead["id"])

    matches = await knowledge.search(
        campaign["id"], "Does NexaFlow integrate with Salesforce and what is the starting price?"
    )
    combined = "\n".join(item["content"] for item in matches)
    assert matches
    assert "Salesforce" in combined
    assert "$500" in combined
    assert {item["document_name"] for item in matches} <= set(KNOWLEDGE_DOCUMENTS)

    selector, routing_method = Engine._outbound_agent_selector(campaign, lead)
    assert selector == AGENT_SLUG
    assert routing_method == "ai_agent"
    assert EngineAgentStore(str(agents_db)).resolve(selector).provider == "google_live"

    session = CallSession(call_id="demo-call", caller_channel_id="demo-call")
    session.is_outbound = True
    session.outbound_campaign_id = campaign["id"]
    session.outbound_lead_id = lead["id"]
    session.outbound_campaign_prompt = lead_context["system_prompt"]
    session.outbound_qualification_rules = lead_context["qualification_rules"]
    session.outbound_qualification_state = lead_context["qualification_state"]
    session.outbound_human_transfer_destination = lead_context[
        "human_transfer_destination"
    ]
    merged = Engine._append_outbound_campaign_context_to_prompt(
        object.__new__(Engine), MAYA_SYSTEM_PROMPT, session
    )

    assert MAYA_SYSTEM_PROMPT in merged
    assert CAMPAIGN_SYSTEM_PROMPT in merged
    assert '"company_size": {"gte": 10}' in merged
    assert f"Configured transfer destination key: {TRANSFER_DESTINATION}" in merged
    assert "use search_knowledge_base" in merged
    assert "call evaluate_qualification" in merged


@pytest.mark.asyncio
async def test_seeded_callback_dnc_and_attended_transfer_configuration(demo_paths):
    result = await _seed(demo_paths)
    _, call_history_db = demo_paths
    outbound = OutboundStore(db_path=str(call_history_db))
    leads = (
        await outbound.list_leads(result["campaign"]["id"], page_size=20)
    )["leads"]
    by_scenario = {lead["custom_vars"]["demo_scenario"]: lead for lead in leads}

    callback_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    callback_lead = by_scenario["callback_requested"]
    normalized = await outbound.schedule_callback(
        callback_lead["id"], callback_at, reason="Requested a later conversation"
    )
    callback_context = await outbound.get_lead_context(callback_lead["id"])
    assert normalized == callback_context["callback_at_utc"]
    assert callback_context["last_outcome"] == "CALLBACK"
    leased = await outbound.lease_pending_leads(result["campaign"]["id"], limit=10)
    assert leased
    assert callback_lead["id"] not in {lead["id"] for lead in leased}

    dnc_lead = by_scenario["company_size_below_threshold"]
    await outbound.mark_do_not_call(dnc_lead["id"], reason="Do not contact again")
    dnc_context = await outbound.get_lead_context(dnc_lead["id"])
    assert dnc_context["state"] == "canceled"
    assert dnc_context["last_outcome"] == "DO_NOT_CALL"
    assert dnc_context["do_not_call_at_utc"]

    config_path = Path(__file__).resolve().parents[1] / "config" / "ai-agent.yaml"
    global_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    agent_policy = {
        "transfer": {
            "destination_policy": "selected",
            "destination_keys": [TRANSFER_DESTINATION],
        }
    }
    effective = resolve_agent_tool_config(global_config, agent_policy)
    transfer_destination = effective.config["tools"]["transfer"]["destinations"][
        TRANSFER_DESTINATION
    ]
    assert effective.effective_destination_keys == (TRANSFER_DESTINATION,)
    assert transfer_destination["type"] == "extension"
    assert transfer_destination["attended_allowed"] is True
