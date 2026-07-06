import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  AvatarGroupWithTooltips,
  getAvatarGroupInitials,
  type AvatarGroupItem,
} from "@/components/ui/avatar-group-with-tooltip";

const avatars: AvatarGroupItem[] = [
  { id: "DEMO_ATLAS", name: "Atlas", color: "#78A8FF" },
  { id: "DEMO_FORGE", name: "Forge", color: "#D6A53B" },
  { id: "DEMO_SAGE", name: "Sage", color: "#7C5FA8" },
];

describe("AvatarGroupWithTooltips", () => {
  it("renders real agent fallbacks and overflow count", () => {
    render(
      <AvatarGroupWithTooltips
        avatars={avatars}
        maxVisible={2}
        ariaLabel="Room participants"
      />,
    );

    expect(screen.getByLabelText("Room participants")).toBeInTheDocument();
    expect(screen.getByText("AT")).toBeInTheDocument();
    expect(screen.getByText("FO")).toBeInTheDocument();
    expect(screen.getByLabelText("1 more participants")).toHaveTextContent("+1");
  });

  it("can render header avatars without visible initials", () => {
    render(
      <AvatarGroupWithTooltips
        avatars={avatars.slice(0, 1)}
        showInitials={false}
        ariaLabel="Active agent"
      />,
    );

    expect(screen.getByLabelText("Active agent")).toBeInTheDocument();
    expect(screen.getByLabelText("Atlas")).toBeInTheDocument();
    expect(screen.queryByText("AT")).not.toBeInTheDocument();
  });

  it("derives compact initials from labels, ids, and explicit initials", () => {
    expect(getAvatarGroupInitials({ id: "agent_one", name: "Agent One" })).toBe("AO");
    expect(getAvatarGroupInitials({ id: "DEMO_SAGE", name: "", initials: "sg" })).toBe("SG");
    expect(getAvatarGroupInitials({ id: "KODA", name: "" })).toBe("KO");
  });
});
