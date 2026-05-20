import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { McpCustomServerModal } from "./mcp-custom-server-modal";

const onSubmitForm = vi.fn();
const onSubmitImport = vi.fn();
const onClose = vi.fn();

beforeEach(() => {
  onSubmitForm.mockReset();
  onSubmitImport.mockReset();
  onClose.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function renderModal(props: Partial<React.ComponentProps<typeof McpCustomServerModal>> = {}) {
  return render(
    <McpCustomServerModal
      open
      onClose={onClose}
      onSubmitForm={onSubmitForm}
      onSubmitImport={onSubmitImport}
      {...props}
    />,
  );
}

describe("McpCustomServerModal", () => {
  it("starts in form mode and switches to JSON mode when defaultMode='json'", () => {
    const { unmount } = renderModal({ defaultMode: "json" });
    // The textarea sample JSON should be visible (JSON tab content)
    const textarea = screen.getByRole("textbox");
    expect((textarea as HTMLTextAreaElement).value).toContain('"mcpServers"');
    unmount();
  });

  it("submits the form payload with required fields", async () => {
    onSubmitForm.mockResolvedValueOnce({ server_key: "custom_demo" });
    renderModal();

    fireEvent.change(screen.getByPlaceholderText("my-server"), {
      target: { value: "demo" },
    });
    fireEvent.change(screen.getByPlaceholderText("My MCP Server"), {
      target: { value: "Demo Server" },
    });
    // Add args (command stays as default 'npx')
    fireEvent.change(screen.getByPlaceholderText("-y @my-company/mcp"), {
      target: { value: "-y @demo/mcp" },
    });

    fireEvent.click(screen.getByRole("button", { name: /^Add$/i }));

    await waitFor(() => {
      expect(onSubmitForm).toHaveBeenCalledTimes(1);
    });
    const callArg = onSubmitForm.mock.calls[0][0];
    expect(callArg.scope).toBe("system");
    expect(callArg.payload.server_key).toBe("demo");
    expect(callArg.payload.transport_type).toBe("stdio");
    expect(callArg.payload.command).toEqual(["npx", "-y", "@demo/mcp"]);
  });

  it("imports Claude Desktop JSON via import endpoint", async () => {
    onSubmitImport.mockResolvedValueOnce({ created: ["custom_linear"], updated: [], errors: [] });
    renderModal({ defaultMode: "json" });

    const sample = `{
      "mcpServers": {
        "linear": { "url": "https://mcp.linear.app/mcp", "transport": "http_sse" }
      }
    }`;
    fireEvent.change(screen.getByRole("textbox"), { target: { value: sample } });

    const importButton = await screen.findByRole("button", { name: /Import \(1\)/i });
    fireEvent.click(importButton);

    await waitFor(() => {
      expect(onSubmitImport).toHaveBeenCalledTimes(1);
    });
    const callArg = onSubmitImport.mock.calls[0][0];
    expect(callArg.scope).toBe("system");
    expect(callArg.raw.mcpServers.linear.url).toBe("https://mcp.linear.app/mcp");
  });

  it("rejects empty server_key in form mode", async () => {
    renderModal();
    fireEvent.click(screen.getByRole("button", { name: /^Add$/i }));
    expect(
      await screen.findByText(/Identifier and display name are required/i),
    ).toBeInTheDocument();
    expect(onSubmitForm).not.toHaveBeenCalled();
  });

  it("disables JSON submit when paste is invalid", () => {
    renderModal({ defaultMode: "json" });
    const textbox = screen.getByRole("textbox");
    fireEvent.change(textbox, { target: { value: "{ not json" } });
    const button = screen.getByRole("button", { name: /^Import$/i });
    expect(button).toBeDisabled();
    // JsonEditor surfaces invalidity through aria-invalid on the textarea.
    expect(textbox).toHaveAttribute("aria-invalid", "true");
  });

  it("does not render when closed", () => {
    const { container } = render(
      <McpCustomServerModal
        open={false}
        onClose={onClose}
        onSubmitForm={onSubmitForm}
        onSubmitImport={onSubmitImport}
      />,
    );
    expect(container.firstChild).toBeNull();
  });
});
