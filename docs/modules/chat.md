# Module: chat

## Responsibility

The assistant feature — one menu item among the platform's features, not its core. A FastAPI streaming endpoint, the LangGraph tool-calling agent, its toolbox, and assembly of structured answer blocks. It consumes catalog, profile, and research exactly like the web UI does, just through a conversational surface.

## Public interface

`POST /api/chat/messages` — request: conversation_id, user message. Response: SSE stream with events:

- `status` — short progress line ("Resolving bikes…", "Researching top speed…")
- `text` — assistant prose tokens
- `block` — typed structured payload; `block.type` ∈ `comparison_table | spec_card | insight_card | research_pending | disambiguation`
- `done` / `error`

Block payload shapes are shared contracts (indexed in SHARED.md once defined) — the frontend renders them 1:1, reusing the same components as the catalog pages.

## Agent toolbox

| Tool | Backs onto | Purpose |
|---|---|---|
| `resolve_bike` | catalog | free text → bike variant candidates; emit `disambiguation` block if ambiguous |
| `get_specs` | catalog | facts with provenance, converted to the user's units |
| `compare_bikes` | catalog | aligned comparison matrix |
| `get_insights` | catalog | source-linked community/tester experience per topic |
| `get_user_profile` | profile | units, market, current bike, riding style, priorities |
| `trigger_research` | research | request a missing spec or insight; honors the hybrid inline/background contract |

## Hard rules

1. **Numbers only via tools.** The agent must never state a quantitative spec from model memory. Missing fact → `trigger_research`.
2. **Subjective topics are grounded.** Heat, comfort, maintenance, electronics, real-world behavior → `get_insights` first; missing topic → `trigger_research`. Only after research fails may the agent fall back to general knowledge, explicitly labeled as ungrounded.
3. **Disagreements are surfaced.** When official and measured values differ, present both with their tiers ("claimed 73.4 hp, dyno-tested 68 hp") — never silently pick one.
4. Every fact shown carries its source tier; the structured blocks include it.
5. "Compare with my bike" resolves the user's current bike from the profile — never asks the user to re-state it.

## Boundaries

- Does NOT write to the catalog and contains NO research logic — it only calls tools.
- Does NOT convert units (catalog does, driven by the profile).

## Open TODOs

- Conversation persistence (v1: in-memory vs. DB table) — decide when building.
- System prompt lives in this module; versioned in code, not in docs.

## Status

Spec drafted, no code.
