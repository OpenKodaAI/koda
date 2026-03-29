import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MaskedSecretPreview, SecretInput } from "@/components/ui/secret-controls";

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

  it("keeps saved previews masked and lets the user hide or show the masked reference", async () => {
    const user = userEvent.setup();
    render(<MaskedSecretPreview preview="sk-******1234" />);

    expect(screen.getByText("sk-******1234")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", {
        name: /ocultar valor mascarado|hide masked value/i,
      }),
    );
    expect(screen.getByText("••••••••••")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", {
        name: /mostrar valor mascarado|show masked value/i,
      }),
    );
    expect(screen.getByText("sk-******1234")).toBeInTheDocument();
  });
});
