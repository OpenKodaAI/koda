import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  AvatarPicker,
  OPERATOR_AVATAR_STORAGE_KEY,
  avatarOptions,
  getAvatarOption,
  readStoredOperatorAvatar,
} from "@/components/ui/avatar-picker";

describe("AvatarPicker", () => {
  it("renders lightweight animated SVG personalities", () => {
    const { container } = render(<AvatarPicker value="cobalt" displayName="Owner" />);

    const style = container.querySelector("svg style");
    expect(style?.textContent).toContain("prefers-reduced-motion");
    expect(style?.textContent).toContain("-blink");
    expect(screen.getAllByRole("img", { name: "Cobalt animated avatar" }).length).toBeGreaterThan(0);
  });

  it("renders every local avatar option and reports selection changes", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(
      <AvatarPicker
        value="ember"
        onChange={onChange}
        displayName="Owner"
        subtitle="Pick an avatar"
      />,
    );

    expect(screen.getByRole("heading", { name: "Owner" })).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(avatarOptions.length);
    expect(screen.getByRole("radio", { name: "Select Ember" })).toHaveAttribute(
      "aria-checked",
      "true",
    );

    await user.click(screen.getByRole("radio", { name: "Select Violet" }));

    expect(onChange).toHaveBeenCalledWith("violet");
  });

  it("normalizes unknown and persisted avatar ids to a safe local option", () => {
    expect(getAvatarOption("not-real").id).toBe("ember");

    window.localStorage.setItem(OPERATOR_AVATAR_STORAGE_KEY, "mint");
    expect(readStoredOperatorAvatar()).toBe("mint");

    window.localStorage.setItem(OPERATOR_AVATAR_STORAGE_KEY, "not-real");
    expect(readStoredOperatorAvatar()).toBe("ember");
  });
});
