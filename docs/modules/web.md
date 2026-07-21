# Module: web

## Responsibility

The Vite + React + TypeScript SPA. The platform surface: catalog browsing, model pages, comparison, the personal area, and the chat page.

## Pages

- **Catalog** — browse manufacturers → models → year/trim variants; search box backed by `resolve_bike`.
- **Model page** — full spec sheet grouped by category, a `SourceBadge` on every fact, dual display when official and measured values differ, and a "Real-world notes" section rendering insights with their sources. If `data_coverage` reports missing core data, the page triggers `populate_bike`, shows per-fact "researching…" placeholders, and polls task status to fill values in as they land.
- **Compare** — pick 2+ bikes (from catalog search, garage, or dream list) → `ComparisonTable`; missing cells trigger research and fill in live.
- **Personal area** — garage (add/remove bikes, set current), dream-bike list, preference editor (units, market, riding style, priorities).
- **Chat** — a menu item: message list, input, SSE client consuming chat events (`status`, `text`, `block`, `done`, `error`).

## Shared components

Block/data renderers are shared between the catalog pages and chat — one implementation each, indexed in SHARED.md:

- `ComparisonTable` — bikes as columns, specs as rows, per-cell source badge, researching/missing states
- `SpecCard` — spec group with badges and dual official/measured display
- `InsightPanel` — per-topic community summary with source links
- `SourceBadge` — tier chip (`official | tested | community | estimated`), consistent everywhere
- `ResearchStatus` — renders pending research (chat's `research_pending` block and model-page placeholders)
- `Disambiguation` — candidate picker when `resolve_bike` is ambiguous
- `BikePicker` — search/select a bike; reused by compare, garage, dream list

State/data: TanStack Query for REST, a dedicated SSE hook for chat streaming, polling hook for research status.

## Hard rules

- **Presentation only.** No unit conversion, no spec logic, no tier resolution in the frontend — values arrive display-ready; the frontend renders what it is given.
- Payload types mirror the backend contracts and are indexed in SHARED.md; when a contract changes, both sides and the index change in the same commit.

## Boundaries

- Talks only to the FastAPI backend; no direct LLM or database access.

## Open TODOs

- Component/styling approach (plain CSS modules vs. Tailwind) — decide at scaffold time and record in DECISIONS.md.

## Status

Spec drafted, no code.
