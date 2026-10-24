# Nebius × NVIDIA Global AI Hackathon — how this entry is meant to be judged

**Track:** Best Apps and Agents  
**Deadline:** 30 Oct 2026 10:00 PDT  
**Must-haves:** runtime call to Nebius Token Factory **and** at least one NVIDIA open model.

## Stage 1 (pass/fail)

A genuine C/C++ → Rust migration product that calls Token Factory at runtime. Not a rebranded chatbot.

## Stage 2 (1–5 each, equal weight)

1. **Technological Implementation** — `backend/polyglot/llm/client.py` hits `https://api.tokenfactory.nebius.com/v1`. Ultra / Super / Nano are separate settings. Optional Serverless Job: `python -m polyglot.jobs.entrypoint`.
2. **Design** — UI at `:3000` is a complete loop: start run, watch the agent, inspect C vs Rust, signatures, tokens, PR.
3. **Potential Impact** — Demo the bundled `examples/c-satadd` library: C tests, then a `rust-port` crate with `cargo test`.
4. **Quality of the Idea** — Multi-file DAG + test loop + revert policy, not a single completion.

## Bonus: Best Use of Tavily ($3,000)

`backend/polyglot/research/tavily.py` makes a **runtime** Tavily Search call and feeds mappings into the Ultra plan. Leave `TAVILY_API_KEY` set.

## Submission checklist

- [ ] Public GitHub repo, MIT `LICENSE` visible
- [ ] README names Nemotron models + Token Factory + Tavily + Jobs
- [ ] Working demo URL (or localhost recording)
- [ ] YouTube video ≤ 3 minutes showing Token Factory + a green `cargo test`
- [ ] Track = Best Apps and Agents
- [ ] Feedback form on Token Factory / Nemotron (Most Valuable Feedback prize)
- [ ] If the idea existed before the submission window, write what changed during it
