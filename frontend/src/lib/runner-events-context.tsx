"use client";

/**
 * React context that owns the per-session runner-events subscription.
 *
 * One subscription per active session — when the user switches sessions, the
 * provider tears down the previous AbortController and opens a new one. Job
 * state is keyed by job_id (unique per Superbio submission), so multiple
 * concurrent runners coexist without colliding.
 *
 * History per job is bounded so a long-running pipeline doesn't grow
 * unboundedly — the latest event is always available, and the last
 * MAX_HISTORY_PER_JOB events are kept for log tail / sparkline rendering.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { subscribeRunnerEvents } from "./runner-events";
import type { RunnerEventPayload, RunnerJobState } from "./types";

const MAX_HISTORY_PER_JOB = 200;
// Cap how often we flush state into React. Runner events fire at most every
// ~10s today, but heartbeats may eventually be more frequent — debouncing
// here prevents a thundering herd if a tool emits many events at once.
const FLUSH_INTERVAL_MS = 100;

interface RunnerEventsContextValue {
  jobs: ReadonlyMap<string, RunnerJobState>;
  selectedJobId: string | null;
  setSelectedJobId: (jobId: string | null) => void;
  /** Connection state for the current session, surfaced to the UI for badges. */
  connection: "idle" | "connecting" | "open" | "error";
  /** Last known error message, if connection === "error". */
  lastError: string | null;
}

const RunnerEventsContext = createContext<RunnerEventsContextValue | null>(null);

export interface RunnerEventsProviderProps {
  /** Session whose runners to follow; `null` disables the subscription. */
  sessionId: string | null;
  /** Optional bearer for non-loopback deployments. */
  bearerToken?: string | null;
  children: ReactNode;
}

export function RunnerEventsProvider({
  sessionId,
  bearerToken,
  children,
}: RunnerEventsProviderProps) {
  const [jobs, setJobs] = useState<ReadonlyMap<string, RunnerJobState>>(new Map());
  const [selectedJobId, setSelectedJobIdState] = useState<string | null>(null);
  const [connection, setConnection] =
    useState<RunnerEventsContextValue["connection"]>("idle");
  const [lastError, setLastError] = useState<string | null>(null);

  // Mutable working copy that we mutate on every event and flush into React
  // state at most every FLUSH_INTERVAL_MS to coalesce bursts.
  const jobsRef = useRef<Map<string, RunnerJobState>>(new Map());
  const flushScheduled = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Track the highest event_index we've seen so a reconnect can resume.
  const lastIndexRef = useRef<number>(0);
  // Auto-select the first job we observe; clear selection on session change.
  const sawFirstJobRef = useRef(false);

  const flushJobs = useCallback(() => {
    flushScheduled.current = null;
    setJobs(new Map(jobsRef.current));
  }, []);

  const scheduleFlush = useCallback(() => {
    if (flushScheduled.current !== null) return;
    flushScheduled.current = setTimeout(flushJobs, FLUSH_INTERVAL_MS);
  }, [flushJobs]);

  const handleEvent = useCallback(
    (event: RunnerEventPayload) => {
      lastIndexRef.current = Math.max(lastIndexRef.current, event.event_index);

      const existing = jobsRef.current.get(event.job_id);
      const history = existing
        ? [...existing.history, event].slice(-MAX_HISTORY_PER_JOB)
        : [event];
      const next: RunnerJobState = {
        job_id: event.job_id,
        tool: event.tool,
        latest: event,
        history,
        first_seen_at: existing?.first_seen_at ?? event.timestamp,
      };
      jobsRef.current.set(event.job_id, next);

      if (!sawFirstJobRef.current) {
        sawFirstJobRef.current = true;
        setSelectedJobIdState((prev) => prev ?? event.job_id);
      }

      scheduleFlush();
    },
    [scheduleFlush]
  );

  const setSelectedJobId = useCallback((jobId: string | null) => {
    setSelectedJobIdState(jobId);
  }, []);

  // Reset state on session change (or when sessionId becomes null).
  useEffect(() => {
    jobsRef.current = new Map();
    lastIndexRef.current = 0;
    sawFirstJobRef.current = false;
    setJobs(new Map());
    setSelectedJobIdState(null);
    setLastError(null);
    setConnection(sessionId ? "connecting" : "idle");
  }, [sessionId]);

  // Subscribe whenever sessionId changes. AbortController is the teardown.
  useEffect(() => {
    if (!sessionId) return undefined;

    const controller = new AbortController();
    let cancelled = false;

    void subscribeRunnerEvents({
      sessionId,
      sinceEventIndex: lastIndexRef.current,
      bearerToken,
      signal: controller.signal,
      onEvent: (event) => {
        if (cancelled) return;
        if (connection !== "open") setConnection("open");
        handleEvent(event);
      },
      onError: (err) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : String(err);
        setLastError(message);
        setConnection("error");
      },
    }).finally(() => {
      // Stream closed cleanly; surface as idle if not already errored.
      if (!cancelled) {
        setConnection((prev) => (prev === "error" ? prev : "idle"));
      }
    });

    return () => {
      cancelled = true;
      controller.abort();
      if (flushScheduled.current !== null) {
        clearTimeout(flushScheduled.current);
        flushScheduled.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, bearerToken]);

  const value = useMemo<RunnerEventsContextValue>(
    () => ({
      jobs,
      selectedJobId,
      setSelectedJobId,
      connection,
      lastError,
    }),
    [jobs, selectedJobId, setSelectedJobId, connection, lastError]
  );

  return (
    <RunnerEventsContext.Provider value={value}>
      {children}
    </RunnerEventsContext.Provider>
  );
}

export function useRunnerEvents(): RunnerEventsContextValue {
  const ctx = useContext(RunnerEventsContext);
  if (!ctx) {
    throw new Error(
      "useRunnerEvents() must be called inside <RunnerEventsProvider>."
    );
  }
  return ctx;
}

/** Convenience selector: only re-renders when the chosen job updates. */
export function useRunnerJob(jobId: string | null): RunnerJobState | null {
  const { jobs } = useRunnerEvents();
  if (!jobId) return null;
  return jobs.get(jobId) ?? null;
}
