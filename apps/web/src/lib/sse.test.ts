import { describe, expect, it } from "vitest";
import {
  isRejectedStreamStatus,
  STREAM_ERROR_EVENT,
  STREAM_REJECTED_RETRY_MS,
  streamErrorResponse,
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

  it("emits one named stream_error event with a slow retry hint on a finished 200 event stream", async () => {
    const response = streamErrorResponse(400);

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toContain("text/event-stream");
    const body = await response.text();
    expect(body).toContain(`retry: ${STREAM_REJECTED_RETRY_MS}\n`);
    expect(body).toContain(`event: ${STREAM_ERROR_EVENT}\n`);
    expect(body).toContain('data: {"status":400}\n\n');
  });
});
