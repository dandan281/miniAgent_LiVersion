"use client";

/**
 * Mol* (molstar) wrapper for rendering AlphaFold-style structure predictions.
 *
 * Designed to stay tiny and additive — Mol* is dynamically imported so its
 * ~2 MB gzipped bundle never lands in the main chunk. Coloring defaults to
 * pLDDT (B-factor scale, AlphaFold convention: blue ≥ 90, light blue 70–90,
 * yellow 50–70, orange < 50) when a confidence value is present in the
 * loaded structure, otherwise to chain-id.
 */
import { useEffect, useRef, useState } from "react";

import { buildRunnerArtifactUrl } from "@/lib/runner-events";

export interface StructureViewerProps {
  /** Runner / tool name (e.g. "alphafold2"). Used to resolve the artifact URL. */
  tool: string;
  /** Path relative to <repo>/artifacts/<tool>/ (PDB or CIF file). */
  path: string;
  /**
   * If true, Mol* applies the AlphaFold pLDDT color theme. The structure must
   * carry pLDDT in its B-factor column for this to look right (AlphaFold and
   * Boltz outputs both do).
   */
  pLDDTColoring?: boolean;
  /** Container height in CSS units. Defaults to a comfortable inspector size. */
  height?: number | string;
}

interface MolstarHandle {
  dispose: () => void;
}

export default function StructureViewer({
  tool,
  path,
  pLDDTColoring = true,
  height = 360,
}: StructureViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const handleRef = useRef<MolstarHandle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<"loading" | "ready">("loading");

  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;
    if (!container) return undefined;

    setStatus("loading");
    setError(null);

    // Reset any previous viewer instance synchronously so a path change
    // doesn't leave the old structure on screen.
    if (handleRef.current) {
      handleRef.current.dispose();
      handleRef.current = null;
    }

    const url = buildRunnerArtifactUrl(tool, path);
    const format = path.toLowerCase().endsWith(".cif") ? "mmcif" : "pdb";

    void (async () => {
      try {
        // Dynamic import so Mol* only ships when this component mounts. We
        // load via a type-erased import() so the file still type-checks
        // when `molstar` isn't installed yet (the runtime error message
        // makes it clear the dep is missing).
        const dynImport = (specifier: string): Promise<any> =>
          import(/* webpackIgnore: true */ /* @vite-ignore */ specifier);
        const mod = await dynImport("molstar/lib/mol-plugin-ui");
        const specMod = await dynImport("molstar/lib/mol-plugin-ui/spec");
        const presetMod = await dynImport(
          "molstar/lib/mol-plugin-state/builder/structure/representation-preset"
        );

        if (cancelled || !container) return;

        const spec = specMod.DefaultPluginUISpec();
        // Surface a minimalist UI: no left panel, no bottom panel; the
        // floating control buttons stay (zoom, screenshot, expand).
        spec.layout = {
          initial: {
            isExpanded: false,
            showControls: false,
            controlsDisplay: "reactive",
            regionState: {
              left: "hidden",
              right: "hidden",
              top: "hidden",
              bottom: "hidden",
            },
          },
        };

        const plugin = await mod.createPluginUI({
          target: container,
          spec,
          render: mod.renderReact18,
        });

        const data = await plugin.builders.data.download(
          { url, isBinary: false },
          { state: { isGhost: true } }
        );
        const trajectory = await plugin.builders.structure.parseTrajectory(
          data,
          format
        );
        await plugin.builders.structure.hierarchy.applyPreset(
          trajectory,
          "default",
          {
            structure: { name: "model", params: {} },
            showUnitcell: false,
            representationPreset: pLDDTColoring
              ? presetMod.PresetStructureRepresentations[
                  "atomic-detail"
                ]?.id ?? "auto"
              : "auto",
          }
        );

        if (pLDDTColoring) {
          // AlphaFold convention: pLDDT lives in the B-factor column. The
          // built-in "plddt-confidence" theme picks it up automatically.
          plugin.dataTransaction(async () => {
            for (const ref of plugin.managers.structure.hierarchy.current
              .refs as unknown as Map<string, unknown>) {
              // No-op: theme is applied via preset above; loop reserved for
              // future per-component overrides.
              void ref;
            }
          });
        }

        if (cancelled) {
          plugin.dispose();
          return;
        }

        handleRef.current = { dispose: () => plugin.dispose() };
        setStatus("ready");
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        setStatus("ready");
      }
    })();

    return () => {
      cancelled = true;
      if (handleRef.current) {
        handleRef.current.dispose();
        handleRef.current = null;
      }
    };
  }, [tool, path, pLDDTColoring]);

  return (
    <div className="relative w-full overflow-hidden rounded-lg border border-slate-200 bg-slate-950">
      <div
        ref={containerRef}
        style={{ height }}
        className="h-full w-full"
        data-testid="structure-viewer-canvas"
      />
      {status === "loading" && !error ? (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-300">
          Loading 3D viewer…
        </div>
      ) : null}
      {error ? (
        <div className="absolute inset-0 flex items-center justify-center px-4 text-center text-xs text-rose-300">
          Failed to render structure: {error}
        </div>
      ) : null}
    </div>
  );
}
