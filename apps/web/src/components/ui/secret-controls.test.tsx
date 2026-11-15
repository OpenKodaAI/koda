import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { SecretInput } from "@/components/ui/secret-controls";

describe("secret controls", () => {
  it("toggles secret input visibility without changing the value", async () => {
    const user = userEvent.setup();
    render(<SecretInput value="draft-secret" onChange={() => undefined} placeholder="Cole o segredo" />);

    const input = screen.getByPlaceholderText("Cole o segredo") as HTMLInputElement;
    expect(input.type).toBe("password");

    await user.click(
      screen.getByRole("button", { name: /visualizar valor|view value/i }),
    );
    expect(input.type).toBe("text");
    expect(input.value).toBe("draft-secret");

    await user.click(
      screen.getByRole("button", { name: /esconder valor|hide value/i }),
    );
    expect(input.type).toBe("password");
  });

  it("looks and behaves disabled when disabled, including the reveal toggle", async () => {
    const user = userEvent.setup();
    render(
      <SecretInput value="draft-secret" onChange={() => undefined} placeholder="Cole o segredo" disabled />,
    );

    const input = screen.getByPlaceholderText("Cole o segredo") as HTMLInputElement;
    expect(input).toBeDisabled();
    expect(input.className).toContain("disabled:opacity-60");
    expect(input.className).toContain("disabled:cursor-not-allowed");

    const reveal = screen.getByRole("button", { name: /visualizar valor|view value/i });
    expect(reveal).toBeDisabled();
    await user.click(reveal);
    expect(input.type).toBe("password");
  });
});
