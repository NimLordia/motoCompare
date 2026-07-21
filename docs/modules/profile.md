# Module: profile

## Responsibility

The personal area: user preferences, the garage (owned bikes, one designated current), and the dream-bike list. Everything that personalizes answers and comparisons.

## Data owned

- `users` — id. V1 has exactly one row (the local user); **no auth in v1**, but `user_id` exists on every user-scoped table from day one so multi-user/auth later is a migration, not a rewrite.
- `profiles` — user_id, unit_system (`metric | imperial | mixed`), country/market, riding_style, priority_factors (ordered list: heat, comfort, performance, cost, …).
- `garage_bikes` — user_id, motorcycle_id (FK → catalog.motorcycles), is_current (exactly one true per user), nickname, added_at.
- `dream_bikes` — user_id, motorcycle_id (FK → catalog.motorcycles), note, added_at.

Bikes are always stored as catalog FKs (resolved via `resolve_bike` when the user adds them), never as free text — so "compare with my bike" is a normal catalog comparison.

## Public interface

- `GET /api/profile` / `PUT /api/profile`
- `GET/POST/DELETE /api/garage` + `PUT /api/garage/{id}/current`
- `GET/POST/DELETE /api/dream-bikes`
- `get_profile(user_id) -> Profile` — service function: preferences + current bike. Consumed by chat's `get_user_profile` tool and by catalog's unit conversion at the response layer.

## Boundaries

- Does NOT convert units — it states the preference; catalog applies it.
- Does NOT store conversation history or any catalog data.

## Open TODOs

- Exact enum lists for riding_style and priority_factors — settle when building the personal-area UI.

## Status

Spec drafted, no code.
