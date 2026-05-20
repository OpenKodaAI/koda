import { describe, expect, it } from "vitest";
import { runGraphNodeTypeSchema } from "@/lib/contracts/run-graph";
import {
  getExecutionMetadataVisual,
  getRunGraphNodeVisual,
  getToolVisual,
} from "@/lib/runtime-visual-taxonomy";

describe("runtime visual taxonomy", () => {
  it("covers every RunGraph node type with a specific visual descriptor", () => {
    for (const type of runGraphNodeTypeSchema.options) {
      const visual = getRunGraphNodeVisual(type);
      expect(visual.key).toBe(type);
      expect(visual.label.length).toBeGreaterThan(3);
      expect(visual.icon).toBeTruthy();
    }
  });

  it("keeps request/result/call tool nodes visually distinct", () => {
    expect(getRunGraphNodeVisual("tool_request").icon).not.toBe(getRunGraphNodeVisual("tool_call").icon);
    expect(getRunGraphNodeVisual("tool_result").icon).not.toBe(getRunGraphNodeVisual("tool_request").icon);
    expect(getRunGraphNodeVisual("approval_request").icon).not.toBe(getRunGraphNodeVisual("approval_decision").icon);
  });

  it("differentiates common tool categories and security-sensitive actions", () => {
    expect(getToolVisual({ tool: "web_search", category: "research" }).key).toBe("network_research");
    expect(getToolVisual({ tool: "file_write", category: "fileops" }).key).toBe("file_write");
    expect(getToolVisual({ tool: "file_delete", category: "fileops" }).tone).toBe("danger");
    expect(getToolVisual({ tool: "shell_execute", category: "shell" }).key).toBe("shell");
    expect(getToolVisual({ tool: "task", category: "agent" }).key).toBe("delegate_task");
    expect(getToolVisual({ tool: "mcp_delete_project", category: "mcp" }).key).toBe("mcp");
  });

  it("exposes reusable metadata visuals for execution detail strips", () => {
    expect(getExecutionMetadataVisual("cost").key).toBe("cost");
    expect(getExecutionMetadataVisual("duration").key).toBe("duration");
    expect(getExecutionMetadataVisual("trace_source").key).toBe("trace_source");
    expect(getExecutionMetadataVisual("unknown").key).toBe("metadata");
  });
});
