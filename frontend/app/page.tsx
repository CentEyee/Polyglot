"use client";
import { useEffect, useRef, useState } from "react";
import {
  API,
  EVENT_TYPES,
  Pair,
  RunEvent,
  RunSummary,
  getDemo,
  getDiff,
  getHealth,
  getPairs,
  listRuns,
  fetchReport,
  startRun,
} from "../lib/api";

type Row = { text: string; detail?: string; tone: "" | "ok" | "bad" | "warn" };

function describe(e: RunEvent): Row | null {
  const d = e.data;
  switch (e.type) {
    case "ingest.done":
      return { text: `Cloned ${d.language} → ${d.target}`, detail: `${d.files} files · ${String(d.sha).slice(0, 8)}`, tone: "ok" };
    case "baseline.done":
      return { text: `C baseline: ${d.passed} passed / ${d.failed} failed`, tone: d.ok ? "ok" : "warn" };
    case "graph.built":
      return { text: `Include graph: ${d.files} units, ${d.edges} edges`, tone: "" };
    case "research.done":
      return {
        text: `Tavily mappings: ${d.breaking_changes}`,
        detail: d.verified ? `${(d.sources || []).length} docs` : "no docs — using model knowledge",
        tone: d.verified ? "ok" : "warn",
      };
    case "plan.ready":
      return { text: `Ultra plan: ${d.waves?.length || 0} wave(s)`, detail: d.summary, tone: "ok" };
    case "crate.scaffolded":
      return { text: "Scaffolded rust-port crate", tone: "ok" };
    case "step.started":
      return { text: d.title, detail: `${(d.files || []).length} file(s) · ${d.risk} risk`, tone: "" };
    case "step.done":
      return { text: "Step committed", detail: String(d.commit ?? "").slice(0, 8), tone: "ok" };
    case "step.flagged":
      return { text: `Needs a human: ${d.step}`, detail: (d.reason ?? []).join("; "), tone: "warn" };
    case "tests.run":
      return {
        text: `cargo test: ${d.passed} passed, ${d.failed + d.errors} failing`,
        detail: (d.new_failures || []).length ? `${d.new_failures.length} to repair` : "clean",
        tone: (d.new_failures || []).length ? "bad" : "ok",
      };
    case "repair.applied":
      return { text: `Repaired ${d.path}`, detail: `${d.tier} · round ${d.iteration}`, tone: "warn" };
    case "run.error":
      return { text: "Run failed", detail: d.error, tone: "bad" };
    default:
      return null;
  }
}

function Diff({ text }: { text: string }) {
  return (
    <pre className="diff">
      {text.split("\n").map((l, i) => {
        const c =
          l.startsWith("diff --git") ? "f" :
          l.startsWith("@@") ? "h" :
          l.startsWith("+") && !l.startsWith("+++") ? "a" :
          l.startsWith("-") && !l.startsWith("---") ? "d" : "";
        return <div key={i} className={c}>{l || " "}</div>;
      })}
    </pre>
  );
}

export default function Home() {
  const [repo, setRepo] = useState("");
  const [ref, setRef] = useState("main");
  const [instruction, setInstruction] = useState(
    "Migrate this C/C++ library to safe idiomatic Rust. Preserve overflow semantics. Emit cargo tests."
  );
  const [openPr, setOpenPr] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);
  const [report, setReport] = useState<any>(null);
  const [diff, setDiff] = useState("");
  const [pairs, setPairs] = useState<Pair[]>([]);
  const [waves, setWaves] = useState<any[][]>([]);
  const [tab, setTab] = useState<"pairs" | "diff" | "sigs">("pairs");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [health, setHealth] = useState<any>(null);
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [pastRunId, setPastRunId] = useState<string | null>(null);
  const es = useRef<EventSource | null>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth({ ok: false }));
    listRuns().then(setHistory).catch(() => setHistory([]));
  }, []);

  async function useExample() {
    const d = await getDemo();
    setRepo(d.repo_url);
    setRef(d.ref);
    setInstruction(d.instruction);
  }

  async function loadHistory() {
    try {
      setHistory(await listRuns());
    } catch {
      setHistory([]);
    }
  }

  async function loadPastRun(id: string) {
    setPastRunId(id);
    setBusy(true);
    try {
      const r = await fetchReport(id);
      setReport(r);
      setDiff("");
      setPairs([]);
      setWaves([]);
      setError("");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function go(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true);
    setRows([]);
    setReport(null);
    setDiff("");
    setPairs([]);
    setWaves([]);
    setPastRunId(null);
    setError("");
    try {
      const id = await startRun({ repo_url: repo, ref, instruction, open_pr: openPr });
      const src = new EventSource(`${API}/runs/${id}/events`);
      es.current = src;
      EVENT_TYPES.forEach((t) =>
        src.addEventListener(t, async (m) => {
          const e: RunEvent = JSON.parse((m as MessageEvent).data);
          const row = describe(e);
          if (row) setRows((r) => [...r, row]);
          if (t === "plan.ready") setWaves(e.data.waves || []);
          if (t === "run.finished") {
            src.close();
            setReport(e.data.report);
            setBusy(false);
            try { setDiff(await getDiff(id)); } catch {}
            try { setPairs(await getPairs(id)); } catch {}
          }
        })
      );
      src.onerror = () => { src.close(); setBusy(false); };
    } catch (err: any) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div>
      {/* Sidebar for past migrations */}
      <aside className="sidebar">
        <div className="sidebar-title">Migration History</div>
        {history.length === 0 ? (
          <div className="sidebar-empty">No past migrations yet</div>
        ) : (
          history.map((h) => (
            <div
              key={h.run_id}
              className="sidebar-run"
              onClick={() => loadPastRun(h.run_id)}
              role="button"
              tabIndex={0}
            >
              <div className="sidebar-run-id">{h.run_id}</div>
              <div className="sidebar-run-status"><span>{h.status}</span></div>
              <div className="sidebar-run-details">
                {h.files_changed} files · {h.tests_passed ?? "–"} passed / {h.tests_failed ?? "–"} failed · {h.repair_iterations ?? 0} repairs
              </div>
            </div>
          ))
        )}
      </aside>

      <main className="shell">
        <header className="hero">
          <div>
            <p className="brand-text">
              <span>PolyGlot Refactor AI</span>
            </p>
            <h1>Autonomous C/C++ → Rust Migration</h1>
            <p className="sub">
              Point it at a C/C++ repository. Nemotron Ultra plans the include DAG,
              Super/Nano rewrite translation units in parallel, cargo test loops until
              green, and you get a reviewable Rust crate — side-by-side with the C it came from.
            </p>
          </div>
          <div className="chips">
            <span className="chip"><b>Ultra</b> plans</span>
            <span className="chip"><b>Super</b> rewrites</span>
            <span className="chip"><b>Nano</b> low-risk</span>
            <span className="chip"><b>Tavily</b> mappings</span>
            <span className="chip"><b>Jobs</b> sandbox</span>
          </div>
        </header>

        <form className="panel" onSubmit={go}>
          <label>Repository URL or local path
            <input type="text" required value={repo} onChange={(e) => setRepo(e.target.value)}
              placeholder="https://github.com/owner/repo  or  /path/to/examples/c-satadd" />
          </label>
          <label>Branch
            <input type="text" value={ref} onChange={(e) => setRef(e.target.value)} placeholder="main" />
          </label>
          <button className="go" disabled={busy} type="submit">{busy ? "Migrating…" : "Start C → Rust"}</button>
          <label className="wide">Migration instruction
            <textarea rows={2} required value={instruction} onChange={(e) => setInstruction(e.target.value)} />
          </label>
          <label className="check wide">
            <input type="checkbox" checked={openPr} onChange={(e) => setOpenPr(e.target.checked)} />
            Open a GitHub pull request when cargo test is clean (needs GITHUB_TOKEN)
          </label>
        </form>

        <p className={health?.ok && health?.token_factory ? "health ok" : "health"}>
          API {health?.ok ? "up" : "down"} · Token Factory {health?.token_factory ? "key loaded" : "missing NEBIUS_API_KEY"} ·
          Tavily {health?.tavily ? "on" : "off"} · GitHub {health?.github ? "on" : "off"}
          {" · "}<button type="button" onClick={useExample} style={{ background: "none", border: 0, color: "var(--nvidia-green)", cursor: "pointer", padding: 0 }}>Load bundled satadd example</button>
        </p>

        {history.length > 0 && (
          <section className="panel" style={{ marginTop: 16, marginBottom: 16 }}>
            <div
              style={{
                display: "flex",
                gap: 10,
                alignItems: "center",
                marginBottom: 8,
                flexWrap: "wrap",
              }}
            >
              <p className="kicker" style={{ margin: 0 }}>
                Past migrations
              </p>
              <button
                type="button"
                onClick={loadHistory}
                style={{
                  background: "transparent",
                  border: "1px solid var(--line)",
                  color: "var(--muted)",
                  borderRadius: 6,
                  padding: "4px 10px",
                  fontSize: 12,
                  cursor: "pointer",
                }}
              >
                Refresh
              </button>
            </div>
            <div style={{ display: "grid", gap: 6 }}>
              {history.map((h) => (
                <div
                  key={h.run_id}
                  className="history-row"
                  onClick={() => loadPastRun(h.run_id)}
                  role="button"
                  tabIndex={0}
                >
                  <div
                    style={{
                      display: "flex",
                      gap: 8,
                      alignItems: "center",
                      flexWrap: "wrap",
                    }}
                  >
                    <span className="mono">{h.run_id}</span>
                    <span className={`badge ${h.status}`}>{h.status}</span>
                    {h.pr_url && (
                      <a
                        href={h.pr_url}
                        target="_blank"
                        rel="noreferrer"
                        style={{
                          color: "var(--nvidia-green)",
                          fontSize: 11,
                          marginLeft: 6,
                        }}
                      >
                        PR →
                      </a>
                    )}
                  </div>
                  <div
                    className="muted"
                    style={{ color: "var(--muted)", fontSize: 11, marginTop: 4 }}
                  >
                    {h.files_changed} files ·
                    {h.tests_passed ?? "–"} passed / {h.tests_failed ?? "–"} failed ·
                    {h.repair_iterations ?? 0} repairs ·
                    {Math.round(h.wall_seconds ?? 0)}s ·
                    {h.tokens?.toLocaleString() ?? "–"} tokens
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {error && <p className="alert" role="alert">Could not start: {error}</p>}

        {report && (
          <div className="stats" aria-label="Run summary">
            <div className="stat"><b><span className={`badge ${report.status}`}>{report.status}</span></b><span>result</span></div>
            <div className="stat"><b>{report.files_changed}</b><span>files changed</span></div>
            <div className="stat"><b>{report.tests_after?.passed ?? "–"}</b><span>rust tests passing</span></div>
            <div className="stat"><b>{report.repair_iterations}</b><span>repair rounds</span></div>
            <div className="stat"><b>{report.unsafe_blocks}</b><span>unsafe mentions</span></div>
            <div className="stat"><b>{(report.prompt_tokens + report.completion_tokens).toLocaleString()}</b><span>tokens</span></div>
            <div className="stat"><b>{Math.round(report.wall_seconds)}s</b><span>wall time</span></div>
            <div className="stat"><b>{report.llm_calls}</b><span>Nemotron calls</span></div>
          </div>
        )}

        {waves.length > 0 && (
          <div className="panel" style={{ marginTop: 12 }}>
            <p className="kicker">Transformation DAG</p>
            <div className="waves">
              {waves.map((w, i) => (
                <div className="wave" key={i}>
                  <strong>wave {i + 1}</strong>
                  <span>{w.map((s: any) => s.title).join(" · ")}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {(rows.length > 0 || diff || pairs.length > 0) && (
          <div className="layout">
            <section className="panel">
              <p className="kicker">Live agent</p>
              <ol className="timeline" aria-live="polite">
                {rows.map((r, i) => (
                  <li key={i} className={r.tone}>{r.text}{r.detail && <small>{r.detail}</small>}</li>
                ))}
                {busy && <li>working…</li>}
              </ol>
              {report?.pr_url && <p><a href={report.pr_url}>Open pull request →</a></p>}
            </section>
            <section className="panel">
              <div className="tabs">
                <button className={tab === "pairs" ? "on" : ""} onClick={() => setTab("pairs")}>C vs Rust</button>
                <button className={tab === "diff" ? "on" : ""} onClick={() => setTab("diff")}>Git diff</button>
                <button className={tab === "sigs" ? "on" : ""} onClick={() => setTab("sigs")}>Signatures</button>
              </div>
              {tab === "diff" && (diff ? <Diff text={diff} /> : <p className="sub">Diff appears when the run finishes.</p>)}
              {tab === "pairs" && (
                pairs.length === 0 ? <p className="sub">Pairs appear when the run finishes.</p> :
                pairs.map((p) => (
                  <div key={p.target} style={{ marginBottom: 16 }}>
                    <div className="split">
                      <div>
                        <div className="codehead"><span>{p.source_files.join(", ")}</span><span>C/C++</span></div>
                        <pre className="code">{p.source}</pre>
                      </div>
                      <div>
                        <div className="codehead"><span>{p.target}</span><span>Rust</span></div>
                        <pre className="code">{p.rust || "// not generated"}</pre>
                      </div>
                    </div>
                  </div>
                ))
              )}
              {tab === "sigs" && (
                <table className="sig">
                  <thead><tr><th>C/C++</th><th>Rust</th><th>Module</th></tr></thead>
                  <tbody>
                    {(report?.signatures || []).map((s: any, i: number) => (
                      <tr key={i}><td>{s.source_sig}</td><td>{s.target_sig}</td><td>{s.target_file}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
