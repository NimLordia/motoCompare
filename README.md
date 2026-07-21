# motoCompare

A personalized motorcycle platform with a self-filling, source-aware specification database. Keep a garage and a dream-bike list, browse every manufacturer and model, compare bikes side by side, and ask an assistant that never invents numbers.

## What makes it interesting

- **Self-filling catalog.** Open a model nobody has viewed before and an AI research agent populates its spec sheet live — researched once, stored for every future user.
- **No ungrounded claims.** Quantitative specs come from the database, never from LLM memory. Subjective topics — engine heat, comfort, maintenance — come from researched real-owner experience, stored with source links.
- **Provenance everywhere.** Every fact is tiered: official / independently tested / community-reported / estimated. When the manufacturer's claim and the dyno disagree, you see both.
- **Personalized.** Units, market, and riding style shape every answer; compare anything against your own bike.

## Stack

React (Vite + TypeScript) · FastAPI · LangGraph · PostgreSQL · Claude API

## Status

🚧 In development — architecture and module specs live in [docs/](docs/SCOPE.md).
