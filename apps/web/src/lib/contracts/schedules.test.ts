import { describe, expect, it } from "vitest";
import {
  scheduleErrorMessage,
  scheduleValidationNotQueuedMessage,
} from "@/lib/contracts/schedules";

describe("scheduleErrorMessage", () => {
  it("shows the scheduler's refusal message when the action answers ok:false", () => {
    // POST .../actions/validate on a job whose validation is still in flight.
    const payload = { ok: false, message: "Validation already pending.", run_id: null };
    expect(scheduleErrorMessage(payload, "Unable to operate on schedule")).toBe(
      "Validation already pending.",
    );
  });

  it("prefers the proxy error over a message", () => {
    expect(scheduleErrorMessage({ error: "Unknown action: x.", message: "ignored" }, "fallback")).toBe(
      "Unknown action: x.",
    );
  });

  it("falls back when the payload carries no usable text", () => {
    expect(scheduleErrorMessage({ error: "  ", message: 42 }, "fallback")).toBe("fallback");
    expect(scheduleErrorMessage(null, "fallback")).toBe("fallback");
    expect(scheduleErrorMessage("oops", "fallback")).toBe("fallback");
  });
});

describe("scheduleValidationNotQueuedMessage", () => {
  it("reports the backend explanation when validation was not queued", () => {
    const payload = {
      ok: true,
      validation_run_id: null,
      message: "Job created, but validation was not queued: Validation could not be queued.",
      job: { id: 7, status: "validation_pending" },
    };
    expect(scheduleValidationNotQueuedMessage(payload, "fallback")).toBe(
      "Job created, but validation was not queued: Validation could not be queued.",
    );
    expect(scheduleValidationNotQueuedMessage({ validation_run_id: null }, "fallback")).toBe("fallback");
  });

  it("stays quiet when validation was queued or is not reported", () => {
    expect(
      scheduleValidationNotQueuedMessage({ validation_run_id: 12, message: "Job created. Validation queued." }, "x"),
    ).toBeNull();
    expect(scheduleValidationNotQueuedMessage({ ok: true, job: { id: 7 } }, "x")).toBeNull();
    expect(scheduleValidationNotQueuedMessage(undefined, "x")).toBeNull();
  });
});
