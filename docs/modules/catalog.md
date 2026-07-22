# Module: catalog

## Responsibility

Motorcycle identity, the spec registry, source-aware storage of facts and insights, the browsing API, and unit conversion. This module owns the truth; every other module reads bikes and their data through it.

## Data owned

- `manufacturers` — id, name
- `models` — id, manufacturer_id, name (e.g. "YZF-R7")
- `motorcycles` — id, model_id, year, trim, market. One row = one identifiable variant.
- `spec_definitions` — the registry: key (e.g. `power_peak`), canonical_unit (e.g. `kW`), value_type, category (engine/chassis/performance/…), **is_core** (part of the auto-population set every bike page needs). Single source of truth for what specs exist and how they are stored.
- `spec_values` — the quantitative fact table: motorcycle_id, spec_key, value, source_type (`official | tested | community | estimated`), source_url, source_note, retrieved_at. **Unique on (motorcycle_id, spec_key, source_type)** — official and measured values coexist by design.
- `insights` — the qualitative fact table: motorcycle_id, topic (`heat | comfort | maintenance | electronics | reliability | real_world_performance | …`), summary, source_type (`community | tested`), source_urls[], retrieved_at. Unique on (motorcycle_id, topic). One researched, source-linked summary per topic per bike.

Canonical unit examples: power kW, torque Nm, mass kg, speed km/h, length mm, volume L, time s, displacement cc.

## Public interface

Browsing (backs the web catalog):
- `list_manufacturers()` / `list_models(manufacturer_id)` / `list_variants(model_id)`
- `get_variant(bike_id) -> VariantOut` — one variant with its display name; the FK-validation and rendering hook for other modules (profile's garage/dream bikes).
- `resolve_bike(query: str, market: str | None) -> list[BikeCandidate]` — fuzzy text → ranked variants ("R7" → Yamaha YZF-R7 2023 EU), with confidence; the caller decides whether to disambiguate.
- `data_coverage(bike_id) -> Coverage` — which core specs and insight topics are present vs. missing (and whether research is pending). Web uses this to decide when to trigger population and to render "researching…" states.

Facts:
- `get_specs(bike_id, keys | None, unit_system) -> list[Fact]` — values converted to the requested units, **all source tiers present returned**, resolved display order official > tested > community > estimated. Unit systems: `metric | imperial | mixed` (mixed = metric with power in hp — the motorcycle-press convention).
- `compare(bike_ids, keys | None, unit_system) -> ComparisonMatrix` — aligned facts across bikes with per-cell provenance and explicit `missing` markers.
- `get_insights(bike_id, topics | None) -> list[Insight]`
- `upsert_spec_value(...)` / `upsert_insight(...)` — validate against the registry / topic list, convert to canonical units, write. **The research module is the only external writer of both.**
- `units.convert(value, from_unit, to_unit)` — pure function. Conversion to display units happens only inside this module; research also calls it to normalize candidate values to canonical units before its conflict checks.

## Boundaries

- Does NOT search the web or fill missing data — that is [research](research.md).
- Does NOT phrase answers or decide presentation — that is [chat](chat.md) / [web](web.md).
- No other module converts units or writes `spec_values`/`insights` directly.

## Open TODOs

- ~~Seed strategy: initial dataset of common bikes so the demo isn't an empty database.~~ Resolved: idempotent seed script (`python -m app.catalog.seed`) — see DECISIONS 2026-07-21.
- ~~Fuzzy-matching approach for `resolve_bike` (pg_trgm vs. application-side scoring).~~ Resolved: application-side token scoring — see DECISIONS 2026-07-21.
- ~~Final list of core specs and insight topics.~~ Resolved: 13 spec definitions (8 core) and six insight topics in `backend/app/catalog/registry.py` — see DECISIONS 2026-07-21.

## Code map

`backend/app/catalog/` — `models.py` (tables), `registry.py` (spec/topic bootstrap), `units.py` (conversion), `service.py` (public interface), `schemas.py` (API payloads), `router.py` (REST, mounted at `/api/catalog`), `seed.py` (demo data). Tests in `backend/tests/`.

## Status

Implemented (v1): schema + Alembic migration, service layer, REST endpoints, idempotent seed, 51 tests. `data_coverage` reports research as pending only once the research module registers its provider hook.
