import { describe, expect, it } from "vitest";
import {
  isRejectedStreamStatus,
  readStreamError,
  STREAM_ERROR_EVENT,
  STREAM_REJECTED_RETRY_MS,
  streamErrorResponse,
  upstreamStreamErrorMessage,
} from "@/lib/sse";

describe("runtime stream error contract", () => {
  it("treats only runtime rejections as rejected and everything else as transient", () => {
    for (const status of [400, 404, 422]) {
      expect(isRejectedStreamStatus(status)).toBe(true);
    }
    // 401/403 usually mean the relay got no runtime token from the control plane.
    for (const status of [200, 401, 403, 408, 425, 429, 500, 502, 503, 504]) {
      expect(isRejectedStreamStatus(status)).toBe(false);
    }
  });

  it("extracts the upstream message from plain text and JSON bodies", () => {
    expect(upstreamStreamErrorMessage("invalid after_seq", 400)).toBe("invalid after_seq");
    expect(upstreamStreamErrorMessage('{"error":"invalid runtime token"}', 403)).toBe(
      "invalid runtime token",
    );
    expect(
      upstreamStreamErrorMessage('{"error":{"code":"x","message":"agent not found"}}', 404),
    ).toBe("agent not found");
    expect(upstreamStreamErrorMessage("", 400)).toBe("Runtime stream request failed (400)");
    expect(upstreamStreamErrorMessage("x".repeat(1_000), 400)).toHaveLength(300);
  });

  it("emits one named stream_error event with a slow retry hint on a finished 200 event stream", async () => {
    const response = streamErrorResponse(400, "invalid after_seq");

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toContain("text/event-stream");
    const body = await response.text();
    expect(body).toContain(`retry: ${STREAM_REJECTED_RETRY_MS}\n`);
    expect(body).toContain(`event: ${STREAM_ERROR_EVENT}\n`);
    expect(body).toContain('data: {"status":400,"error":"invalid after_seq"}\n\n');
  });

  it("parses stream_error events and rejects malformed data", () => {
    const event = (data: unknown) => ({ data }) as unknown as Event;

    expect(readStreamError(event('{"status":400,"error":"invalid after_seq"}'))).toEqual({
      status: 400,
      error: "invalid after_seq",
    });
    expect(readStreamError(event("not json"))).toBeNull();
    expect(readStreamError(event('{"status":"400"}'))).toBeNull();
    expect(readStreamError(event(undefined))).toBeNull();
  });
});
