# AI SDR extension architecture audit

Audit baseline: AVA `main` at `0bba79ae22794a786a685a8c2048c7bcab3c1627`.

## Existing architecture

AVA is a Python asyncio application centered on `src/engine.py`. Asterisk ARI events
create and tear down `CallSession` instances, provider adapters own realtime audio,
and the provider-neutral tool registry exposes the same business and telephony tools
to Gemini Live and the other supported providers.

The outbound dialer is already a non-blocking control plane:

`outbound_campaigns` -> atomic lead lease -> attempt row -> ARI originate ->
Stasis/AMD/consent -> AI session -> cleanup -> call-history/attempt finalization ->
scheduler capacity is released -> next eligible lead.

The current persistence layer is SQLite, not an ORM or PostgreSQL. Outbound tables
live in the same database as call history (`CALL_HISTORY_DB_PATH`) and use WAL mode,
transactions, and additive startup migrations.

## Reuse unchanged

- `src/ari_client.py`: ARI connection and channel origination primitives.
- `src/providers/google_live.py`: Gemini Live native realtime audio, filtered tool
  declarations, tool execution, and input/output transcription events.
- `src/tools/adapters/google.py`: provider-neutral tool definitions adapted to Gemini.
- `src/tools/telephony/attended_transfer.py`: warm transfer origination and acceptance.
- `src/tools/telephony/unified_transfer.py`: existing blind-transfer implementation.
- `src/tools/telephony/hangup.py`: existing guarded call termination.
- `src/core/session_store.py`: active-call ownership and outbound-capacity accounting.
- `src/core/outbound_schedule.py`: campaign-window normalization.
- `admin_ui/frontend/src/pages/CallSchedulingPage.tsx`: existing campaign, lead,
  attempt, start/stop, import, and concurrency UI foundation.
- `admin_ui/frontend/src/pages/CallHistoryPage.tsx`: existing transcript and tool-event
  inspection foundation.

## Extend existing modules

- `src/core/outbound_store.py`
  - add campaign prompt, qualification rules, and human-transfer destination;
  - add durable lead qualification/outcome/DNC/callback fields;
  - add attempt qualification, outcome reason, transfer, and summary fields;
  - enforce DNC in both leasing and the leased-to-dialing transition;
  - preserve DNC during import/recycle operations.
- `src/core/models.py`: add call-local outbound qualification/outcome state.
- `src/tools/registry.py`: register the AI SDR business tools.
- `src/engine.py`
  - inject the campaign prompt and current qualification context into outbound calls;
  - finalize attempts/leads from the structured outcome chosen during the call;
  - include structured qualification context in attended-transfer briefings;
  - keep automatic progression in the existing scheduler.
- `admin_ui/backend/api/outbound.py`: accept campaign SDR settings and expose knowledge
  document ingestion/list/delete routes.
- `admin_ui/backend/api/tools.py`: reserve the new built-in tool names.
- `admin_ui/frontend/src/pages/CallSchedulingPage.tsx`: expose the new campaign fields
  and show structured lead/attempt results without redesigning the page.

## New modules

- `src/qualification/schemas.py`: typed rule/result structures and supported outcomes.
- `src/qualification/engine.py`: pure deterministic qualification evaluator.
- `src/knowledge/base.py`: chunking, replaceable embedding interface, SQLite document/
  chunk persistence, and bounded similarity search. The first provider is a local
  sparse lexical embedding so the vertical slice adds no model dependency; a
  pgvector-backed implementation can replace it behind the same interface.
- `src/tools/business/outbound_sdr.py`: provider-neutral implementations of
  `search_knowledge_base`, `get_lead_context`, `update_lead_qualification`,
  `evaluate_qualification`, `set_lead_outcome`, `schedule_callback`, and
  `mark_do_not_call`. Existing attended-transfer and hangup tools remain canonical.
- focused unit tests for rule evaluation, knowledge retrieval, tool persistence, and
  DNC leasing/redial enforcement.

## Missing features found during audit

- No campaign-scoped knowledge documents or retrieval tool.
- No structured qualification state or deterministic campaign rules.
- Existing outbound outcomes are transport-oriented (`answered_human`, `error`, etc.)
  rather than sales/disposition-oriented.
- No backend-enforced DNC flag.
- No scheduled-callback eligibility field.
- Existing call history stores the complete conversation and tool audit trail, but
  outbound attempt rows do not yet hold qualification/transfer metadata.
- The attended-transfer briefing summarizes recent transcript only; it does not yet
  consume qualification state.

## Database migration requirements

AVA has no Alembic migration framework. The compatible pattern is to update table
creation SQL and add idempotent column/table checks in `OutboundStore._ensure_schema_sync`.
The vertical slice therefore uses additive nullable/defaulted SQLite changes only:

- campaign: `system_prompt`, `qualification_rules_json`, `human_transfer_destination`;
- lead: `qualification_state_json`, `qualification_result_json`, `outcome_reason`,
  `qualification_score`, `callback_at_utc`, `do_not_call_at_utc`, `do_not_call_reason`;
- attempt: `qualification_state_json`, `qualification_result_json`, `outcome_reason`,
  `summary`, `transfer_attempted`, `transfer_successful`;
- new `knowledge_documents` and `knowledge_chunks` tables and indexes.

Existing rows remain valid through defaults. PostgreSQL/pgvector is intentionally not
introduced into AVA's SQLite runtime in this first slice; the retrieval interface keeps
that storage migration isolated from telephony and qualification logic.

## Implementation order

1. Add and unit-test the pure qualification schemas/engine.
2. Extend the outbound schema and enforce DNC/callback eligibility transactionally.
3. Add campaign knowledge persistence, chunking, retrieval abstraction, and API.
4. Add provider-neutral AI SDR tools and register them for Gemini Live.
5. Hydrate call-local campaign state and persist the selected structured outcome during
   the existing cleanup/finalization flow.
6. Feed qualification context to the existing attended-transfer briefing path.
7. Extend the existing Admin UI with the minimum campaign/lead/attempt fields.
8. Run focused tests, the outbound regression suite, and syntax/type/build checks that
   are available in the workspace.
