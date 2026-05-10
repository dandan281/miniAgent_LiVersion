"use client";

import { type ReactNode, useCallback, useState } from "react";
import { AppProvider, useApp } from "@/lib/store";
import { RunnerEventsProvider } from "@/lib/runner-events-context";
import InspectorPanel from "@/components/editor/InspectorPanel";
import Navbar from "@/components/layout/Navbar";
import ResizeHandle from "@/components/layout/ResizeHandle";
import Sidebar from "@/components/layout/Sidebar";
import WorkspacePanel from "@/components/layout/WorkspacePanel";

function RunnerEventsBridge({ children }: { children: ReactNode }) {
  const { currentSessionId } = useApp();
  return (
    <RunnerEventsProvider sessionId={currentSessionId}>{children}</RunnerEventsProvider>
  );
}

const SIDEBAR_MIN = 232;
const SIDEBAR_MAX = 296;
const INSPECTOR_MIN = 216;
const INSPECTOR_MAX = 280;

export default function AppShell() {
  const [sidebarWidth, setSidebarWidth] = useState(256);
  const [inspectorWidth, setInspectorWidth] = useState(236);

  const resizeSidebar = useCallback((dx: number) => {
    setSidebarWidth((width) =>
      Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, width + dx))
    );
  }, []);

  const resizeInspector = useCallback((dx: number) => {
    // Dragging right shrinks the inspector; dragging left expands it.
    setInspectorWidth((width) =>
      Math.max(INSPECTOR_MIN, Math.min(INSPECTOR_MAX, width - dx))
    );
  }, []);

  return (
    <AppProvider>
      <RunnerEventsBridge>
        <div className="app-shell-viewport flex min-h-0 flex-col overflow-hidden bg-[var(--shell-canvas)] text-slate-900">
          <Navbar />

          <main className="min-h-0 flex-1 overflow-hidden">
            <div className="mx-auto flex h-full min-h-0 w-full max-w-[1420px] box-border gap-2.5 px-3 py-3 sm:gap-3 sm:px-5 sm:py-5">
              <div className="flex min-h-0 flex-1 items-stretch gap-0">
                <div
                  style={{ width: sidebarWidth }}
                  className="min-h-0 flex-shrink-0 overflow-hidden"
                >
                  <Sidebar />
                </div>

                <ResizeHandle onResize={resizeSidebar} />

                <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
                  <WorkspacePanel />
                </div>

                <ResizeHandle onResize={resizeInspector} />

                <div
                  style={{ width: inspectorWidth }}
                  className="min-h-0 flex-shrink-0 overflow-hidden"
                >
                  <InspectorPanel />
                </div>
              </div>
            </div>
          </main>
        </div>
      </RunnerEventsBridge>
    </AppProvider>
  );
}
