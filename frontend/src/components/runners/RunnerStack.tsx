"use client";

/**
 * Vertical list of active and recent runner jobs for the current session.
 *
 * Pulls state from {@link useRunnerEvents} (populated by the per-session SSE
 * subscription mounted in AppShell). Sorts active jobs first, then completed
 * jobs by most-recent-first. Each entry is a tool-specific card; for now
 * AlphaFold-style structure jobs use {@link AlphaFoldCard} and other tools
 * fall back to a generic status row.
 */
import { useMemo } from "react";

import { useRunnerEvents } from "@/lib/runner-events-context";
import type { RunnerJobState } from "@/lib/types";

import AlphaFoldCard from "./AlphaFoldCard";

const STRUCTURE_TOOLS = new Set(["alphafold2", "alphafold3", "boltz1", "boltz", "esmfold"]);
const ACTIVE_PHASES = new Set(["queued", "running", "downloading", "heartbeat"]);

function compareJobs(a: RunnerJobState, b: RunnerJobState): number {
  const aActive = ACTIVE_PHASES.has(a.latest.phase);
  const bActive = ACTIVE_PHASES.has(b.latest.phase);
  if (aActive !== bActive) return aActive ? -1 : 1;
  return b.latest.timestamp - a.latest.timestamp;
}

function GenericRunnerCard({ job }: { job: RunnerJobState }) {
  const phase = job.latest.phase;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs">
      <div className="flex items-center justify-between">
        <div className="font-mono text-slate-500">
          {job.tool} · {job.job_id}
        </div>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
          {phase}
        </span>
      </div>
      {job.latest.log_tail ? (
        <pre className="mt-2 whitespace-pre-wrap font-mono text-[11px] text-slate-600">
          {job.latest.log_tail}
        </pre>
      ) : null}
    </div>
  );
}

export default function RunnerStack() {
  const { jobs, connection, lastError } = useRunnerEvents();
  const sorted = useMemo(
    () => Array.from(jobs.values()).sort(compareJobs),
    [jobs]
  );

  if (connection === "idle" && sorted.length === 0) {
    return (
      <div className="px-2 py-6 text-center text-xs text-slate-500">
        No active runner jobs. Trigger an AlphaFold or Boltz run from the
        chat to see live progress here.
      </div>
    );
  }

  return (
    <div className="space-y-3 px-1 py-2">
      {connection === "error" ? (
        <div className="rounded border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-700">
          Lost connection to runner events
          {lastError ? `: ${lastError}` : ""}. New events may be missed until
          the page is refreshed.
        </div>
      ) : null}

      {sorted.length === 0 && connection !== "idle" ? (
        <div className="px-2 py-6 text-center text-xs text-slate-500">
          Connected. Waiting for runner events…
        </div>
      ) : null}

      {sorted.map((job) =>
        STRUCTURE_TOOLS.has(job.tool) ? (
          <AlphaFoldCard key={job.job_id} job={job} />
        ) : (
          <GenericRunnerCard key={job.job_id} job={job} />
        )
      )}
    </div>
  );
}
