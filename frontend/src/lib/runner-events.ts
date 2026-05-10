/**
 * Client for the /api/runners/events SSE channel.
 *
 * The runner-events stream lives alongside the main chat SSE: it is keyed
 * per session and outlives any single conversational turn (long-running
 * runners — AlphaFold2, Boltz, Nextflow pipelines — emit progress for tens
 * of minutes). Use this module via {@link subscribeRunnerEvents} for a raw
 * subscription, or via the React provider in `runner-events-context.tsx`.
 *
 * Resume semantics: the server-side bus keeps a bounded ring buffer per
 * session. After a reconnect we replay events strictly after
 * `since_event_index` to avoid duplicate UI state without losing progress.
 */
import type { RunnerEventPayload } from "./types";

export interface RunnerEventsSubscribeOptions {
  sessionId: string;
  /** Resume cursor: only events with index > this value will be delivered. */
  sinceEventIndex?: number;
  /** Optional bearer token for protected (non-loopback) deployments. */
  bearerToken?: string | null;
  /** Override the default backend origin (matches `lib/api.ts` resolution). */
  apiBase?: string;
  onEvent: (event: RunnerEventPayload) => void;
  onError?: (error: unknown) => void;
  /** Aborting this signal cancels the underlying fetch and stops dispatch. */
  signal: AbortSignal;
}

const DEFAULT_API_PORT = "8002";

function resolveApiBase(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  const port = process.env.NEXT_PUBLIC_API_PORT || DEFAULT_API_PORT;
  if (typeof window === "undefined") return `http://localhost:${port}`;
  return window.location.origin;
}

/**
 * Parse a partial SSE buffer and return any complete events plus the
 * unconsumed remainder. SSE frames are separated by blank lines (\n\n);
 * a frame may span multiple `data:` lines (we concatenate them). Comments
 * (lines starting with `:`) are silently ignored.
 *
 * Exported for unit tests — callers should normally use
 * {@link subscribeRunnerEvents}.
 */
export function parseRunnerEventChunk(
  buffer: string,
  chunk: string
): { events: RunnerEventPayload[]; remainder: string } {
  const combined = buffer + chunk;
  const events: RunnerEventPayload[] = [];

  // Normalize CRLF → LF so we can split on \n\n consistently.
  const normalized = combined.replace(/\r\n/g, "\n");
  const frames = normalized.split("\n\n");
  // The last frame may be incomplete; carry it forward as the remainder.
  const remainder = frames.pop() ?? "";

  for (const frame of frames) {
    if (!frame.trim()) continue;
    const dataLines: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith(":")) continue; // SSE comment / keepalive
      if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (dataLines.length === 0) continue;

    const payload = dataLines.join("\n");
    try {
      const parsed = JSON.parse(payload) as unknown;
      if (isRunnerEventPayload(parsed)) {
        events.push(parsed);
      }
    } catch {
      // Malformed JSON in a single frame should not break the stream.
      // We skip it; the next frame will still be parsed cleanly.
    }
  }

  return { events, remainder };
}

function isRunnerEventPayload(value: unknown): value is RunnerEventPayload {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.session_id === "string" &&
    typeof v.job_id === "string" &&
    typeof v.tool === "string" &&
    typeof v.phase === "string" &&
    typeof v.event_index === "number" &&
    typeof v.timestamp === "number"
  );
}

/**
 * Open an SSE subscription to /api/runners/events for the given session.
 * Returns a Promise that resolves when the underlying stream ends or is
 * aborted. Errors during streaming are reported via `onError`; the function
 * does not auto-reconnect (callers / hooks own the retry policy so they can
 * surface state to the UI).
 */
export async function subscribeRunnerEvents(
  options: RunnerEventsSubscribeOptions
): Promise<void> {
  const {
    sessionId,
    sinceEventIndex = 0,
    bearerToken = null,
    apiBase = resolveApiBase(),
    onEvent,
    onError,
    signal,
  } = options;

  const url = new URL("/api/runners/events", apiBase);
  url.searchParams.set("session_id", sessionId);
  if (sinceEventIndex > 0) {
    url.searchParams.set("since_event_index", String(sinceEventIndex));
  }

  const headers: Record<string, string> = { Accept: "text/event-stream" };
  if (bearerToken) headers.Authorization = `Bearer ${bearerToken}`;

  let response: Response;
  try {
    response = await fetch(url.toString(), { headers, signal });
  } catch (err) {
    if ((err as DOMException)?.name === "AbortError") return;
    onError?.(err);
    return;
  }

  if (!response.ok || !response.body) {
    onError?.(new Error(`runner events stream failed: HTTP ${response.status}`));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const { events, remainder } = parseRunnerEventChunk(
        buffer,
        decoder.decode(value, { stream: true })
      );
      buffer = remainder;
      for (const event of events) {
        onEvent(event);
      }
    }
    // Flush trailing bytes (decoder finalize).
    const tail = decoder.decode();
    if (tail) {
      const { events } = parseRunnerEventChunk(buffer, tail);
      for (const event of events) onEvent(event);
    }
  } catch (err) {
    if ((err as DOMException)?.name !== "AbortError") onError?.(err);
  }
}

/**
 * Build a URL for the runner artifact endpoint (PDB / CIF / pLDDT JSON).
 * Returns an absolute URL so it can be passed directly to Mol* loaders or
 * <img>/<a> tags. Path validation happens server-side; the caller does not
 * need to escape components.
 */
export function buildRunnerArtifactUrl(
  tool: string,
  path: string,
  apiBase: string = resolveApiBase()
): string {
  const url = new URL("/api/runners/artifact", apiBase);
  url.searchParams.set("tool", tool);
  url.searchParams.set("path", path);
  return url.toString();
}

export const RUNNER_EVENT_API_BASE_RESOLVER = resolveApiBase;
