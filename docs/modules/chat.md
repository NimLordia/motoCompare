# Module: chat

## Responsibility

The assistant feature — one menu item among the platform's features, not its core. A FastAPI streaming endpoint, the LangGraph tool-calling agent, its toolbox, and assembly of structured answer blocks. It consumes catalog, profile, and research exactly like the web UI does, just through a conversational surface.

## Public interface

`POST /api/chat/messages` — request: `ChatMessageIn` (`message`, optional `conversation_id`; when omitted the server generates one and returns it in `done`). Response: SSE stream (`text/event-stream`) with events:

- `status` — short progress line derived from each tool call ("Looking up \"r7\"…", "Researching top speed…"); data: `{content}`
- `text` — assistant prose tokens; data: `{content}`
- `block` — typed structured payload; `type` ∈ `comparison_table | spec_card | insight_card | research_pending | disambiguation`
- `done` — data: `{conversation_id}` (always the last event on success)
- `error` — data: `{detail}` (terminal; also emitted when the agent exceeds its step budget)

Answers 503 when no chat model is configured (no Gemini API key) — the rest of the API keeps working.

Block payload shapes are shared contracts in `app/chat/schemas.py` (indexed in SHARED.md) — the frontend renders them 1:1, reusing the same components as the catalog pages. They embed the catalog payloads (`Fact`, `ComparisonMatrix`, `VariantOut`, `InsightOut`, `BikeCandidate`) unchanged.

## Agent toolbox

Built per request (`build_toolbox`), closing over the request's DB session, the user id, and the profile's unit system — so unit conversion is decided once, before the agent runs.

| Tool | Backs onto | Purpose |
|---|---|---|
| `resolve_bike` | catalog | free text → bike variant candidates; auto-picks a clear winner (≥ 0.15 confidence gap), otherwise emits a `disambiguation` block |
| `get_specs` | catalog | facts with provenance, converted to the user's units; emits `spec_card`; lists missing keys so the agent researches them |
| `compare_bikes` | catalog | aligned comparison matrix; emits `comparison_table`; calls out per-bike gaps |
| `get_insights` | catalog | source-linked community/tester experience per topic; emits `insight_card` |
| `get_user_profile` | profile | units, market, current bike, riding style, priorities |
| `trigger_research` | research | request missing specs or insights; honors the hybrid inline/background contract (`wait_for_research` with the `MOTO_RESEARCH_INLINE_BUDGET_SECONDS` budget); on success returns the fresh facts with a `spec_card`/`insight_card`, on timeout emits `research_pending`, memoized failures are reported with their reason |

Expected service errors (unknown bike/key/topic, too few bikes to compare) become tool content the LLM can react to; unexpected exceptions fail the stream with an `error` event.

## Hard rules

1. **Numbers only via tools.** The agent must never state a quantitative spec from model memory. Missing fact → `trigger_research`.
2. **Subjective topics are grounded.** Heat, comfort, maintenance, electronics, real-world behavior → `get_insights` first; missing topic → `trigger_research`. Only after research fails may the agent fall back to general knowledge, explicitly labeled as ungrounded.
3. **Disagreements are surfaced.** When official and measured values differ, present both with their tiers ("claimed 73.4 hp, dyno-tested 68 hp") — never silently pick one.
4. Every fact shown carries its source tier; the structured blocks include it.
5. "Compare with my bike" resolves the user's current bike from the profile — never asks the user to re-state it.

Rules 1–2 and 5 are enforced by the system prompt plus the tool design (tools list what's missing and what to do about it); 3–4 ride on catalog payloads that always carry every tier.

## Agent architecture

Hand-rolled two-node LangGraph (`agent` ⇄ `tools`, see DECISIONS 2026-07-22): the LLM node streams prose tokens (`text` events); its tool calls become `status` events; tools return `(content_for_llm, blocks)` via LangChain's `content_and_artifact` format, and the artifacts stream out as `block` events. The tools node executes calls **sequentially** because the toolbox shares one SQLAlchemy session. A recursion limit (25 super-steps) converts runaway tool loops into an `error` event.

Conversation history lives in an in-memory LangGraph checkpointer keyed by `conversation_id` — process-lifetime only, reset when the model is reconfigured (see DECISIONS 2026-07-22). The system prompt is versioned in code (`app/chat/prompts.py`, `SYSTEM_PROMPT_VERSION`), injected per LLM call and never stored in history.

## Boundaries

- Does NOT write to the catalog and contains NO research logic — it only calls tools.
- Does NOT convert units (catalog does, driven by the profile, wired in at toolbox build time).

## Open TODOs

- History is unbounded per conversation; add trimming/summarization if long conversations become a real use case.
- Durable conversations (DB-backed checkpointer) if chat history must survive restarts.

## Code map

`backend/app/chat/` — `schemas.py` (request + block contracts), `prompts.py` (versioned system prompt), `tools.py` (toolbox factory, status lines), `agent.py` (LangGraph loop), `service.py` (model configuration, SSE event stream), `router.py` (REST at `/api/chat`). The model is built in `app/main.py` (`_build_chat_model`, None without a key) and configured in the lifespan. Tests in `backend/tests/test_chat_*.py`; `FakeChatModel`/`scripted_chat` live in `tests/conftest.py`.

## Status

Implemented (v1): streaming endpoint, six-tool grounded agent on `gemini-3.6-flash` (`MOTO_CHAT_MODEL`), structured blocks, hybrid inline/background research, per-conversation memory, 30 tests (220 total). Verified live against the Gemini API (tool loop, blocks, dual official/tested presentation).
