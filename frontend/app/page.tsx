"use client";
import {  useCallback, useEffect, useRef, useState } from "react";
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

/* ------------------------------------------------------------------ types */
type Row = { text: string; detail?: string; tone: "" | "ok" | "bad" | "warn" };
type Project = { id: string; name: string; repo: string; ref: string; instruction: string };

const DEFAULT_INSTRUCTION =
  "Migrate this C library to safe idiomatic Rust. Preserve overflow semantics. Emit cargo tests.";

const STAGES = ["Ingest", "Analyze", "Plan", "Translate", "Verify", "Deliver"] as const;
const STAGE_OF: Record<string, number> = {
  "ingest.done": 0,
  "baseline.done": 0,
  "graph.built": 1,
  "research.done": 1,
  "plan.ready": 2,
  "crate.scaffolded": 2,
  "step.started": 3,
  "step.done": 3,
  "step.flagged": 3,
  "tests.run": 4,
  "repair.applied": 4,
  "run.finished": 5,
};

/* ---------------------------------------------------------------- helpers */
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
        detail: d.verified ? `${(d.sources || []).length} docs` : "no docs, using model knowledge",
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

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}
function save(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
}

function shortRepo(repo: string): string {
  const gh = repo.replace(/^https?:\/\/(www\.)?github\.com\//, "").replace(/\.git$/, "");
  if (gh !== repo) return gh;
  return repo.split("/").filter(Boolean).slice(-2).join("/") || repo;
}

function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}m ${String(Math.floor(s % 60)).padStart(2, "0")}s` : `${s.toFixed(0)}s`;
}

function useCountUp(target: number, ms = 700) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (!Number.isFinite(target)) { setV(0); return; }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setV(target); return; }
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / ms);
      setV(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

/* ------------------------------------------------------------- small bits */
const Icon = {
  chevron: (
    <svg className="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="m15 18-6-6 6-6" /></svg>
  ),
  plus: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden><path d="M12 5v14M5 12h14" /></svg>
  ),
  menu: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M4 6h16M4 12h16M4 18h16" /></svg>
  ),
  check: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="m5 12 5 5 9-10" /></svg>
  ),
};

function Count({ value }: { value: number | null | undefined }) {
  const n = useCountUp(typeof value === "number" ? value : 0);
  return <>{typeof value === "number" ? n.toLocaleString() : "–"}</>;
}

function Stat({ label, value, hot }: { label: string; value: number | null | undefined; hot?: boolean }) {
  return (
    <div className={`stat${hot ? " hot" : ""}`}>
      <b><Count value={value} /></b>
      <span>{label}</span>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="copy"
      onClick={async () => {
        try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1400); } catch {}
      }}
    >
      {done ? "copied" : "copy"}
    </button>
  );
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

/* ------------------------------------------------------------------- page */
export default function Home() {
  // run form
  const [repo, setRepo] = useState("");
  const [ref, setRef] = useState("main");
  const [instruction, setInstruction] = useState(DEFAULT_INSTRUCTION);
  const [openPr, setOpenPr] = useState(false);
  // run state
  const [rows, setRows] = useState<Row[]>([]);
  const [report, setReport] = useState<any>(null);
  const [diff, setDiff] = useState("");
  const [pairs, setPairs] = useState<Pair[]>([]);
  const [activePair, setActivePair] = useState(0);
  const [waves, setWaves] = useState<any[][]>([]);
  const [tab, setTab] = useState<"pairs" | "diff" | "sigs">("pairs");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [health, setHealth] = useState<any>(null);
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [pastRunId, setPastRunId] = useState<string | null>(null);
  const [stage, setStage] = useState(-1);
  const [failed, setFailed] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  // sidebar + projects
  const [collapsed, setCollapsed] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<string | null>(null);
  const [runProject, setRunProject] = useState<Record<string, string>>({});
  const [scope, setScope] = useState<"all" | "project">("all");
  const [showNew, setShowNew] = useState(false);
  const [draft, setDraft] = useState({ name: "", repo: "", ref: "main" });

  const es = useRef<EventSource | null>(null);
  const startedAt = useRef(0);
  const timelineRef = useRef<HTMLOListElement | null>(null);

  const loadHistory = useCallback(async () => {
    try { setHistory(await listRuns()); } catch { setHistory([]); }
  }, []);

  /* initial load */
  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth({ ok: false }));
    loadHistory();
    const saved = localStorage.getItem("pg.sidebar");
    setCollapsed(saved ? saved === "1" : window.innerWidth < 860);
    setProjects(load<Project[]>("pg.projects", []));
    setRunProject(load<Record<string, string>>("pg.runProject", {}));
    setActiveProject(load<string | null>("pg.activeProject", null));
  }, [loadHistory]);

  /* elapsed timer while a run is live */
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setElapsed((Date.now() - startedAt.current) / 1000), 500);
    return () => clearInterval(t);
  }, [busy]);

  /* keep the live timeline scrolled to the newest event */
  useEffect(() => {
    const el = timelineRef.current;
    if (el && busy) el.scrollTop = el.scrollHeight;
  }, [rows, busy]);

  /* keyboard: [ toggles sidebar, Esc closes the dialog */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (e.key === "Escape") setShowNew(false);
      if (e.key === "[" && tag !== "INPUT" && tag !== "TEXTAREA") toggleSidebar();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function toggleSidebar() {
    setCollapsed((c) => {
      localStorage.setItem("pg.sidebar", c ? "0" : "1");
      return !c;
    });
  }

  /* projects */
  function createProject(e: React.FormEvent) {
    e.preventDefault();
    const p: Project = {
      id: Math.random().toString(36).slice(2, 10),
      name: draft.name.trim() || "Untitled project",
      repo: draft.repo.trim(),
      ref: draft.ref.trim() || "main",
      instruction,
    };
    const next = [p, ...projects];
    setProjects(next);
    save("pg.projects", next);
    selectProject(p);
    setDraft({ name: "", repo: "", ref: "main" });
    setShowNew(false);
  }

  function selectProject(p: Project) {
    setActiveProject(p.id);
    save("pg.activeProject", p.id);
    setRepo(p.repo);
    setRef(p.ref);
    setInstruction(p.instruction || DEFAULT_INSTRUCTION);
    setScope("project");
  }

  function removeProject(id: string) {
    const next = projects.filter((p) => p.id !== id);
    setProjects(next);
    save("pg.projects", next);
    if (activeProject === id) { setActiveProject(null); save("pg.activeProject", null); setScope("all"); }
  }

  function updateProject() {
    const next = projects.map((p) => (p.id === activeProject ? { ...p, repo, ref, instruction } : p));
    setProjects(next);
    save("pg.projects", next);
  }

  /* runs */
  async function useExample() {
    try {
      const d = await getDemo();
      setRepo(d.repo_url);
      setRef(d.ref);
      setInstruction(d.instruction);
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function loadPastRun(id: string) {
    setPastRunId(id);
    setBusy(true);
    try {
      const r = await fetchReport(id);
      setReport(r);
      setRows([]); setDiff(""); setPairs([]); setWaves([]); setError("");
      setStage(5);
      setFailed(r?.status === "failed");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function go(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true);
    setRows([]); setReport(null); setDiff(""); setPairs([]); setWaves([]);
    setPastRunId(null); setError(""); setStage(-1); setFailed(false); setActivePair(0);
    startedAt.current = Date.now();
    setElapsed(0);
    try {
      const id = await startRun({ repo_url: repo, ref, instruction, open_pr: openPr });
      if (activeProject) {
        const map = { ...runProject, [id]: activeProject };
        setRunProject(map);
        save("pg.runProject", map);
      }
      loadHistory();
      const src = new EventSource(`${API}/runs/${id}/events`);
      es.current = src;
      EVENT_TYPES.forEach((t) =>
        src.addEventListener(t, async (m) => {
          const e: RunEvent = JSON.parse((m as MessageEvent).data);
          const row = describe(e);
          if (row) setRows((r) => [...r, row]);
          const s = STAGE_OF[t];
          if (s !== undefined) setStage((prev) => Math.max(prev, s));
          if (t === "run.error") setFailed(true);
          if (t === "plan.ready") setWaves(e.data.waves || []);
          if (t === "run.finished") {
            src.close();
            setReport(e.data.report);
            setFailed(e.data.report?.status === "failed");
            setBusy(false);
            try { setDiff(await getDiff(id)); } catch {}
            try { setPairs(await getPairs(id)); } catch {}
            loadHistory();
          }
        })
      );
      src.onerror = () => { src.close(); setBusy(false); };
    } catch (err: any) {
      setError(err.message);
      setBusy(false);
    }
  }

  /* derived */
  const active = projects.find((p) => p.id === activeProject) || null;
  const visibleHistory =
    scope === "project" && activeProject ? history.filter((h) => runProject[h.run_id] === activeProject) : history;
  const showStepper = stage >= 0 || busy;
  const pair = pairs[Math.min(activePair, Math.max(pairs.length - 1, 0))];

  return (
    <div className="app">
      {/* ------------------------------------------------------- sidebar */}
      <aside className={`sidebar${collapsed ? " collapsed" : ""}`} aria-label="Projects and history">
        <div className="sb-head">
          <div className="logo">
            <span className="logo-mark" aria-hidden>PG</span>
            <span className="logo-text">PolyGlot<small>Refactor AI</small></span>
          </div>
          <button
            type="button"
            className="icon-btn"
            onClick={toggleSidebar}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
            title="Toggle sidebar  ["
          >
            {Icon.chevron}
          </button>
        </div>

        <button type="button" className="new-project" onClick={() => setShowNew(true)} title="New project">
          {Icon.plus}<span>New project</span>
        </button>

        <div className="sb-section">
          <div className="sb-label"><span>Projects</span></div>
          {projects.length === 0 && <p className="sb-empty">No projects yet. Create one to save a repo and its settings.</p>}
          {projects.map((p) => (
            <div key={p.id} className={`sb-item${p.id === activeProject ? " on" : ""}`}>
              <button type="button" className="sb-main" onClick={() => selectProject(p)} title={p.name}>
                <span className="avatar">{p.name.slice(0, 2).toUpperCase()}</span>
                <span className="sb-text"><b>{p.name}</b><small>{shortRepo(p.repo) || "no repo yet"}</small></span>
              </button>
              <button type="button" className="sb-x" onClick={() => removeProject(p.id)} aria-label={`Delete project ${p.name}`}>×</button>
            </div>
          ))}
        </div>

        <div className="sb-section grow">
          <div className="sb-label">
            <span>History</span>
            <button type="button" onClick={loadHistory}>refresh</button>
          </div>
          {active && (
            <div className="scope" role="group" aria-label="History filter">
              <button type="button" className={scope === "all" ? "on" : ""} onClick={() => setScope("all")}>All</button>
              <button type="button" className={scope === "project" ? "on" : ""} onClick={() => setScope("project")}>{active.name}</button>
            </div>
          )}
          {visibleHistory.length === 0 && <p className="sb-empty">No past migrations yet</p>}
          {visibleHistory.map((h) => (
            <button
              key={h.run_id}
              type="button"
              className={`run${pastRunId === h.run_id ? " on" : ""}`}
              onClick={() => loadPastRun(h.run_id)}
              title={`${h.run_id} · ${h.status}`}
            >
              <span className={`dot ${h.status}`} />
              <span className="sb-text">
                <b>{h.run_id}</b>
                <small>
                  {h.files_changed} files · {h.tests_passed ?? "–"}/{(h.tests_passed ?? 0) + (h.tests_failed ?? 0) || "–"} tests · {h.repair_iterations ?? 0} repairs
                </small>
              </span>
            </button>
          ))}
        </div>

        <div className="sb-foot">press <kbd>[</kbd> to toggle</div>
      </aside>
      {!collapsed && <div className="backdrop" onClick={toggleSidebar} aria-hidden />}

      {/* ----------------------------------------------------------- main */}
      <div className="main">
        <div className="shell">
          <div className="topbar">
            <div className="crumbs">
              <button type="button" className="icon-btn menu-btn" onClick={toggleSidebar} aria-label="Open sidebar">{Icon.menu}</button>
              <span>project</span>/<b>{active ? active.name : "untitled"}</b>
            </div>
            <span className={`pill${health?.ok ? " ok" : ""}`}><i />API {health?.ok ? "online" : "offline"}</span>
          </div>

          <header className="hero">
            <div>
              <p className="kicker">C → Rust · memory-safe migration</p>
              <h1>Autonomous <em>C → Rust</em> migration</h1>
              <p className="sub">
                Point it at a C repository. Nemotron Ultra plans the include DAG, Super and Nano rewrite
                translation units in parallel, cargo test loops until green, and you get a reviewable Rust
                crate, side by side with the C it came from.
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
            <button className="go" disabled={busy} type="submit">
              {busy ? <><span className="spin" />Migrating…</> : "Start C → Rust"}
            </button>
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
            {" · "}<button type="button" className="link-btn" onClick={useExample}>Load bundled satadd example</button>
            {active && <>{" · "}<button type="button" className="link-btn" onClick={updateProject}>Save settings to “{active.name}”</button></>}
          </p>

          {error && <p className="alert" role="alert">Could not start: {error}</p>}

          {pastRunId && (
            <div className="notice">
              <span>Viewing saved run <b>{pastRunId}</b>. Code views are only available for live runs.</span>
              <button type="button" className="ghost-btn" onClick={() => { setPastRunId(null); setReport(null); setStage(-1); }}>Close</button>
            </div>
          )}

          {showStepper && (
            <ol className="stepper" aria-label="Pipeline progress">
              {STAGES.map((name, i) => {
                const st = i < stage ? "done" : i === stage ? (busy ? "active" : failed ? "bad" : "done") : "todo";
                return (
                  <li key={name} className={st}>
                    <span className="node">{st === "done" ? Icon.check : i + 1}</span>
                    {name}
                  </li>
                );
              })}
            </ol>
          )}

          {report && !busy && (
            <div className={`banner ${report.status}`} role="status">
              <span className={`badge ${report.status}`}>{report.status}</span>
              <span>
                {report.status === "success" && "Migration complete. The Rust crate builds and its tests are green."}
                {report.status === "partial" && "Partly migrated. Some steps were flagged for a human to review."}
                {report.status === "failed" && "Migration did not finish cleanly. Check the live agent log below."}
              </span>
              {report.pr_url && <a href={report.pr_url} target="_blank" rel="noreferrer">Open pull request →</a>}
            </div>
          )}

          {report && (
            <div className="stats" aria-label="Run summary">
              <Stat label="files changed" value={report.files_changed} />
              <Stat label="rust tests passing" value={report.tests_after?.passed} hot />
              <Stat label="repair rounds" value={report.repair_iterations} />
              <Stat label="unsafe mentions" value={report.unsafe_blocks} />
              <Stat label="tokens" value={(report.prompt_tokens ?? 0) + (report.completion_tokens ?? 0)} />
              <Stat label="Nemotron calls" value={report.llm_calls} />
              <div className="stat"><b>{fmtTime(report.wall_seconds ?? 0)}</b><span>wall time</span></div>
            </div>
          )}

          {waves.length > 0 && (
            <div className="panel" style={{ marginTop: 16 }}>
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
                <div className="panel-head">
                  <p className="kicker">Live agent</p>
                  {(busy || elapsed > 0) && <span className="timer">{fmtTime(elapsed)}</span>}
                </div>
                <ol className="timeline" aria-live="polite" ref={timelineRef}>
                  {rows.map((r, i) => (
                    <li key={i} className={r.tone}>{r.text}{r.detail && <small>{r.detail}</small>}</li>
                  ))}
                  {busy && <li className="live">working…</li>}
                </ol>
              </section>

              <section className="panel">
                <div className="tabs" role="tablist">
                  <button role="tab" aria-selected={tab === "pairs"} className={tab === "pairs" ? "on" : ""} onClick={() => setTab("pairs")}>C vs Rust</button>
                  <button role="tab" aria-selected={tab === "diff"} className={tab === "diff" ? "on" : ""} onClick={() => setTab("diff")}>Git diff</button>
                  <button role="tab" aria-selected={tab === "sigs"} className={tab === "sigs" ? "on" : ""} onClick={() => setTab("sigs")}>Signatures</button>
                </div>

                {tab === "diff" && (diff ? <Diff text={diff} /> : <p className="sub">Diff appears when the run finishes.</p>)}

                {tab === "pairs" && (
                  pairs.length === 0 ? <p className="sub">Pairs appear when the run finishes.</p> : (
                    <>
                      {pairs.length > 1 && (
                        <div className="filechips">
                          {pairs.map((p, i) => (
                            <button key={p.target} type="button" className={i === activePair ? "on" : ""} onClick={() => setActivePair(i)}>
                              {p.target}
                            </button>
                          ))}
                        </div>
                      )}
                      {pair && (
                        <div className="split">
                          <div>
                            <div className="codehead">
                              <span>{pair.source_files.join(", ")}</span>
                              <span style={{ display: "flex", gap: 6 }}><CopyButton text={pair.source} /><span className="lang">C</span></span>
                            </div>
                            <pre className="code">{pair.source}</pre>
                          </div>
                          <div>
                            <div className="codehead">
                              <span>{pair.target}</span>
                              <span style={{ display: "flex", gap: 6 }}><CopyButton text={pair.rust || ""} /><span className="lang rust">Rust</span></span>
                            </div>
                            <pre className="code">{pair.rust || "// not generated"}</pre>
                          </div>
                        </div>
                      )}
                    </>
                  )
                )}

                {tab === "sigs" && (
                  <table className="sig">
                    <thead><tr><th>C</th><th>Rust</th><th>Module</th></tr></thead>
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
        </div>
      </div>

      {/* --------------------------------------------------- new project */}
      {showNew && (
        <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) setShowNew(false); }}>
          <form className="modal" onSubmit={createProject} role="dialog" aria-modal="true" aria-labelledby="np-title">
            <h2 id="np-title">New project</h2>
            <p>Save a C repository and its settings so you can rerun and compare migrations later. Projects are stored in this browser.</p>
            <label>Project name
              <input type="text" autoFocus required value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="libsatadd" />
            </label>
            <label>Repository URL or local path
              <input type="text" value={draft.repo} onChange={(e) => setDraft({ ...draft, repo: e.target.value })} placeholder="https://github.com/owner/repo" />
            </label>
            <label>Branch
              <input type="text" value={draft.ref} onChange={(e) => setDraft({ ...draft, ref: e.target.value })} placeholder="main" />
            </label>
            <div className="modal-actions">
              <button type="button" className="ghost-btn" onClick={() => setShowNew(false)}>Cancel</button>
              <button type="submit" className="go">Create project</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

