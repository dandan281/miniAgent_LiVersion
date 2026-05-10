"use client";

/**
 * Live AlphaFold2 (or any structure-prediction runner) card.
 *
 * Shows: phase badge, elapsed time, ETA, and last log tail while the job is
 * running. When the job completes and the runner emits structure file paths
 * in its payload, lazy-loads the Mol* viewer below the status row.
 *
 * The card is generic over any tool that produces "phase + elapsed + payload
 * pointing to a PDB/CIF artifact". For now it's used by alphafold2; Boltz-1
 * and AF3 will plug in once those runners emit equivalent runner events.
 */
import { lazy, Suspense, useMemo } from "react";

import type { RunnerJobState } from "@/lib/types";

const StructureViewer = lazy(() => import("./StructureViewer"));

export interface AlphaFoldCardProps {
  job: RunnerJobState;
}

const PHASE_BADGE: Record<string, { label: string; cls: string }> = {
  queued: { label: "Queued", cls: "bg-slate-100 text-slate-600 ring-slate-200" },
  running: { label: "Running", cls: "bg-amber-50 text-amber-700 ring-amber-200" },
  downloading: {
    label: "Downloading",
    cls: "bg-blue-50 text-blue-700 ring-blue-200",
  },
  done: { label: "Done", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  failed: { label: "Failed", cls: "bg-rose-50 text-rose-700 ring-rose-200" },
  heartbeat: { label: "Running", cls: "bg-amber-50 text-amber-700 ring-amber-200" },
};

function formatDuration(seconds: number | undefined | null): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "—";
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m === 0) return `${s}s`;
  if (m < 60) return `${m}m ${s.toString().padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${(m % 60).toString().padStart(2, "0")}m`;
}

interface StructurePathInfo {
  rel: string;
  display: string;
}

/**
 * Resolve which file from the payload to render. AlphaFold2 jobs typically
 * emit a `structure_predictions_dir` plus a list of `files`; we prefer the
 * top-ranked PDB if one is named like `ranked_*` or `model_*`, otherwise the
 * first PDB or CIF in the list.
 */
function pickStructureFile(
  job: RunnerJobState
): StructurePathInfo | null {
  const payload = job.latest.payload;
  if (!payload) return null;
  const dir = payload.structure_predictions_dir;
  const files = payload.files;
  if (typeof dir !== "string" || !Array.isArray(files)) return null;

  const dirAsString = String(dir);
  const dirSegments = dirAsString.split("/").filter(Boolean);
  // The runner writes ``<repo>/artifacts/<tool>/<date>/<hash>/outputs/...``,
  // so the path relative to ``<repo>/artifacts/<tool>/`` starts after the
  // tool segment. We split by "/artifacts/<tool>/" and take the suffix.
  const marker = `/artifacts/${job.tool}/`;
  const idx = dirAsString.indexOf(marker);
  const dirRel =
    idx >= 0
      ? dirAsString.slice(idx + marker.length).replace(/\/$/, "")
      : dirSegments.slice(-2).join("/");

  const candidates = files
    .filter((f): f is string => typeof f === "string")
    .filter((f) => /\.(pdb|cif)$/i.test(f));
  if (candidates.length === 0) return null;

  // Prefer rank_1 / model_1 / unrelaxed_rank_1 if present.
  const ranked = candidates.find((f) =>
    /(^|\/)(ranked_0|rank_1|model_1|unrelaxed_rank_1)/i.test(f)
  );
  const chosen = ranked ?? candidates[0];

  return {
    rel: `${dirRel}/${chosen}`.replace(/\/+/g, "/"),
    display: chosen,
  };
}

export default function AlphaFoldCard({ job }: AlphaFoldCardProps) {
  const phase = job.latest.phase;
  const badge = PHASE_BADGE[phase] ?? {
    label: phase,
    cls: "bg-slate-100 text-slate-600 ring-slate-200",
  };
  const elapsed = formatDuration(job.latest.elapsed_s);
  const etaHint = job.latest.eta_s != null ? ` · ETA ≤ ${formatDuration(job.latest.eta_s)}` : "";
  const isTerminal = phase === "done" || phase === "failed";

  const structureFile = useMemo(
    () => (phase === "done" ? pickStructureFile(job) : null),
    [job, phase]
  );

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-xs font-mono text-slate-500">
            {job.tool} · job {job.job_id}
          </div>
          <div className="mt-0.5 text-sm font-medium text-slate-900">
            {phase === "done"
              ? "Structure prediction complete"
              : phase === "failed"
              ? "Job failed"
              : "Predicting structure"}
          </div>
        </div>
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${badge.cls}`}
        >
          {badge.label}
        </span>
      </div>

      <div className="text-xs text-slate-600">
        Elapsed {elapsed}
        {!isTerminal ? etaHint : ""}
      </div>

      {job.latest.log_tail ? (
        <pre className="whitespace-pre-wrap rounded border border-slate-100 bg-slate-50 p-2 text-[11px] font-mono text-slate-600">
          {job.latest.log_tail}
        </pre>
      ) : null}

      {phase === "done" && structureFile ? (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-[11px] text-slate-500">
            <span className="truncate font-mono">{structureFile.display}</span>
            <span>pLDDT-colored</span>
          </div>
          <Suspense
            fallback={
              <div className="flex h-[360px] items-center justify-center rounded-lg border border-slate-200 bg-slate-950 text-sm text-slate-300">
                Loading 3D viewer…
              </div>
            }
          >
            <StructureViewer
              tool={job.tool}
              path={structureFile.rel}
              pLDDTColoring
            />
          </Suspense>
        </div>
      ) : null}

      {phase === "done" && !structureFile ? (
        <div className="text-xs text-slate-500">
          Job complete, but no PDB/CIF file was found in the runner output. Check
          the run directory listed in the runner payload.
        </div>
      ) : null}
    </div>
  );
}
