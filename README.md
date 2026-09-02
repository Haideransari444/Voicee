<div align="center">

<img src="admin_ui/frontend/public/callflow-logo.png" alt="CallFlow" width="280" />

# CallFlow

### AI outbound calling, lead qualification, and human handoff

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=111827)](https://react.dev/)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Asterisk](https://img.shields.io/badge/Asterisk-18%2B-F0B323?logo=asterisk&logoColor=111827)](https://www.asterisk.org/)
[![License](https://img.shields.io/badge/license-MIT-22C55E)](LICENSE)

</div>
CallFlow connects Asterisk telephony to realtime AI agents and gives sales and
operations teams one place to configure campaigns, qualify leads, review
conversations, and follow up. This repository contains the AI engine, Admin API,
CallFlow web application, configuration, test suites, and Docker deployment
files.

> **Status:** CallFlow is an active engineering project. Test provider and
> transfer changes with an internal endpoint or non-PSTN mode before dialing
> real contacts.

## Product demo

<div align="center">

[▶ Watch the CallFlow product demo on Vimeo](https://vimeo.com/1223456212)

See the complete product walkthrough, including campaign setup, live calling,
qualification, and operational reporting.

</div>

---

## Contents

- [What CallFlow does](#what-callflow-does)
- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Quick start with Docker](#quick-start-with-docker)
- [Admin UI and local frontend development](#admin-ui-and-local-frontend-development)
- [Authentication and secrets](#authentication-and-secrets)
- [Agents, campaigns, and routing](#agents-campaigns-and-routing)
- [Outbound SDR workflow](#outbound-sdr-workflow)
- [NexaFlow demo setup](#nexaflow-demo-setup)
- [Providers and Google Live](#providers-and-google-live)
- [Asterisk integration](#asterisk-integration)
- [Knowledge base and retrieval](#knowledge-base-and-retrieval)
- [Call history and observability](#call-history-and-observability)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Security checklist](#security-checklist)
- [Development and contributing](#development-and-contributing)
- [License](#license)

---

## What CallFlow does

A typical outbound conversation follows this path:

~~~text
Campaign
  -> Lead and consent/DNC checks
  -> Asterisk outbound dial and AMD
  -> AI Agent selected by campaign context
  -> Realtime provider (for example Google Live)
  -> Campaign prompt + campaign knowledge retrieval
  -> Structured SDR tools update lead state
  -> Deterministic qualification evaluation
  -> Attended transfer, callback, DNC, or final outcome
  -> Persisted transcript, call history, and reporting data
~~~

| Area | Capability |
| --- | --- |
| Voice | Realtime providers, streaming audio, interruption handling, AudioSocket and other supported transports |
| Campaigns | Scheduled outbound campaigns, lead import, calling windows, concurrency, retries, and attempt history |
| SDR | Company size, decision-maker, interest, budget, qualification score, and reason fields |
| Knowledge | Campaign-isolated documents, chunking, indexing, and relevance-ranked retrieval |
| Compliance | Do-not-call suppression, callback scheduling, consent gates, and fail-closed routing |
| Handoff | Blind and attended transfer workflows with destination validation and cleanup |
| Operations | Dashboard, campaigns, leads, callbacks, knowledge base, call history, transcripts, and analytics |
| Developer tools | Provider health, configuration validation, logs, metrics, dialplan generation, and demo scripts |

---

## Architecture

Telephony ownership stays in Asterisk while call orchestration stays in the AI
engine. The Admin API reads and writes the same persistent operational data used
by the engine.

~~~mermaid
flowchart LR
    PBX[Asterisk / FreePBX\nPJSIP, ARI, Stasis] -->|ARI + media| ENGINE[ai_engine\nCall orchestration]
    ENGINE -->|Realtime API| PROVIDER[AI provider\nGoogle Live, OpenAI, Deepgram, etc.]
    ENGINE -->|Optional WebSocket| LOCAL[local_ai_server\nlocal STT/LLM/TTS]
    ENGINE --> DATA[(SQLite runtime data)]
    UI[CallFlow Admin UI\nReact + Vite] --> API[Admin API\nFastAPI]
    API --> DATA
    API -->|health / reload| ENGINE
~~~

### Runtime services

| Service | Default port | Responsibility |
| --- | ---: | --- |
| ai_engine | 15000 health/metrics | ARI connection, call state, media transport, provider sessions, tools, persistence |
| admin_ui | 3003 | FastAPI Admin API and built CallFlow frontend |
| local_ai_server | 8765 WebSocket | Optional local STT, LLM, and TTS models |
| Asterisk ARI | 8088 | PBX control plane; your installation may use another port |

The default Compose file uses host networking for low-latency access to
Asterisk. Review the Compose overlays before using bridge or GPU deployments.

---

## Repository layout

~~~text
admin_ui/
  backend/                 FastAPI Admin API, auth, configuration, and tests
  frontend/                CallFlow React/Vite application
config/
  ai-agent.yaml            Tracked provider, tool, and transport baseline
data/
  call_history.db          Calls, attempts, campaigns, leads, and KB at runtime
  operator/agents.db       Operator-managed Agent definitions
scripts/
  seed_nexaflow_demo.py    Idempotent campaign, Agent, KB, and lead seed
  mock_sdr_conversation.py Provider-free SDR verification
  gemini_live_sdr_test.py  Real Gemini Live non-PSTN verification
src/
  engine.py                ARI/Stasis lifecycle and provider orchestration
  providers/               Realtime and pipeline provider adapters
  knowledge/               Campaign-scoped KB store and retrieval
  qualification/           Deterministic qualification engine and schemas
  tools/                   Business, compliance, and telephony tools
tests/                     Focused and integration-oriented backend tests
docker-compose*.yml        Runtime, host, local-core, and GPU variants
Dockerfile                  AI engine image definition
admin_ui/Dockerfile         Admin API + frontend production image
~~~

---

## Requirements

### Runtime

- Linux, WSL2, or a Linux VM for the Docker/telephony runtime
- Docker Engine and Docker Compose v2
- Asterisk 18 or newer with ARI enabled
- An outbound-capable PJSIP/SIP trunk for real calls
- Python 3.11 or newer for local scripts and tests
- Node.js 20 or newer for frontend development

### Provider requirements

At least one configured provider is required for AI calls. Google Live uses
GOOGLE_API_KEY; other providers use their corresponding environment key or
operator credential configuration. Never place real credentials in YAML, source
code, tests, screenshots, or commits.

---

## Quick start with Docker

### 1. Clone and enter the repository

~~~bash
git clone https://github.com/Haideransari444/Voicee.git
cd Voicee
~~~

### 2. Run preflight

~~~bash
sudo ./preflight.sh --apply-fixes
~~~

Preflight creates .env from .env.example, generates a JWT secret when needed,
checks host paths, and aligns permissions for shared runtime data.

### 3. Configure environment secrets

Edit .env locally. At minimum, configure Asterisk ARI and the provider:

~~~dotenv
ASTERISK_HOST=127.0.0.1
ASTERISK_ARI_PORT=8088
ASTERISK_ARI_USERNAME=asterisk
ASTERISK_ARI_PASSWORD=replace-me
GOOGLE_API_KEY=replace-me
~~~

.env is ignored by Git. Keep a secure backup outside the repository.

### 4. Start the services

~~~bash
docker compose -p asterisk-ai-voice-agent up -d --build ai_engine admin_ui
~~~

The optional local model service is not required for Google Live:

~~~bash
docker compose -p asterisk-ai-voice-agent up -d local_ai_server
~~~

### 5. Verify health and open the UI

~~~bash
curl http://127.0.0.1:15000/health
docker compose -p asterisk-ai-voice-agent ps
docker compose -p asterisk-ai-voice-agent logs --tail=100 ai_engine admin_ui
~~~

Open http://localhost:3003. For remote hosts, put the UI behind a firewall,
VPN, or reverse proxy; do not expose the Docker socket or Admin API directly to
the public internet.

---

## Admin UI and local frontend development

The production admin_ui container serves the built React application and API on
port 3003. For frontend work, run Vite locally:

~~~bash
cd admin_ui/frontend
npm ci
npm run dev -- --host 127.0.0.1
~~~

Vite serves http://localhost:5173. API clients use relative paths such as
/api/calls and /api/outbound/campaigns; the development proxy forwards them to
http://127.0.0.1:3003. This keeps login, campaigns, leads, transcripts, and
analytics connected to Docker runtime data instead of a second local backend
database.

~~~bash
npm run lint
npm test -- --run
npm run build
npm run preview
~~~

If the dashboard is empty, verify that admin_ui is running on 3003, the Vite
proxy in admin_ui/frontend/vite.config.ts points to that port, data has been
seeded, and the browser has been hard-refreshed.

---

## Authentication and secrets

The Admin API uses JWT authentication. The initial password is generated by the
Admin UI runtime and must be changed after first login. Retrieve a first-start
value from logs when needed:

~~~bash
docker compose -p asterisk-ai-voice-agent logs admin_ui | grep -i password
~~~

Change it through the UI. Do not reset or edit config/users.json while the
service is running unless you understand password-hash and permission effects.

Important files:

- .env — ignored environment secrets and deployment values
- .env.example — safe variable template; no real credentials
- config/users.json — runtime authentication data; keep private and backed up
- secrets/ — provider credential files when file-based auth is required

---

## Agents, campaigns, and routing

CallFlow separates the reusable AI Agent persona from campaign business context:

1. An **Agent** defines provider, voice, system instructions, and effective tool
   allowlist. Agents are stored in data/operator/agents.db.
2. A **Campaign** defines audience, schedule, campaign prompt, qualification
   rules, transfer destination, and campaign-scoped KB.
3. A lead may provide an explicit Agent override. Without one, it inherits the
   campaign default_context dynamically.
4. The outbound engine resolves campaign and Agent before starting a provider
   session. Missing or ambiguous routing fails closed.

For inbound calls, the dialplan can select an Agent with AI_AGENT:

~~~asterisk
[from-ai-agent]
exten => s,1,NoOp(CallFlow AI Agent)
 same => n,Set(AI_AGENT=nexaflow-sdr)
 same => n,Stasis(asterisk-ai-voice-agent)
 same => n,Hangup()
~~~

Generate a current snippet with:

~~~bash
agent dialplan --agent nexaflow-sdr
~~~

For outbound calls, campaign default_context is the fallback for leads without an
override. The Agent supplies persona/provider; the campaign supplies business
context and qualification rules.

---

## Outbound SDR workflow

### Persisted lead state

Leads retain phone/name/company variables, attempt metadata, qualification fields
and result, outcome and reason, callback time, DNC time, transfer attempted and
successful flags, linked call-history ID, and summary.

### SDR tools

| Tool | Purpose |
| --- | --- |
| search_knowledge_base | Retrieve factual, campaign-scoped product information |
| update_lead_qualification | Record structured facts from conversation |
| evaluate_qualification | Run deterministic campaign rules; no model judgment |
| set_lead_outcome | Persist disposition and reason |
| schedule_callback | Store requested follow-up time and timezone |
| mark_do_not_call | Suppress future outbound attempts |
| attended_transfer | Ring a human destination and bridge after acceptance |

Example rules:

~~~json
{
  "required": {"decision_maker": true, "interested": true},
  "numeric": {
    "company_size": {"min": 10},
    "budget": {"min": 500}
  }
}
~~~

Qualification is persisted independently from the transcript, making the result
auditable and repeatable. Before dialing, the scheduler checks campaign status,
calling window, retry policy, consent, and DNC suppression. During a call, a DNC
request is persisted immediately and the agent must stop selling. A callback
request is stored with its time and does not imply qualification.

### Attended transfer

The transfer workflow validates the destination, rings the human endpoint, and
preserves the original caller until the handoff is accepted. The NexaFlow demo
uses screening_mode: direct: once the human answers, the existing finalize bridge
path connects the caller without Local AI Server TTS or a DTMF prompt.

---

## NexaFlow demo setup

The repository includes an idempotent fictional campaign for demonstrations and
regression checks. It creates or updates:

- Agent **Maya**, slug nexaflow-sdr, provider google_live
- campaign **NexaFlow SDR Demo**
- campaign-scoped product, pricing, FAQ, integration, and objection content
- rules: decision-maker, interested, company size ≥ 10, budget ≥ 500
- five fictional demo leads
- attended-transfer metadata using sales_agent

### Seed inside Docker (recommended)

~~~bash
docker compose -p asterisk-ai-voice-agent exec ai_engine \
  python /app/scripts/seed_nexaflow_demo.py
~~~

Run it twice to verify idempotency. The second run reuses or updates the same
records instead of creating duplicates.

### Seed a local checkout explicitly

~~~bash
python scripts/seed_nexaflow_demo.py \
  --agents-db data/operator/agents.db \
  --call-history-db data/call_history.db
~~~

The seed verifies KB retrieval for “What is the starting price?” and expects the
fact that NexaFlow plans start at $500 per month.

### Demo verification scripts

Provider-free SDR verification (no SIP/Asterisk or external API):

~~~bash
python scripts/mock_sdr_conversation.py --db data/mock_sdr_demo.db
~~~

Real Gemini Live non-PSTN verification (requires GOOGLE_API_KEY):

~~~bash
python scripts/gemini_live_sdr_test.py \
  --db data/gemini_live_existing_provider_test.db
~~~

The Gemini test uses the same SDR tools, simulates human transfer, and persists
transcript, qualification, outcome, and transfer state in the supplied SQLite
database.

---

## Providers and Google Live

Provider and transport behavior is configured in config/ai-agent.yaml, with
operator overrides kept in the local configuration layer. Depending on
credentials, CallFlow supports Google Live, OpenAI Realtime, Deepgram Voice
Agent, ElevenLabs Agent, xAI Grok, and local or hybrid pipelines.

### Google Live checklist

1. Set GOOGLE_API_KEY in .env, or configure supported Vertex AI credentials.
2. Ensure the Agent resolves to google_live.
3. Use a supported Live model and voice.
4. Keep input and output transcription enabled for transcript persistence.
5. Native-audio Live models use an audio response modality and obtain text from
   output audio transcription.

The provider session receives the resolved Agent prompt, campaign prompt,
campaign ID, campaign KB scope, qualification rules, and effective tool list.

---

## Asterisk integration

### ARI and Stasis

Asterisk must expose ARI and allow the configured user to control channels,
bridges, playback, and applications. The engine connects using .env values and
enters the configured Stasis application.

### Media transports

CallFlow supports the transport profiles implemented by the engine, including
AudioSocket. Audio profiles define encoding and sample rate; keep the Asterisk
endpoint, provider contract, and Agent profile aligned. Do not hardcode PCM16 or
a sample rate in a dialplan override.

### Outbound routing

Outbound campaigns use the configured dial context, extension identity, prefix,
AMD hop, and per-attempt variables. The engine performs AMD and lead-context
checks before starting the provider. Human answers, voicemail, busy, DNC,
callbacks, and failed attempts are recorded as distinct outcomes.

---

## Knowledge base and retrieval

The existing KB is campaign-scoped. Documents are normalized, hashed, chunked,
and indexed in the call-history SQLite database. A document is not visible to
another campaign unless explicitly added there.

The Admin UI supports adding factual text, uploading text/Markdown, optional PDF
extraction when pypdf is installed, listing document size and chunk count, and
deleting campaign documents. search_knowledge_base always receives the active
campaign scope; agents should answer only from retrieved facts or say that the KB
does not contain an answer.

---

## Call history and observability

The Admin UI exposes persisted calls, transcripts, summaries, outcomes, tool
events, recordings when available, qualification state, transfer state, DNC, and
callbacks.

| Resource | API path |
| --- | --- |
| Provider health | GET /api/providers/health |
| Calls | GET /api/calls |
| Call stats | GET /api/calls/stats |
| Call detail | GET /api/calls/{id} |
| Transcript | GET /api/calls/{id}/transcript |
| Agents | GET /api/agents |
| Campaigns | GET /api/outbound/campaigns |
| Campaign stats | GET /api/outbound/campaigns/{id}/stats |
| Campaign leads | GET /api/outbound/campaigns/{id}/leads |
| Campaign KB | GET /api/outbound/campaigns/{id}/knowledge |
| Attempts | GET /api/outbound/campaigns/{id}/attempts |

The AI engine exposes health and Prometheus-compatible metrics on port 15000
when enabled:

~~~bash
docker compose -p asterisk-ai-voice-agent logs -f ai_engine
docker compose -p asterisk-ai-voice-agent logs -f admin_ui
~~~

---

## Testing

### Backend

~~~bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pytest -q
~~~

Focused SDR and telephony checks:

~~~bash
python -m pytest -q \
  tests/test_nexaflow_demo_seed.py \
  tests/test_qualification_engine.py \
  tests/test_campaign_knowledge_base.py \
  tests/test_outbound_sdr_store.py \
  tests/test_attended_transfer_tool.py \
  tests/test_attended_transfer_streaming.py \
  tests/test_audiosocket_startup_priming.py
~~~

Compile and secret checks:

~~~bash
python -m compileall -q src admin_ui/backend scripts
python scripts/check_no_committed_secrets.py
git diff --check
~~~

### Frontend

~~~bash
cd admin_ui/frontend
npm ci
npm run lint
npm test -- --run
npm run build
~~~

Use isolated temporary SQLite databases for tests. Never point a destructive
test at live Docker data.

---

## Troubleshooting

### localhost:3003 refuses the connection

~~~bash
docker compose -p asterisk-ai-voice-agent ps admin_ui
docker compose -p asterisk-ai-voice-agent logs --tail=100 admin_ui
~~~

On WSL, confirm Docker Desktop or the Linux Docker daemon is running and that
the port is forwarded to Windows.

### Vite opens but the dashboard is empty

The Windows frontend must use relative /api requests and proxy to the real Admin
API on 127.0.0.1:3003. Do not point normal development at a second Uvicorn
process on port 8000. Confirm seed data exists and hard-refresh.

### Login fails

Use the Admin UI account stored by the runtime. Retrieve a first-start password
from admin_ui logs, then change it through the UI. Verify that .env,
config/users.json, and mounted data paths were not replaced during sync.

### AI provider is not ready

Check provider health and the environment variable name. For Google Live:

~~~bash
docker compose -p asterisk-ai-voice-agent exec ai_engine sh -lc \
  'test -n "$GOOGLE_API_KEY" && echo configured || echo missing'
~~~

Never print the key itself.

### Campaign calls use the wrong Agent

Check campaign default_context, lead-level override, and the Agent slug in
data/operator/agents.db. A blank lead override should remain NULL so it inherits
campaign routing dynamically. Re-run the idempotent seed if needed.

### AudioSocket closes during startup

Inspect engine and Asterisk logs together. The call-scoped startup priming path
keeps the leg alive while the provider starts and uses the negotiated profile.
Rebuild ai_engine after source changes; do not add a global infinite keepalive.

### Attended transfer aborts before bridging

The NexaFlow demo uses direct screening and does not require Local AI Server TTS.
Verify tools.attended_transfer.enabled, screening_mode: direct, and that
sales_agent resolves to the intended PJSIP endpoint.

### Docker status reports “system cannot find the file specified”

The Admin UI Docker page needs access to the Docker socket and a matching
DOCKER_GID. This is separate from AI call execution; verify socket mounting,
permissions, and the selected Compose project.

---

## Security checklist

- Keep .env, API keys, SIP credentials, JWT secrets, and config/users.json out of Git.
- Restrict Admin UI port 3003 with a firewall, VPN, or reverse proxy.
- Use HTTPS/WSS and certificate verification for remote ARI deployments.
- Never expose the Docker socket to untrusted users or networks.
- Apply privacy and retention policies to recordings and transcripts.
- Configure DNC and consent before dialing real contacts.
- Test provider and transfer changes with an internal endpoint first.
- Redact phone numbers, credentials, and provider payloads from issue reports.
- Back up SQLite databases before migrations or bulk campaign operations.

See SECURITY.md for deployment guidance.

---

## Development and contributing

The codebase keeps clear boundaries:

- provider adapters own provider protocols and media contracts;
- src/engine.py owns call lifecycle and ARI state;
- src/tools/ owns business and telephony actions;
- src/knowledge/ owns campaign KB storage and retrieval;
- src/qualification/ owns deterministic rule evaluation;
- admin_ui/backend/ exposes authenticated operational APIs;
- admin_ui/frontend/ consumes APIs and does not fabricate operational records.

When changing call behavior, trace setup, success, timeout, retry, hangup,
restart recovery, and cleanup. Preserve fail-closed DNC, callback, consent,
transfer, and ownership checks. Add a focused test with every lifecycle change.

Before opening a pull request:

~~~bash
git diff --check
python scripts/check_no_committed_secrets.py
python -m pytest -q
cd admin_ui/frontend && npm run lint && npm test -- --run && npm run build
~~~

Keep commits focused, avoid unrelated telephony refactors, and include the exact
runtime or test command used to verify a change.

---

## License

CallFlow is released under the MIT License (see LICENSE).

<div align="center">

Built for teams that want every outbound conversation to be measurable,
compliant, and useful.

</div>
