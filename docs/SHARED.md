# Shared Code Index

One line per reusable item. **Check this file before writing any new helper, component, hook, type, or utility.** If something close exists, generalize it (after checking blast radius — see CLAUDE.md rule 3) instead of duplicating. Every new reusable item gets a line here in the same commit that creates it.

Format: `symbol(signature)` — path — one-line purpose.

## Backend — utilities

- `get_settings() -> Settings` — backend/app/config.py — cached pydantic-settings (env prefix `MOTO_`, reads `.env`)
- `Base` / `SessionLocal` / `get_db()` — backend/app/db.py — declarative base with naming conventions, session factory, FastAPI session dependency

## Backend — services & types

- `units.convert(value, from_unit, to_unit)` — backend/app/catalog/units.py — pure conversion (linear pairs + reciprocal L/100km↔mpg); raises `UnknownConversionError`
- `units.display_unit(canonical_unit, unit_system)` — backend/app/catalog/units.py — canonical → display unit per unit system ("metric"/"imperial")
- catalog service (`list_manufacturers/list_models/list_variants/resolve_bike/data_coverage/get_specs/compare/get_insights/get_bike_detail/upsert_spec_value/upsert_insight`) — backend/app/catalog/service.py — the catalog public interface; other modules go through these, never raw SQL
- `CatalogNotFoundError` / `CatalogValidationError` — backend/app/catalog/service.py — service exceptions, mapped to 404/422 by app-level handlers in main.py
- `register_pending_research_provider(fn)` — backend/app/catalog/service.py — hook the research module uses to surface in-flight research in `data_coverage`
- `SourceType` / `ValueType` / `SOURCE_TIER_PRIORITY` — backend/app/catalog/models.py — source tier enum + resolution order
- `SPEC_DEFINITIONS` / `CORE_SPEC_KEYS` / `INSIGHT_TOPICS` — backend/app/catalog/registry.py — code bootstrap of the spec registry and topic list

## Frontend — components

*(nothing yet)*

## Frontend — hooks & utilities

*(nothing yet)*

## Shared contracts (API payload types)

- `Fact`, `Coverage`, `BikeCandidate`, `ComparisonMatrix`/`Row`/`Cell`, `BikeDetail`, `InsightOut`, `ManufacturerOut`/`ModelOut`/`VariantOut` — backend/app/catalog/schemas.py — Pydantic payloads returned by the catalog API; the frontend mirrors these
