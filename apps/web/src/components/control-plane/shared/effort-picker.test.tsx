import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EffortPicker, type EffortCapability } from "./effort-picker";

vi.mock("@/hooks/use-app-i18n", async () => {
  const { translateForLanguage } = await vi.importActual<typeof import("@/lib/i18n")>("@/lib/i18n");
  const t = (key: string, options?: Record<string, unknown>) => translateForLanguage("pt-BR", key, options);

  return {
    useAppI18n: () => ({
      t,
      tl: (value: string) => value,
      i18n: { t },
      language: "pt-BR",
      setLanguage: vi.fn(),
      options: [],
    }),
  };
});

describe("EffortPicker", () => {
  it("renders nothing when capability is undefined (model has no effort support)", () => {
    const { container } = render(
      <EffortPicker
        capability={undefined}
        value={null}
        onChange={() => {}}
        context="agent"
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders SoftTabs for enum kind and propagates the chosen value", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const cap: EffortCapability = {
      kind: "enum",
      values: ["low", "medium", "high"],
      defaultValue: "medium",
    };
    render(
      <EffortPicker
        capability={cap}
        value="low"
        onChange={onChange}
        context="global"
      />,
    );
    const highButton = screen.getByRole("tab", { name: /modelEffort\.enumHigh|high|alto/i });
    await user.click(highButton);
    expect(onChange).toHaveBeenCalledWith("high");
  });

  it("renders a numeric input for tokens kind within min and max", () => {
    const onChange = vi.fn();
    const cap: EffortCapability = {
      kind: "tokens",
      min: 0,
      max: 8000,
      defaultValue: 2000,
    };
    render(
      <EffortPicker
        capability={cap}
        value={4000}
        onChange={onChange}
        context="global"
      />,
    );
    const numberInput = screen.getByRole("spinbutton") as HTMLInputElement;
    expect(numberInput.value).toBe("4000");
    expect(numberInput.min).toBe("0");
    expect(numberInput.max).toBe("8000");
    fireEvent.change(numberInput, { target: { value: "6000" } });
    expect(onChange).toHaveBeenCalledWith(6000);
  });

  it("agent context shows an inherit/override toggle that emits null when reverting to inherit", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const cap: EffortCapability = {
      kind: "enum",
      values: ["low", "medium", "high"],
      defaultValue: "medium",
    };
    render(
      <EffortPicker
        capability={cap}
        value="high"
        inheritedValue="medium"
        onChange={onChange}
        context="agent"
      />,
    );
    const inheritButton = screen.getByRole("button", { name: /inherit|herdar/i });
    await user.click(inheritButton);
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("global context does not render the inherit toggle", () => {
    const cap: EffortCapability = {
      kind: "enum",
      values: ["low", "medium", "high"],
    };
    render(
      <EffortPicker capability={cap} value="medium" onChange={() => {}} context="global" />,
    );
    expect(screen.queryByRole("button", { name: /inherit|herdar|override|sobrescrever/i })).toBeNull();
  });
});
