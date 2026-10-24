export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type RunEvent = { type: string; ts: number; data: Record<string, any> };

export const EVENT_TYPES = [
  "run.started",
  "ingest.done",
  "setup.run",
  "baseline.done",
  "graph.built",
  "research.done",
  "plan.ready",
  "crate.scaffolded",
  "wave.started",
  "step.started",
  "file.migrated",
  "step.done",
  "step.flagged",
  "tests.run",
  "repair.applied",
  "run.error",
  "run.finished",
];

export async function startRun(body: {
  repo_url: string;
  ref: string;
  instruction: string;
  open_pr: boolean;
  target_language?: string;
}) {
  const r = await fetch(`${API}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_language: "rust", ...body }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()).run_id as string;
}

export const getDiff = async (id: string) =>
  ((await (await fetch(`${API}/runs/${id}/diff`)).json()).diff as string) ?? "";

export const getPairs = async (id: string) =>
  ((await (await fetch(`${API}/runs/${id}/pairs`)).json()).pairs as Pair[]) ?? [];

export const getHealth = async () => (await fetch(`${API}/health`)).json();

export const getDemo = async () => (await fetch(`${API}/demo`)).json() as Promise<{
  repo_url: string;
  ref: string;
  instruction: string;
}>;

export type RunSummary = {
  run_id: string;
  status: string;
  wall_seconds?: number;
  files_changed?: number;
  tests_passed?: number;
  tests_failed?: number;
  repair_iterations?: number;
  unsafe_blocks?: number;
  llm_calls?: number;
  pr_url?: string | null;
  tokens?: number;
  plan_summary?: string;
};

export const listRuns = async () => {
  const r = await fetch(`${API}/runs`);
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()).runs as RunSummary[];
};

export const fetchReport = async (id: string) => {
  const r = await fetch(`${API}/runs/${id}/report`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
};

export type Pair = {
  source_files: string[];
  source: string;
  target: string;
  rust: string;
};
