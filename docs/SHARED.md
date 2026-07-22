# Shared Code Index

One line per reusable item. **Check this file before writing any new helper, component, hook, type, or utility.** If something close exists, generalize it (after checking blast radius — see CLAUDE.md rule 3) instead of duplicating. Every new reusable item gets a line here in the same commit that creates it.

Format: `symbol(signature)` — path — one-line purpose.

## Backend — utilities

- `get_settings() -> Settings` — backend/app/config.py — cached pydantic-settings (env prefix `MOTO_`, reads `.env`)
- `Base` / `SessionLocal` / `get_db()` — backend/app/db.py — declarative base with naming conventions, session factory, FastAPI session dependency
- `ensure_utc(dt)` — backend/app/db.py — naive→UTC normalizer for timezone-aware columns read from SQLite; use before comparing or serializing stored datetimes

## Backend — services & types

- `units.convert(value, from_unit, to_unit)` — backend/app/catalog/units.py — pure conversion (linear pairs + reciprocal L/100km↔mpg); raises `UnknownConversionError`
- `units.display_unit(canonical_unit, unit_system)` — backend/app/catalog/units.py — canonical → display unit per unit system ("metric"/"imperial"/"mixed")
- catalog service (`list_manufacturers/list_models/list_variants/get_variant/resolve_bike/data_coverage/get_specs/compare/get_insights/get_bike_detail/upsert_spec_value/upsert_insight`) — backend/app/catalog/service.py — the catalog public interface; other modules go through these, never raw SQL
- `CatalogNotFoundError` / `CatalogValidationError` — backend/app/catalog/service.py — service exceptions, mapped to 404/422 by app-level handlers in main.py
- `register_pending_research_provider(fn)` — backend/app/catalog/service.py — hook the research module uses to surface in-flight research in `data_coverage`
- `SourceType` / `ValueType` / `SOURCE_TIER_PRIORITY` — backend/app/catalog/models.py — source tier enum + resolution order
- `PortableJSON` — backend/app/catalog/models.py — JSON column type (JSONB variant on PostgreSQL) for dual-dialect models
- `SPEC_DEFINITIONS` / `CORE_SPEC_KEYS` / `INSIGHT_TOPICS` — backend/app/catalog/registry.py — code bootstrap of the spec registry and topic list
- research service (`request_research/populate_bike/get_task/get_tasks_for_bike/wait_for_research/pending_research_for_bike/configure_dispatcher`) — backend/app/research/service.py — the research public interface
- `ResearchNotFoundError` / `ResearchValidationError` — backend/app/research/service.py — service exceptions, mapped to 404/422 in main.py
- profile service (`get_profile/update_profile/list_garage/add_garage_bike/set_current_garage_bike/remove_garage_bike/list_dream_bikes/add_dream_bike/remove_dream_bike`) — backend/app/profile/service.py — the profile public interface
- `ProfileNotFoundError` / `ProfileValidationError` — backend/app/profile/service.py — service exceptions, mapped to 404/422 in main.py
- `DEFAULT_USER_ID` / `UnitSystemPreference` — backend/app/profile/models.py — v1 single-user id + unit preference enum (metric/imperial/mixed)
- `ResearchKind` / `ResearchTaskState` / `FailureReason` / `FAILURE_COOLDOWNS` — backend/app/research/models.py — task enums and retry policy
- `SearchProvider` protocol + `SpecRequest`/`SpecFinding`/`InsightFinding`/`ResearchFindings` + `ResearchExecutionError` — backend/app/research/provider.py — the pluggable research-provider contract
- `GeminiSearchProvider` — backend/app/research/provider.py — two-phase Gemini implementation (Google Search grounding → JSON-schema extraction, with redirect-resolved source URLs)
- `classify_source_tier(url)` / `is_valid_source_url(url)` — backend/app/research/tiering.py — domain→tier map and URL sanity check
- `run_bike_research(db, provider, bike_id)` — backend/app/research/runner.py — batched pipeline execution for one bike
- `BackgroundResearchExecutor` — backend/app/research/executor.py — thread-pool dispatcher with per-bike dedup and inline await
- chat service (`configure_chat_model/chat_is_configured/stream_chat` + `ChatEvent`) — backend/app/chat/service.py — the chat public interface; stream_chat yields SSE-ready events
- `build_toolbox(db, user_id, unit_system, inline_budget_seconds)` — backend/app/chat/tools.py — the agent's six tools bound to one request; `status_line(tool_name, args)` maps a tool call to its progress line
- `build_chat_agent(model, tools, checkpointer)` — backend/app/chat/agent.py — compiled LangGraph tool loop (sequential tool execution; `RECURSION_LIMIT` step budget)
- `SYSTEM_PROMPT` / `SYSTEM_PROMPT_VERSION` — backend/app/chat/prompts.py — the assistant's versioned system prompt
- `db` / `make_bike` fixtures — backend/tests/conftest.py — in-memory SQLite session with seeded registry + bike factory; reuse in any backend test
- `fake_provider` fixture (`FakeSearchProvider`) — backend/tests/conftest.py — scripted SearchProvider for research tests
- `scripted_chat` fixture (`FakeChatModel`) — backend/tests/conftest.py — scripted tool-calling chat model for agent/stream tests; records prompts and bound tools

## Frontend — components

*(nothing yet)*

## Frontend — hooks & utilities

*(nothing yet)*

## Shared contracts (API payload types)

- `Fact`, `Coverage`, `BikeCandidate`, `ComparisonMatrix`/`Row`/`Cell`, `BikeDetail`, `InsightOut`, `ManufacturerOut`/`ModelOut`/`VariantOut` — backend/app/catalog/schemas.py — Pydantic payloads returned by the catalog API; the frontend mirrors these
- `ResearchTaskOut` / `ResearchRequestIn` — backend/app/research/schemas.py — research API payloads for task polling and requests
- `ProfileOut` / `ProfileUpdateIn` / `GarageBikeOut` / `GarageBikeIn` / `DreamBikeOut` / `DreamBikeIn` — backend/app/profile/schemas.py — profile API payloads; garage/dream entries embed the catalog `VariantOut`
- `ChatMessageIn` + chat blocks (`SpecCardBlock`/`ComparisonTableBlock`/`InsightCardBlock`/`ResearchPendingBlock`/`DisambiguationBlock`, union `ChatBlock`) — backend/app/chat/schemas.py — chat request + SSE `block` event payloads; blocks embed catalog payloads unchanged, so the frontend reuses catalog components
