import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from src.core.outbound_store import OutboundStore


async def _campaign_and_lead(store: OutboundStore):
    campaign = await store.create_campaign(
        {
            "name": "SDR test",
            "timezone": "UTC",
            "qualification_rules": {"required": {"interested": True}},
        }
    )
    imported = await store.import_leads_csv(
        campaign["id"],
        b"name,phone_number\nTest Lead,+15551234567\n",
    )
    assert imported["accepted"] == 1
    leads = await store.list_leads(campaign["id"])
    return campaign, leads["leads"][0]


@pytest.mark.asyncio
async def test_do_not_call_lead_is_never_leased_or_recycled(tmp_path):
    store = OutboundStore(db_path=str(tmp_path / "calls.db"))
    campaign, lead = await _campaign_and_lead(store)

    await store.mark_do_not_call(lead["id"], reason="Do not contact me")

    assert await store.lease_pending_leads(campaign["id"], limit=1) == []
    assert await store.recycle_lead(lead["id"], mode="redial") is False
    context = await store.get_lead_context(lead["id"])
    assert context["last_outcome"] == "DO_NOT_CALL"
    assert context["do_not_call_at_utc"]


@pytest.mark.asyncio
async def test_dnc_race_blocks_leased_to_dialing_transition(tmp_path):
    store = OutboundStore(db_path=str(tmp_path / "calls.db"))
    campaign, lead = await _campaign_and_lead(store)
    leased = await store.lease_pending_leads(campaign["id"], limit=1)
    assert leased[0]["id"] == lead["id"]

    await store.mark_do_not_call(lead["id"], reason="Stop calling")

    assert await store.mark_lead_dialing(lead["id"]) is False


@pytest.mark.asyncio
async def test_qualification_state_and_result_are_persisted_on_lead_and_attempt(tmp_path):
    store = OutboundStore(db_path=str(tmp_path / "calls.db"))
    campaign, lead = await _campaign_and_lead(store)
    leased = await store.lease_pending_leads(campaign["id"], limit=1)
    assert leased
    attempt_id = await store.create_attempt(campaign["id"], lead["id"])

    updated = await store.update_lead_qualification(
        lead["id"],
        field="interested",
        value=True,
        evidence="Prospect asked for next steps",
        attempt_id=attempt_id,
    )
    await store.save_qualification_result(
        lead["id"],
        {"qualified": True, "score": 100},
        attempt_id=attempt_id,
    )

    assert updated["qualification_state"] == {"interested": True}
    context = await store.get_lead_context(lead["id"])
    assert context["qualification_state"] == {"interested": True}
    assert context["qualification_result"]["qualified"] is True
    assert context["qualification_score"] == 100


@pytest.mark.asyncio
async def test_callback_window_blocks_until_due_then_allows_leasing(tmp_path):
    db_path = tmp_path / "calls.db"
    store = OutboundStore(db_path=str(db_path))
    campaign, lead = await _campaign_and_lead(store)
    callback_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    await store.schedule_callback(lead["id"], callback_at, reason="Prospect requested tomorrow")
    assert await store.lease_pending_leads(campaign["id"], limit=1) == []

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE outbound_leads SET callback_at_utc=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), lead["id"]),
        )
        conn.commit()

    leased = await store.lease_pending_leads(campaign["id"], limit=1)
    assert leased and leased[0]["id"] == lead["id"]
