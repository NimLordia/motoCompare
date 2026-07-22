# Module: research

## Responsibility

Fill missing data exactly once — both quantitative specs and qualitative insights: deduplicate requests, search the web, validate and tier-classify sources, normalize, store via catalog. Memoize failures with a predefined reason and per-reason retry policy.

## Data owned

- `research_tasks` — motorcycle_id, kind (`spec | insight`), fact_key (spec_key or insight topic), state (`queued | searching | found | not_found | failed`), failure_reason, recheck_after, attempt_count, next_attempt_at, attempted_at, completed_at, result reference. **Unique on (motorcycle_id, kind, fact_key)** — this constraint IS the "research once for all users" guarantee.

## Pipelines

**Spec fact:** dedup → search → validate source & classify tier (manufacturer domain → `official`; reputable magazine/dyno test → `tested`; forums/owner reports → `community`; derived → `estimated`; the domain→tier map is code config — official domains derive from catalog's `MANUFACTURER_OFFICIAL_DOMAINS` roster, tested domains are listed in `tiering.py`) → parse value + unit → write through catalog's `upsert_spec_value` (validates against the registry, converts to canonical unit) → mark `found`.

**Insight:** dedup → search community and long-term-test sources for the (bike, topic) → require at least one verifiable source URL → synthesize a per-topic summary from real owner/tester experience → write through `upsert_insight` with all source URLs. A summary without verifiable sources is `not_found`, never stored.

**Population:** `populate_bike(bike_id)` fans out tasks for every missing core spec and core insight topic (each individually deduped). Optimization contract: **page-level extraction** — one validated source (e.g. a manufacturer spec page) is mined for every core fact it contains before further searches are issued, so populating a bike costs a few searches, not one per fact.

## Failure taxonomy

Two categories, deliberately kept apart:

**Knowledge failures** — statements about the world, memoized via `failure_reason` + `recheck_after`:

| failure_reason | Meaning | Retry policy |
|---|---|---|
| `not_released_yet` | Bike announced but data not published; expected release date stored | recheck_after = release date |
| `no_reliable_source` | Searched; nothing trustworthy found | 30-day cooldown |
| `unresolved_conflict` | Credible same-tier sources disagree beyond tolerance | 30-day cooldown; flagged for review |
| `not_applicable` | Spec/topic does not exist for this bike | never retried |
| `retries_exhausted` | Execution kept failing (see below); the fact itself is still unknown | 7-day cooldown; flagged for review |

**Execution errors** (provider rate limit, network timeout, provider outage) are NOT knowledge about the bike and are never memoized as an outcome. The task stays `queued`, `attempt_count` increments, and `next_attempt_at` follows exponential backoff (1 min → 10 min → 1 h). After `max_attempts` (default 3) the task becomes `failed` with reason `retries_exhausted`. Retries are therefore always bounded — a flaky provider can never cause needless consecutive searches.

The enum lives in code; new reasons are added there and reflected here.

## Public interface

- `request_research(bike_id, kind, fact_key) -> ResearchTask` — idempotent; returns the existing task (or its memoized failure) if present and not past `recheck_after`.
- `populate_bike(bike_id) -> list[ResearchTask]`
- `get_task(task_id)` / `get_tasks_for_bike(bike_id)` — status for UI polling. Polling doubles as the retry pump: due retries and stale `searching` tasks (crashed runs, reclaimed after 10 min) are re-dispatched here, so no scheduler exists.
- `wait_for_research(bike_id, timeout) -> bool` — chat's inline-await hook; False means research continues in the background.
- `pending_research_for_bike(bike_id)` — registered as catalog's pending-research provider at app startup, so `data_coverage` reports in-flight research.
- REST (mounted at `/api/research`): `POST /bikes/{id}/populate`, `POST /bikes/{id}/tasks`, `GET /bikes/{id}/tasks`, `GET /tasks/{id}`.

## UX contracts

- **Chat (hybrid):** chat awaits inline completion up to a configurable budget (default ~20s), streaming `status` events; on timeout it emits a `research_pending` block and the task continues in the background.
- **Web (background):** model-page/compare-triggered population runs in the background; the page polls task status and fills facts in as they land.

## Boundaries

- Sole external writer of researched data — but always through catalog's upserts, never raw SQL.
- Never fabricates: no verifiable source → `not_found` with a reason, not `estimated`.
- Does NOT decide when research is needed — chat (missing tool results) and web (via `data_coverage`) do.

## Open TODOs

- ~~Search provider (Claude API web search tool vs. external search API).~~ Resolved: Gemini API with Google Search grounding, two-phase (grounded search → JSON-schema extraction); source URLs come from grounding metadata with redirects resolved to the real pages — see DECISIONS 2026-07-22.
- ~~Background execution mechanism (FastAPI BackgroundTasks vs. worker) — simplest that satisfies both UX contracts.~~ Resolved: in-process thread pool + poll-as-retry-pump — see DECISIONS 2026-07-22.
- Source-quality heuristics per insight topic (v1 uses the shared domain→tier map for all topics; refine per topic if research quality demands it).

## Code map

`backend/app/research/` — `models.py` (research_tasks table, failure taxonomy, retry policy), `tiering.py` (domain→tier map; official domains come from catalog's manufacturer roster), `provider.py` (SearchProvider protocol + GeminiSearchProvider), `runner.py` (batched pipeline: dedup-checked execution, validation, conflict detection, writes via catalog), `executor.py` (thread-pool dispatcher with inline-await), `service.py` (public interface), `schemas.py`/`router.py` (REST at `/api/research`). Wiring (dispatcher + coverage hook) happens in `app/main.py`'s lifespan. Tests in `backend/tests/test_research_*.py` and `test_tiering.py`.

## Status

Implemented (v1): schema + migration, two-phase Gemini provider (Google Search grounding → JSON-schema extraction; grounding redirects resolved so stored source URLs are the real pages), batched runner with full failure taxonomy, background executor, REST endpoints. Same-tier conflict tolerance and provider model/attempts/workers are `MOTO_`-prefixed settings.
