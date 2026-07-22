# motoCompare — Project Scope

## Vision

A personalized motorcycle platform backed by a growing, source-aware database. Users maintain a **personal area** (garage of owned bikes, dream-bike list, preferences), browse a **global catalog** of manufacturers and models, view full spec sheets with per-fact provenance, and **compare** any bikes side by side. Opening a model with no data triggers an AI research agent that fills it in — once, for every future user. An **assistant chat**, grounded in the same database, is one feature in the menu — not the center of the app.

## Core principles

1. **No invented numbers.** Quantitative answers come only from the database. Missing data triggers the research pipeline.
2. **Provenance per fact.** Every value carries a source tier — `official | tested | community | estimated` — plus source URL and retrieval date. When official and measured values disagree, **both are shown**; the discrepancy is information, not noise.
3. **Grounded opinions.** Subjective topics (heat, comfort, maintenance, electronics, real-world performance) are answered from researched real-owner and tester experience stored per bike per topic with sources — never from model memory alone.
4. **Canonical units in, personalized units out.** Facts are stored in canonical units defined by the spec registry; conversion happens once, at the API response layer, driven by the user profile.
5. **Research once, reuse forever.** A missing fact or insight is researched a single time (deduplicated by unique constraint), validated, normalized, and stored for all users. Failures are memoized with a predefined reason and a per-reason retry policy.

## Modules

| Module | Spec | Responsibility | Status |
|---|---|---|---|
| catalog | [modules/catalog.md](modules/catalog.md) | Bike identity, spec registry, facts + insights storage, browsing API, unit conversion | implemented (v1) |
| research | [modules/research.md](modules/research.md) | Missing-data pipeline for specs and insights, failure taxonomy, bike auto-population | implemented (v1) |
| profile | [modules/profile.md](modules/profile.md) | Personal area: preferences, garage, dream bikes | implemented (v1) |
| chat | [modules/chat.md](modules/chat.md) | Assistant feature: LangGraph agent, tools, streaming | implemented (v1) |
| web | [modules/web.md](modules/web.md) | SPA: catalog browser, model pages, compare, personal area, chat | spec drafted |

## V1 scope

**In:** catalog browsing (manufacturer → model → year/trim); model pages with full spec sheet, source badges, dual official/measured display, and real-world insight notes; auto-population of empty models with live research status; N-way comparison; personal area (garage with a designated current bike, dream-bike list, preferences); live unit conversion; assistant chat with grounded answers, structured blocks, and hybrid inline/background research.

**Out (deliberately):** authentication (single local user — but every user-scoped table carries `user_id` from day one so multi-user is a migration, not a rewrite), pricing data (market-dependent, needs its own model), photos/media, dealer or listing integrations, mobile app.

## Repo layout

```
/backend        FastAPI app: catalog, research, profile, chat modules
/frontend       Vite + React + TypeScript SPA
/docs           This documentation tree
docker-compose.yml   PostgreSQL for local development
```

## Current status

2026-07-21 — Planning v2 complete after product pivot: platform-first, chat as one feature. Qualitative insights, failure taxonomy, and auto-population added to the design.

2026-07-21 — Backend scaffold and catalog module implemented: schema + migration, service layer, browsing API, seeds, 51 tests. Next: research module (the catalog's `register_pending_research_provider` hook and upserts are its integration points).

2026-07-22 — Research module implemented: two-phase Claude web-search provider, batched pipeline with the full failure taxonomy, in-process executor (chat inline-await + web polling), REST endpoints, 65 tests (116 total). Next: profile module, or chat now that `wait_for_research` exists.

2026-07-22 — Project LLM provider switched to Gemini (the project runs on a Gemini API key). Research now uses Google Search grounding + JSON-schema extraction with redirect-resolved source URLs; chat will use `langchain-google-genai`. See DECISIONS 2026-07-22.

2026-07-22 — Profile module implemented: single lazy-created local user, preferences (with the new `mixed` unit system, applied by catalog), garage with a database-enforced one-current invariant, dream bikes; REST + service layer, 36 tests (167 total). Next: chat (`get_profile` and `wait_for_research` are both ready for it).

2026-07-22 — Manufacturer roster unified: `MANUFACTURER_OFFICIAL_DOMAINS` in the catalog registry is now the single source of truth for both the seeded manufacturer list and research's official-tier domains (the two had drifted: 19 vs. 6). Seed now creates all 19 manufacturers (190 tests total).

2026-07-22 — Chat module implemented: SSE streaming endpoint, six-tool LangGraph agent on Gemini with the grounding hard rules, structured blocks reusing catalog payloads, hybrid inline/background research, per-conversation memory; 30 tests. Verified live against the Gemini API (tool loop, blocks, dual official/tested presentation). Next: the web SPA — every backend module it needs is now in place.
