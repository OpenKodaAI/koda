import { describe, expect, it } from "vitest";
import { __statusToState_for_test as statusToState } from "@/components/control-plane/shared/agent-sigil";

describe("AgentSigil statusToState", () => {
  // Realtime *execution* states drive the foreground orb animation.
  // Anything else — including the control-plane definition status that
  // says the agent is enabled (``"active"``) or disabled (``"paused"``) —
  // must keep the orb at idle. The bug we're guarding against here was
  // the catalog mapping ``status="active"`` to ``"talking"``, which made
  // every enabled agent's orb animate as if it were emitting output even
  // when there were zero tasks in flight.

  it("running tasks animate as thinking", () => {
    expect(statusToState("running")).toBe("thinking");
    expect(statusToState("retrying")).toBe("thinking");
  });

  it("queued tasks animate as listening", () => {
    expect(statusToState("queued")).toBe("listening");
  });

  it("control-plane definition statuses keep the orb idle", () => {
    // 'active' = agent enabled (NOT producing output)
    // 'paused' = agent disabled
    // Other definition-layer values must also stay idle.
    for (const status of ["active", "paused", "idle", "error", "unknown"] as const) {
      expect(statusToState(status)).toBeNull();
    }
  });

  it("terminal task states keep the orb idle", () => {
    for (const status of ["completed", "failed", "cancelled"] as const) {
      expect(statusToState(status)).toBeNull();
    }
  });

  it("unknown / missing status falls back to idle", () => {
    expect(statusToState(undefined)).toBeNull();
    expect(statusToState("something-the-backend-invented")).toBeNull();
  });
});
