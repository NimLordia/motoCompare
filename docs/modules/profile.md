# Module: profile

## Responsibility

The personal area: user preferences, the garage (owned bikes, one designated current), and the dream-bike list. Everything that personalizes answers and comparisons.

## Data owned

- `users` — id. V1 has exactly one row (`DEFAULT_USER_ID = 1`), created lazily on the first profile write; **no auth in v1**, but `user_id` exists on every user-scoped table from day one so multi-user/auth later is a migration, not a rewrite.
- `profiles` — user_id (PK), unit_system (`metric | imperial | mixed` — mixed = metric with power in hp, see DECISIONS 2026-07-22), market, riding_style, priority_factors (ordered JSON list: heat, comfort, performance, cost, …).
- `garage_bikes` — user_id, motorcycle_id (FK → catalog.motorcycles, `ondelete CASCADE`), is_current, nickname, added_at. Unique on (user_id, motorcycle_id); **exactly one current per non-empty garage**, enforced by a partial unique index (`user_id WHERE is_current`, valid on PostgreSQL and SQLite).
- `dream_bikes` — user_id, motorcycle_id (FK → catalog.motorcycles), note, added_at. Unique on (user_id, motorcycle_id).

Bikes are always stored as catalog FKs, never as free text — so "compare with my bike" is a normal catalog comparison. Resolution from free text happens before the write: the caller (web UI, chat) uses catalog's `resolve_bike`, then POSTs the chosen id; the service validates the FK via catalog's `get_variant` (404 on a dangling id).

## Public interface

REST (all operating on the v1 default user):
- `GET /api/profile` — preferences + current bike; returns defaults (`metric`, empty list) without writing when nothing is stored yet.
- `PUT /api/profile` — full replace of preferences. Priority factors must be non-empty and non-repeating (order carries meaning).
- `GET/POST /api/garage`, `DELETE /api/garage/{id}`, `PUT /api/garage/{id}/current` — POST is an upsert on (user, variant) that refreshes the nickname; the first bike added to an empty garage becomes current; deleting the current bike promotes the most recently added remaining one; the list is ordered current-first, then newest.
- `GET/POST /api/dream-bikes`, `DELETE /api/dream-bikes/{id}` — POST is an upsert that refreshes the note.

Service functions (chat's `get_user_profile` tool and catalog-consumers use these):
- `get_profile(db, user_id) -> ProfileOut` — preferences + current bike. Feeds chat's user context and the unit_system passed to catalog's conversion at the response layer.
- `update_profile / list_garage / add_garage_bike / set_current_garage_bike / remove_garage_bike / list_dream_bikes / add_dream_bike / remove_dream_bike`
- `ProfileNotFoundError` / `ProfileValidationError` — mapped to 404/422 in main.py.

## Boundaries

- Does NOT convert units — it states the preference; catalog applies it.
- Does NOT store conversation history or any catalog data.

## Open TODOs

- Exact enum lists for riding_style and priority_factors — settle when building the personal-area UI. Until then both accept free text (factors validated non-empty and non-repeating only).

## Code map

`backend/app/profile/` — `models.py` (tables, `DEFAULT_USER_ID`, `UnitSystemPreference`), `service.py` (public interface), `schemas.py` (API payloads), `router.py` (REST, mounted at `/api`). Migration `0003_profile_tables`. Tests in `backend/tests/test_profile_service.py` and `test_profile_api.py`.

## Status

Implemented (v1): schema + migration, service layer, REST endpoints, 36 tests (service + API + mixed-unit coverage in catalog tests).
