# Architecture

```
            ┌──────────── Web UI (Next.js) ────────────┐
            │ form → live timeline (SSE) → C|Rust + stats │
            └──────────────┬────────────────────────────┘
                           │ POST /runs   GET /runs/{id}/events|diff|pairs|report
                    FastAPI  (Nebius Serverless Endpoint)
                           │
        ┌──────────────────┴──────────── orchestrator.run_migration ─────────────────────────┐
        │ 1 ingest     clone → C/C++ adapter → optional `make test` BASELINE                   │
        │ 2 analyze    include graph + function/struct signatures                              │
        │ 3 research   Tavily (cxx, bindgen, Rustonomicon) → structured C→Rust mappings        │
        │ 4 plan       Nemotron 3 Ultra → step DAG; validate_and_repair() against real graph   │
        │ 5 execute    waves in include order; Super/Nano translate units into rust-port/      │
        │ 6 verify     cargo test; Super → Ultra repairs; revert unverified steps              │
        │ 7 deliver    signature map + telemetry → PR body → GitHub PR (token never in sandbox)│
        └──────────────────────────────────────────────────────────────────────────────────────┘
        Long runs: python -m polyglot.jobs.entrypoint req.json out/   (Nebius Serverless Job)
```

## Why this scores the four criteria

| Criterion | How this project hits it |
|---|---|
| Technological Implementation | Live Token Factory calls, three Nemotron tiers, Tavily, optional Serverless Job + Endpoint, GitHub PR |
| Design | Real product UI: live agent, DAG waves, C vs Rust, signature table, token/unsafe telemetry, PR link |
| Potential Impact | Memory-unsafe C/C++ → verified Rust crate with tests, aimed at teams doing incremental rewrites |
| Quality of the Idea | Not a chat wrapper: DAG planning, AST/signature guards, baseline-aware tests, revert-don't-force |

## Model routing

| Tier | Default catalog id | Used for |
|---|---|---|
| DEEP | `nvidia/Nemotron-3-Ultra-550b-a55b` | Migration DAG, hard `cargo` repairs |
| BALANCED | `nvidia/Nemotron-3-Super-120b-a12b` | File translation, Tavily extraction, first repair |
| FAST | `nvidia/Nemotron-3-Nano-30B-A3B` | Low-risk mechanical steps |

## Design decisions

- **LLM proposes, code disposes.** Hallucinated paths are dropped; include order is taken from the real graph.
- **Translate into `rust-port/`, don't clobber C.** Reviewers can diff behavior, not lose the original.
- **Baseline first.** Pre-existing `make test` failures are not blamed on the port.
- **Revert, don't force.** A step that cannot pass `cargo test` is reverted with its dependents.
- **Secrets isolation.** Sandbox env is scrubbed; `GITHUB_TOKEN` exists only in the PR step.

## Honest gaps (say these in the demo)

- C parsing is a structured regex/AST-lite pass, not clang. Swap in `libclang` for production fidelity.
- Per-file Rust syntax is brace + shape checks; `cargo test` is the real oracle.
- Run state is in-process. Restarting the API drops live runs.
- Nested Docker is usually unavailable on Serverless Jobs; the job container *is* the sandbox.
