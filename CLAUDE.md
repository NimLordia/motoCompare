# motoCompare

Motorcycle research platform over a growing, source-aware database: a personal area (garage, dream bikes, preferences), a browsable global catalog that self-fills via an AI research agent, side-by-side comparison, and a grounded assistant chat as one menu feature.

Stack: React (Vite + TypeScript) · FastAPI · LangGraph/LangChain · PostgreSQL · Claude API

## Documentation map — read only what the task needs

| File | What it holds |
|---|---|
| [docs/SCOPE.md](docs/SCOPE.md) | Project scope, module index with status, repo layout |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Settled decisions and why — do not re-litigate |
| [docs/SHARED.md](docs/SHARED.md) | Index of all reusable code — check before writing anything new |
| docs/modules/*.md | One contract-level spec per module |

## Session rules

1. **Context discipline.** Start by reading SCOPE.md, then only the module spec(s) the task touches. Do not load other module specs unless the task crosses their boundary. When spawning subagents, pass them the specific spec paths they need — never "read all the docs".
2. **No duplication.** Before writing any new helper, component, hook, or type: check docs/SHARED.md. If something close already exists, generalize it to cover the new need instead of writing a parallel version.
3. **Blast radius before generalizing.** Before changing shared code: grep for every consumer, list them, verify each one still works after your generalization, and run their tests. Only then commit.
4. **Docs move with code, in the same commit.** Changed a module's public surface → update its spec. Added reusable code → add one line to SHARED.md. Made an architectural choice → append it to DECISIONS.md with the reasoning.
5. **The core product rule: no ungrounded claims.** Quantitative specs come only from the database via tools; subjective topics (heat, comfort, maintenance, real-world behavior) come from stored, source-linked community insights. Missing data triggers the research pipeline — never model memory. Only after research has failed may the assistant fall back to general knowledge, explicitly labeled as such.
6. **Keep SCOPE.md's module status column current** whenever a module's state changes.
