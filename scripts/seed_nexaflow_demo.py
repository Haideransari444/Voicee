#!/usr/bin/env python3
"""Idempotently seed the persistent NexaFlow/Maya SDR demo configuration."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADMIN_BACKEND = PROJECT_ROOT / "admin_ui" / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(ADMIN_BACKEND) not in sys.path:
    sys.path.insert(0, str(ADMIN_BACKEND))

from agents_store import AgentsStore  # noqa: E402
from src.core.agent_store import EngineAgentStore  # noqa: E402
from src.core.outbound_store import OutboundStore  # noqa: E402
from src.knowledge.base import KnowledgeBaseStore  # noqa: E402


AGENT_SLUG = "nexaflow-sdr"
CAMPAIGN_NAME = "NexaFlow SDR Demo"
TRANSFER_DESTINATION = "sales_agent"
AGENT_TOOLS = [
    "search_knowledge_base",
    "update_lead_qualification",
    "evaluate_qualification",
    "set_lead_outcome",
    "schedule_callback",
    "mark_do_not_call",
    "attended_transfer",
]
QUALIFICATION_RULES = {
    "required": {
        "decision_maker": True,
        "interested": True,
    },
    "numeric": {
        "company_size": {"gte": 10},
        "budget": {"gte": 500},
    },
}

MAYA_SYSTEM_PROMPT = """You are Maya, an AI Sales Development Representative for NexaFlow.

You are speaking with potential business customers by phone.

Your objective is to understand their current customer-support situation, determine whether NexaFlow may be relevant, answer factual questions using the campaign knowledge base, collect qualification information naturally, and transfer qualified prospects to a human representative.

Speak natural professional English.

Keep responses concise, normally one or two sentences.

Ask one main question at a time.

Do not sound like a questionnaire.

If the prospect asks a question, answer it before returning to qualification.

Never fabricate pricing, integrations, product capabilities, policies, results, discounts, or implementation details.

If asked whether you are human, clearly state that you are an AI assistant representing NexaFlow.

OPENING

Introduce yourself briefly and explain that NexaFlow helps businesses automate repetitive customer-support conversations while allowing human staff to handle more complex cases.

Then naturally ask how the prospect currently handles customer support.

QUALIFICATION

Naturally determine:

- company_size
- decision_maker
- interested
- budget

Also collect when useful:

- pain_point
- current_solution
- notes

Whenever reliable information becomes available, immediately call update_lead_qualification.

Do not wait until the end of the conversation.

Never invent numeric values.

Only mark interested=true when the prospect demonstrates genuine interest in learning more, seeing a demo, discussing pricing, implementation, or continuing the conversation.

Do not mark interest simply because the person remains on the phone.

Only mark decision_maker=true when the prospect clearly indicates that they make or meaningfully influence the purchasing decision.

KNOWLEDGE BASE

Use search_knowledge_base for factual questions about:

- pricing
- features
- integrations
- implementation
- onboarding
- capabilities
- FAQs
- factual objections

If the knowledge base does not contain the answer, say you do not want to provide inaccurate information and offer to have a human representative clarify it.

QUALIFICATION DECISION

Do not personally decide whether a prospect is qualified.

When sufficient information has been collected, call evaluate_qualification.

If qualified, briefly acknowledge that the prospect appears to be a relevant fit and initiate the configured attended transfer.

If not qualified, remain polite and conclude naturally.

CALLBACK

If the prospect wants to speak later, use schedule_callback.

Confirm timing if necessary.

DO NOT CALL

If the prospect says not to contact them again, immediately call mark_do_not_call and stop selling.

OBJECTIONS

Handle objections naturally and without pressure.

Use the knowledge base for factual objections.

Never manipulate the prospect into changing answers merely to satisfy qualification criteria.

END OF CALL

Ensure relevant qualification fields and call outcome are persisted before ending when possible."""

CAMPAIGN_SYSTEM_PROMPT = """This is the NexaFlow SDR Demo campaign.

Use the NexaFlow campaign knowledge base as the only source for product, pricing, integration, implementation, onboarding, capability, FAQ, and objection facts. Store reliable prospect facts as they are learned and use the backend qualification evaluator as the sole source of the qualification decision.

When evaluate_qualification returns qualified=true, ask the prospect for permission to connect them to a human NexaFlow representative. If they agree, call attended_transfer with destination sales_agent. If they request another time, schedule a callback. If they request no further contact, mark the lead do-not-call immediately and stop selling."""

KNOWLEDGE_DOCUMENTS = {
    "overview.txt": """NexaFlow is a fictional B2B AI customer-support platform.

It helps businesses automate repetitive customer-support conversations while allowing human representatives to handle complex or escalated cases.

NexaFlow is intended to complement support teams rather than completely replace human staff.""",
    "pricing.txt": """NexaFlow plans start at $500 per month.

Final pricing depends on business requirements and scale.

Enterprise plans may include onboarding and additional analytics capabilities.

No discounts or custom enterprise prices should be claimed unless explicitly provided by a human representative.""",
    "features.txt": """NexaFlow provides:

- AI-powered customer-support conversations
- automation of repetitive support questions
- escalation to human representatives
- customer-support analytics
- support workflow assistance
- Salesforce integration""",
    "integrations.txt": """NexaFlow supports Salesforce integration in this demo.

No other integration should be claimed unless it exists in the campaign knowledge base.""",
    "faq.txt": """What is NexaFlow?
NexaFlow is a fictional B2B AI customer-support platform that automates repetitive support conversations and helps human teams focus on complex cases.

Does NexaFlow replace human support staff?
No. NexaFlow is intended to complement support teams rather than completely replace human staff.

What is the starting price?
NexaFlow plans start at $500 per month. Final pricing depends on business requirements and scale.

Does NexaFlow integrate with Salesforce?
Yes. NexaFlow supports Salesforce integration in this demo.

Are enterprise plans available?
Yes. Enterprise plans may include onboarding and additional analytics capabilities. Exact terms must be confirmed by a NexaFlow representative.

Can I speak with a human representative?
Yes. A qualified and consenting prospect can be connected to a human representative, or a callback can be arranged.

How long does implementation take?
The exact implementation timeline depends on customer requirements and must be confirmed by a NexaFlow representative.""",
    "objections.txt": """Too expensive
NexaFlow plans start at $500 per month, while final pricing depends on business requirements and scale. Do not promise a discount or an unlisted price.

Already using another platform
NexaFlow may be evaluated alongside an existing support platform. Ask about the current workflow and gaps without claiming an integration other than Salesforce.

Don't need AI
NexaFlow is designed for businesses that want to automate repetitive support conversations. It may not be relevant when repetitive support work is not a meaningful problem.

Concern about replacing staff
NexaFlow is intended to complement support teams and allow human representatives to focus on complex or escalated cases, not completely replace staff.

Need to discuss internally
Respect the internal review process. Offer factual information, a conversation with a human representative, or a callback when appropriate.

Busy now
Do not continue the pitch. Ask for a suitable callback time and use the callback tool after the timing is confirmed.

Callback request
Confirm the requested date, time, and timezone when necessary, then schedule the callback. Do not treat a callback request as qualification by itself.""",
}

DEMO_LEADS = [
    {
        "name": "Jordan Blake",
        "phone_number": "+12025550101",
        "custom_vars": {
            "company": "HarborPeak Retail",
            "demo_scenario": "likely_qualified",
            "company_size": 50,
            "decision_maker": True,
            "interested": True,
            "budget": 1000,
        },
    },
    {
        "name": "Casey Morgan",
        "phone_number": "+12025550102",
        "custom_vars": {
            "company": "Maple Street Studio",
            "demo_scenario": "company_size_below_threshold",
            "company_size": 6,
            "decision_maker": True,
            "interested": True,
            "budget": 700,
        },
    },
    {
        "name": "Riley Chen",
        "phone_number": "+12025550103",
        "custom_vars": {
            "company": "Cedarline Services",
            "demo_scenario": "budget_below_threshold",
            "company_size": 35,
            "decision_maker": True,
            "interested": True,
            "budget": 300,
        },
    },
    {
        "name": "Avery Stone",
        "phone_number": "+12025550104",
        "custom_vars": {
            "company": "BlueVale Logistics",
            "demo_scenario": "not_decision_maker",
            "company_size": 80,
            "decision_maker": False,
            "interested": True,
            "budget": 1500,
        },
    },
    {
        "name": "Taylor Reed",
        "phone_number": "+12025550105",
        "custom_vars": {
            "company": "Northstar Workshop",
            "demo_scenario": "callback_requested",
            "callback_requested": True,
        },
    },
]


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _seed_agent(agents_db_path: str, transfer_destination: str) -> dict[str, Any]:
    payload = {
        "display_name": "Maya",
        "provider": "google_live",
        "prompt": MAYA_SYSTEM_PROMPT,
        "extension": None,
        "role_label": "AI Sales Development Representative",
        "voice": "Aoede",
        "greeting": (
            "Hello, this is Maya, an AI sales development representative for NexaFlow. "
            "NexaFlow helps businesses automate repetitive support conversations while "
            "their teams handle complex cases. How do you currently handle customer support?"
        ),
        "tools_json": _json(AGENT_TOOLS),
        "tool_configs_json": _json(
            {
                "transfer": {
                    "destination_policy": "selected",
                    "destination_keys": [transfer_destination],
                }
            }
        ),
        "audio_profile": None,
        "extra_json": None,
        "is_operator_managed": 1,
        "source_file": None,
        "notes": "Idempotently managed by scripts/seed_nexaflow_demo.py",
    }
    with AgentsStore(agents_db_path) as store:
        existing = store.get_by_slug(AGENT_SLUG)
        if existing:
            agent = store.update(AGENT_SLUG, is_active=1, **payload)
            action = "updated"
        else:
            agent = store.create(slug=AGENT_SLUG, **payload)
            action = "created"
    return {"action": action, "record": agent}


async def _seed_campaign(
    outbound: OutboundStore,
    transfer_destination: str,
) -> tuple[str, dict[str, Any]]:
    matches = [
        campaign
        for campaign in await outbound.list_campaigns(include_archived=True)
        if str(campaign.get("name") or "").strip() == CAMPAIGN_NAME
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"multiple campaigns named {CAMPAIGN_NAME!r} already exist; resolve duplicates before seeding"
        )
    payload = {
        "name": CAMPAIGN_NAME,
        "timezone": "UTC",
        "daily_window_start_local": "00:00",
        "daily_window_end_local": "23:59",
        "max_concurrent": 1,
        "min_interval_seconds_between_calls": 5,
        "default_context": AGENT_SLUG,
        "agent_routing_method": "ai_agent",
        "voicemail_drop_enabled": False,
        "consent_enabled": False,
        "amd_options": {},
        "system_prompt": CAMPAIGN_SYSTEM_PROMPT,
        "qualification_rules": QUALIFICATION_RULES,
        "human_transfer_destination": transfer_destination,
    }
    if matches:
        campaign = await outbound.update_campaign(matches[0]["id"], payload)
        return "updated", campaign
    campaign = await outbound.create_campaign(payload)
    return "created", campaign


async def _seed_knowledge(
    knowledge: KnowledgeBaseStore,
    campaign_id: str,
) -> list[dict[str, Any]]:
    existing = await knowledge.list_documents(campaign_id)
    results: list[dict[str, Any]] = []
    for name, content in KNOWLEDGE_DOCUMENTS.items():
        digest = hashlib.sha256(content.strip().encode("utf-8")).hexdigest()
        named = [row for row in existing if row.get("name") == name]
        exact = next((row for row in named if row.get("content_sha256") == digest), None)
        if exact:
            results.append({"name": name, "action": "unchanged", "id": exact["id"]})
            continue
        for row in named:
            await knowledge.delete_document(campaign_id, row["id"])
        document = await knowledge.add_document(
            campaign_id,
            name=name,
            content=content,
            content_type="text/plain",
        )
        results.append(
            {
                "name": name,
                "action": "updated" if named else "created",
                "id": document["id"],
            }
        )
    return results


async def _seed_leads(outbound: OutboundStore, campaign_id: str) -> dict[str, Any]:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=["name", "phone_number", "timezone", "custom_vars"],
        lineterminator="\n",
    )
    writer.writeheader()
    for lead in DEMO_LEADS:
        writer.writerow(
            {
                "name": lead["name"],
                "phone_number": lead["phone_number"],
                "timezone": "UTC",
                "custom_vars": _json(lead["custom_vars"]),
            }
        )
    return await outbound.import_leads_csv(
        campaign_id,
        output.getvalue().encode("utf-8"),
        skip_existing=False,
        known_agents=[AGENT_SLUG],
    )


async def seed_nexaflow_demo(
    *,
    agents_db_path: str,
    call_history_db_path: str,
    transfer_destination: str = TRANSFER_DESTINATION,
) -> dict[str, Any]:
    agent_result = _seed_agent(agents_db_path, transfer_destination)
    outbound = OutboundStore(db_path=call_history_db_path)
    knowledge = KnowledgeBaseStore(db_path=call_history_db_path)
    campaign_action, campaign = await _seed_campaign(outbound, transfer_destination)
    documents = await _seed_knowledge(knowledge, campaign["id"])
    lead_import = await _seed_leads(outbound, campaign["id"])

    resolved_agent = EngineAgentStore(agents_db_path).resolve(AGENT_SLUG)
    leads = await outbound.list_leads(campaign["id"], page_size=200)
    kb_query = "What is the starting price?"
    search_results = await knowledge.search(campaign["id"], kb_query)
    if resolved_agent is None:
        raise RuntimeError("seeded Agent cannot be resolved by the runtime Agent store")
    if resolved_agent.provider != "google_live":
        raise RuntimeError("seeded Agent did not resolve to google_live")
    if set(resolved_agent.tools or []) != set(AGENT_TOOLS):
        raise RuntimeError("seeded Agent tool allowlist does not match the NexaFlow tool set")
    if not search_results:
        raise RuntimeError("seeded NexaFlow campaign knowledge is not retrievable")
    if not any("$500 per month" in str(item.get("content") or "") for item in search_results):
        raise RuntimeError("seeded NexaFlow KB did not return the expected $500 starting-price fact")

    return {
        "agents_db": agents_db_path,
        "call_history_db": call_history_db_path,
        "agent": {
            "action": agent_result["action"],
            "slug": AGENT_SLUG,
            "provider": resolved_agent.provider,
            "tools": list(resolved_agent.tools or []),
        },
        "campaign": {
            "action": campaign_action,
            "id": campaign["id"],
            "name": campaign["name"],
            "default_context": campaign["default_context"],
            "agent_routing_method": campaign["agent_routing_method"],
            "human_transfer_destination": campaign["human_transfer_destination"],
            "qualification_rules": campaign["qualification_rules"],
        },
        "knowledge_documents": documents,
        "lead_import": lead_import,
        "lead_count": leads["total"],
        "kb_verification": {
            "query": kb_query,
            "match_count": len(search_results),
            "expected_fact_found": any(
                "$500 per month" in str(item.get("content") or "")
                for item in search_results
            ),
            "documents": sorted(
                {str(item.get("document_name") or "") for item in search_results}
            ),
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Idempotently seed the persistent NexaFlow/Maya SDR demo"
    )
    parser.add_argument(
        "--agents-db",
        default=os.getenv("AGENTS_DB_PATH", "/app/data/operator/agents.db"),
        help="Agent runtime SQLite path (default: AGENTS_DB_PATH or /app/data/operator/agents.db)",
    )
    parser.add_argument(
        "--call-history-db",
        default=os.getenv("CALL_HISTORY_DB_PATH", "/app/data/call_history.db"),
        help="Outbound/KB runtime SQLite path (default: CALL_HISTORY_DB_PATH or /app/data/call_history.db)",
    )
    parser.add_argument(
        "--transfer-destination",
        default=TRANSFER_DESTINATION,
        help="Existing attended-transfer destination key (default: sales_agent)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = asyncio.run(
        seed_nexaflow_demo(
            agents_db_path=str(Path(args.agents_db)),
            call_history_db_path=str(Path(args.call_history_db)),
            transfer_destination=str(args.transfer_destination).strip(),
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
