# Decisions Log

Settled choices. Check here before re-deciding anything architectural; append new entries with reasoning, never silently reverse old ones — supersede them with a new dated entry.

---

**2026-07-21 — PostgreSQL as the database.**
Why: the data model is relational at its core (bikes → facts → sources), needs unique constraints for research deduplication, and pgvector is available later if semantic retrieval over community info is wanted.

**2026-07-21 — Per-fact provenance table (`spec_values`) instead of wide spec columns.**
Why: provenance is per-fact, not per-bike — a bike's horsepower can be official while its 0–100 time is community-reported. A wide table has nowhere to hang source metadata, and the fact table lets one spec hold values from multiple source tiers simultaneously.

**2026-07-21 — Canonical units in storage, conversion at the API response layer.**
Why: one conversion implementation, driven by the user profile; the frontend stays presentation-only. The spec registry (`spec_definitions`) is the single source of truth for each spec's canonical unit.

**2026-07-21 — Source tiers `official | tested | community | estimated`, resolved in that priority order.**
Why: matches the product requirement to distinguish manufacturer claims from dyno results from forum lore; the tier is surfaced to the user as a badge.

**2026-07-21 — The model never invents numbers.**
Why: this is the credibility core of the project. All quantitative claims flow through tools against the database; missing facts trigger research; subjective answers are allowed from model knowledge but labeled.

**2026-07-21 — Research once per fact, memoize failures.**
Why: a unique constraint on (motorcycle_id, spec_key) in research tasks is the "research once, reuse for all users" guarantee. Failed lookups are stored with a timestamp and a retry cooldown so unfindable facts don't re-trigger doomed searches.

**2026-07-21 — Hybrid research UX (~20s inline budget, then background).**
Why: inline streamed research feels magical when fast; the timeout prevents a slow search from stalling the conversation. Chosen over always-inline and always-background.

**2026-07-21 — Structured chat blocks instead of markdown-only answers.**
Why: the backend emits typed payloads (comparison table, spec card, source badges) that React renders as rich components inline in chat. Strongest portfolio visual; also makes source tiers legible.

**2026-07-21 — Vite SPA instead of Next.js.**
Why: all server logic lives in Python, so Next.js's server features would be redundant. Clean SPA↔API separation.

**2026-07-21 — No auth in v1.**
Why: single local profile; fastest path to the differentiating features. Every table carries `user_id` from day one so adding auth later is a migration, not a rewrite.

**2026-07-21 — LangGraph tool-calling agent; Claude API via `langchain-anthropic`, swappable behind config.** *Superseded 2026-07-22: the project's LLM provider is now Gemini.*
Why: LangGraph is the current LangChain idiom for agent loops; provider kept behind config so the demo isn't locked to one vendor.

**2026-07-21 — Monorepo: `/backend`, `/frontend`, docker-compose for Postgres.**
Why: one repo tells one story for reviewers; compose gives a one-command local setup.

**2026-07-21 — Platform, not chatbot (supersedes the chat-centric vision from earlier today).**
Why: the product is a personal area (garage, dream bikes, preferences) plus a browsable global catalog with comparison; opening a model with no data triggers research. Chat is one menu feature consuming the same services — not the heart of the app.

**2026-07-21 — PostgreSQL confirmed as the only datastore in v1; Redis considered and deferred.**
Why: the data is deeply relational (garage → bike → model → manufacturer FKs, joins for comparison, unique constraints doing real work for research dedup and one-insight-per-topic) and the database is the product's accumulating asset — durability matters. Redis may join later as a cache or task queue if a measured need appears, never as the primary store.

**2026-07-21 — Qualitative community insights are first-class researched facts.**
Why: subjective topics (heat, comfort, maintenance, electronics, real-world performance) must be grounded in real owner/tester experience from the internet, stored per (bike, topic) with source URLs — not answered from model memory. Same research-once pipeline as specs.

**2026-07-21 — Predefined research-failure taxonomy with per-reason retry policy; execution errors are not failure reasons.**
Why: failures are information. `not_released_yet` stores the expected release date and rechecks then; `not_applicable` never retries; `no_reliable_source` cools down 30 days. Infrastructure errors (rate limits, network) are deliberately excluded from the taxonomy — a generic `transient_error` reason was rejected as too broad and retry-loop-prone. Instead they retry with bounded exponential backoff and become `retries_exhausted` after 3 attempts. Taxonomy lives in modules/research.md.

**2026-07-21 — When official and measured values differ, show both.**
Why: the discrepancy itself is useful information (claimed vs. dyno horsepower); hiding it behind tier resolution loses it. UI renders dual values with tier badges; chat mentions both.

**2026-07-21 — Core spec set drives auto-population.**
Why: `spec_definitions.is_core` marks what every bike page needs; opening an under-populated model triggers `populate_bike`, which uses page-level extraction (mine every core fact from each validated source) so populating a bike costs a few searches, not one per fact.

**2026-07-21 — v1 spec registry: 13 definitions (8 core) and six insight topics, defined in code and seeded to the DB.**
Why: `backend/app/catalog/registry.py` is the bootstrap source (tests and seeds build from it); the `spec_definitions` table is the runtime truth the API validates against. Core: engine_type, displacement, power_peak, torque_peak, wet_weight, seat_height, fuel_capacity, top_speed. Non-core: compression_ratio, dry_weight, wheelbase, acceleration_0_100, fuel_consumption. Insight topics: heat, comfort, maintenance, electronics, reliability, real_world_performance — all six count toward coverage. Adding a spec = one line in registry.py + rerun the idempotent seed; no migration.

**2026-07-21 — Seed strategy: idempotent code-defined seed script, run through the service layer.**
Why: `python -m app.catalog.seed` upserts the spec registry plus eight well-known bikes — official figures with manufacturer source URLs, a few magazine-tested values so the dual official/measured display has real content, and one deliberately incomplete bike (KTM 390 Duke) so `data_coverage` gaps are visible in the demo. Seeds go through `upsert_spec_value`/`upsert_insight`, so they obey the same validation and unit conversion as researched data. Kept out of migrations: schema and data change on different cadences, and reseeding must be safe to repeat.

**2026-07-21 — `resolve_bike` fuzzy matching is application-side token scoring, not pg_trgm.**
Why: the dominant query shape is short aliases ("R7", "mt07"), and trigram similarity collapses on 2–4 character queries against full names like "Yamaha YZF-R7 2023". Token-level scoring (exact > containment > difflib ratio, with noise floors) handles hyphen splits (YZF-R7 → r7) naturally, is unit-testable on SQLite, and is cheap at catalog scale (thousands of variants, scored in-process). Supersede with pg_trgm + GIN if the catalog ever outgrows in-process scoring.

**2026-07-21 — Unit tests run on in-memory SQLite; models stay dual-dialect.**
Why: fast, infrastructure-free tests and trivial CI. Cost: model columns must work on both dialects, so `insights.source_urls` is JSON (JSONB variant on PostgreSQL) rather than ARRAY, and enums are portable VARCHARs. Migrations remain PostgreSQL-only; `alembic check` guards model↔migration parity.

**2026-07-22 — Research search provider: Claude API web search tool, in two phases (search → structured extraction).** *Superseded later the same day: the provider is now Gemini; the two-phase design carries over.*
Why: the stack already carries the Claude dependency, so no second search vendor or API key is needed, and the server-side tool handles crawling and citation. Phase one gathers source-cited notes with the web search tool (one pass mines every requested fact — the page-level extraction contract); phase two turns those notes into typed JSON with a structured-output call. Splitting the phases keeps each API call on a documented feature combination and makes parsing schema-guaranteed instead of prompt-hopeful. The provider sits behind a `SearchProvider` protocol, so swapping it is one class.

**2026-07-22 — Research background execution: in-process thread pool; polling doubles as the retry pump.**
Why: the simplest mechanism satisfying both UX contracts. A small `ThreadPoolExecutor` with one deduplicated job per bike gives chat its ~20s inline await (`wait_for_research` blocks on the same future) and lets web poll task state — and because every poll re-dispatches due retries and stale `searching` tasks, no scheduler, timer, or worker process exists. Chosen over FastAPI BackgroundTasks (nothing to await inline) and a worker/queue (rejected with Redis earlier). Restart-safe because all state lives in `research_tasks`.

**2026-07-22 — Source tier classified from a domain→tier map in code; same-tier numeric conflicts beyond 15% are memoized, lower-tier conflicts only discredit that tier.**
Why: manufacturer domains → `official`, known test publications → `tested`, everything else with a verifiable URL → `community` — a reviewable allowlist beats model self-labeling. Conflict rule: after canonical-unit conversion, same-tier values whose spread exceeds 15% of their mean are `unresolved_conflict` when they are the best tier (the discrepancy is flagged, nothing stored); a conflicted *lower* tier is simply skipped so forum noise can't block an official value. Agreement stores the median candidate, keeping value and source URL paired. Research never writes `estimated` — deriving values would violate "never fabricates".

**2026-07-22 — Gemini is the project's LLM provider; research runs on Google Search grounding + JSON-schema output. (Supersedes the Claude provider decision from earlier today and the `langchain-anthropic` part of the chat decision.)**
Why: the project runs on a Gemini API key. The two-phase research design carries over unchanged behind the same `SearchProvider` protocol — phase one grounds a research pass in Google Search, phase two extracts typed findings with a `response_schema`-constrained call (Gemini cannot combine search grounding with JSON mode in one request, so the split is now load-bearing, not just tidy). One Gemini-specific addition: grounded citations arrive as expiring Google redirect URLs in metadata, not as text, so the provider inserts citation markers from `grounding_supports` and resolves each redirect (a single non-following HEAD to Google) into a verified source list that extraction copies URLs from — provenance comes from search metadata, never model memory. Default model `gemini-2.5-flash` (free tier, supports both features), overridable via `MOTO_RESEARCH_MODEL`. Chat, when built, uses `langchain-google-genai`.
