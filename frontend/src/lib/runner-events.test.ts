import { describe, expect, it } from "vitest";

import {
  buildRunnerArtifactUrl,
  parseRunnerEventChunk,
} from "./runner-events";
import type { RunnerEventPayload } from "./types";

function frame(payload: Partial<RunnerEventPayload>): string {
  const full: RunnerEventPayload = {
    session_id: "s1",
    job_id: "j1",
    tool: "alphafold2",
    phase: "running",
    timestamp: 1_700_000_000,
    event_index: 1,
    ...payload,
  };
  return `data: ${JSON.stringify(full)}\n\n`;
}

describe("parseRunnerEventChunk", () => {
  it("parses a single complete frame", () => {
    const { events, remainder } = parseRunnerEventChunk("", frame({ event_index: 5 }));
    expect(events).toHaveLength(1);
    expect(events[0].event_index).toBe(5);
    expect(remainder).toBe("");
  });

  it("preserves an incomplete trailing frame in the remainder", () => {
    const partial = `data: ${JSON.stringify({
      session_id: "s",
      job_id: "j",
      tool: "t",
      phase: "queued",
      event_index: 1,
      timestamp: 1,
    })}`;
    const { events, remainder } = parseRunnerEventChunk("", partial);
    expect(events).toEqual([]);
    expect(remainder).toBe(partial);
  });

  it("stitches a frame split across two chunks", () => {
    const full = frame({ event_index: 7 });
    const splitAt = full.length - 4;
    const first = parseRunnerEventChunk("", full.slice(0, splitAt));
    expect(first.events).toEqual([]);
    const second = parseRunnerEventChunk(first.remainder, full.slice(splitAt));
    expect(second.events).toHaveLength(1);
    expect(second.events[0].event_index).toBe(7);
  });

  it("ignores SSE comment / keepalive lines", () => {
    const raw = `: keepalive\n\n${frame({ event_index: 9 })}`;
    const { events } = parseRunnerEventChunk("", raw);
    expect(events).toHaveLength(1);
    expect(events[0].event_index).toBe(9);
  });

  it("skips malformed JSON without breaking subsequent frames", () => {
    const bad = `data: {"oops":\n\n`;
    const ok = frame({ event_index: 11 });
    const { events } = parseRunnerEventChunk("", bad + ok);
    expect(events).toHaveLength(1);
    expect(events[0].event_index).toBe(11);
  });

  it("rejects payloads missing required fields", () => {
    const incomplete = `data: ${JSON.stringify({ session_id: "s", phase: "queued" })}\n\n`;
    const { events } = parseRunnerEventChunk("", incomplete);
    expect(events).toEqual([]);
  });

  it("normalizes CRLF separators", () => {
    const crlf = frame({ event_index: 3 }).replace(/\n/g, "\r\n");
    const { events } = parseRunnerEventChunk("", crlf);
    expect(events).toHaveLength(1);
  });

  it("parses two events from a single chunk", () => {
    const combined = frame({ event_index: 1 }) + frame({ event_index: 2 });
    const { events } = parseRunnerEventChunk("", combined);
    expect(events.map((e) => e.event_index)).toEqual([1, 2]);
  });
});

describe("buildRunnerArtifactUrl", () => {
  it("URL-encodes path components and preserves the tool segment", () => {
    const url = buildRunnerArtifactUrl(
      "alphafold2",
      "20260504/abcd/outputs/ranked_0.pdb",
      "http://example.test"
    );
    const u = new URL(url);
    expect(u.pathname).toBe("/api/runners/artifact");
    expect(u.searchParams.get("tool")).toBe("alphafold2");
    expect(u.searchParams.get("path")).toBe(
      "20260504/abcd/outputs/ranked_0.pdb"
    );
  });
});
