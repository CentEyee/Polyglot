# PolyGlot Refactor AI

An autonomous **C/C++ → Rust** migration agent. It clones a repo, builds an include/call graph, plans a transformation DAG with **NVIDIA Nemotron 3 Ultra**, rewrites translation units in parallel with **Super / Nano** on **Nebius Token Factory**, runs `cargo test` until green, and opens a reviewable pull request.

Built for the Nebius × NVIDIA Global AI Hackathon — **Best Apps and Agents**.

## How it uses Nebius and NVIDIA

| Piece | Where | Role |
|---|---|---|
| Token Factory (`https://api.tokenfactory.nebius.com/v1`) | `backend/polyglot/llm/client.py` | Every model call |
| Nemotron 3 Ultra | `planner/planner.py`, `verify/loop.py` | DAG plan, hard repairs |
| Nemotron 3 Super | `executor/worker.py`, `research/tavily.py` | Default translation + mapping extract |
| Nemotron 3 Nano | `executor/worker.py` | Low-risk mechanical steps |
| Tavily Search | `research/tavily.py` | Ground mappings in real docs (prize) |
| Serverless Job | `python -m polyglot.jobs.entrypoint` | One isolated container per run |
| Serverless Endpoint | `uvicorn polyglot.api.main:app` | Hosted API + SSE |
| GitHub | `vcs/pr.py` | PR only; token never enters the sandbox |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/HACKATHON.md](docs/HACKATHON.md).

## Where to put API keys

1. Copy `.env.example` → `.env` at the **repository root** (already done if you had keys).
2. Fill:

```
NEBIUS_API_KEY=          # Token Factory console → API keys
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1
LLM_DEEP=nvidia/Nemotron-3-Ultra-550b-a55b
LLM_BALANCED=nvidia/Nemotron-3-Super-120b-a12b
LLM_FAST=nvidia/Nemotron-3-Nano-30B-A3B
TAVILY_API_KEY=          # tavily.com
GITHUB_TOKEN=            # optional, contents:write + pull_requests:write
```

3. If your Token Factory catalog shows ids **without** `nvidia/`, that is fine — the backend prefixes it.
4. Keys stay on the API process. The Next.js app only talks to `http://localhost:8000`. **Never** put keys in `frontend/`.

Confirm: `curl -s http://localhost:8000/health` should show `"token_factory": true`.

## Run it

```bash
# Python 3.11+  (gcc + cargo recommended for a live port)
python3 -m venv .venv && source .venv/bin/activate
make dev && make test          # unit tests, no network
make api                       # http://localhost:8000
make web                       # http://localhost:3000
```

In the UI: **Load bundled satadd example** → **Start C → Rust**.

Headless (what a Serverless Job runs):

```bash
cat > /tmp/req.json <<'JSON'
{"repo_url":"/ABS/PATH/examples/c-satadd","ref":"","instruction":"Migrate this C library to safe idiomatic Rust","open_pr":false}
JSON
python -m polyglot.jobs.entrypoint /tmp/req.json /tmp/polyglot-out
```

## Demo target

`examples/c-satadd` — a tiny saturating-arithmetic C library with `make test`. The agent writes `rust-port/` (Cargo crate) beside the original C.

## Layout

```
backend/polyglot/     pipeline + FastAPI
frontend/             Next.js review UI
examples/c-satadd/    bundled C repo
eval/                 benchmark harness
docs/                 architecture + judging notes
```

License: MIT
