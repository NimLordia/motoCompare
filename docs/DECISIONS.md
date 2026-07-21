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

**2026-07-21 — LangGraph tool-calling agent; Claude API via `langchain-anthropic`, swappable behind config.**
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
