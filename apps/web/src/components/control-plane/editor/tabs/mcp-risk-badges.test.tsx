import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  McpRiskBadgeGroup,
  getMcpToolRisk,
} from "@/components/control-plane/editor/tabs/mcp-risk-badges";
import { phase2McpRiskFixture } from "@/lib/contracts/__fixtures__/phase2";
import type { McpDiscoveredTool } from "@/lib/control-plane";

describe("McpRiskBadgeGroup", () => {
  it("renders backend-provided risk metadata", () => {
    render(
      <McpRiskBadgeGroup
        risk={phase2McpRiskFixture}
        capabilityName={phase2McpRiskFixture.capability_name}
      />,
    );

    expect(screen.getByText("Destructive Write")).toBeInTheDocument();
    expect(screen.getByText("Requires Approval")).toBeInTheDocument();
    expect(screen.getByText("Redaction")).toBeInTheDocument();
  });

  it("renders unknown risk when mcp_risk.v1 is absent", () => {
    render(<McpRiskBadgeGroup risk={null} capabilityName="list_projects" />);

    expect(screen.getByText("Unknown risk")).toBeInTheDocument();
  });

  it("extracts risk metadata from discovered tools", () => {
    const tool: McpDiscoveredTool = {
      name: "delete_project",
      description: "Delete a project",
      risk_metadata: phase2McpRiskFixture,
    };

    expect(getMcpToolRisk(tool)?.risk_class).toBe("destructive_write");
  });
});
