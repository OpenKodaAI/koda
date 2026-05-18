import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { ChatComposer } from "@/components/sessions/chat/chat-composer";
import type { Mention } from "@/lib/contracts/sessions";

vi.mock("@/hooks/use-command-catalog", () => ({
  useSkillsCatalog: () => [
    { id: "python_dev", title: "Python dev", description: "Python expertise", category: "code" },
    { id: "clean_arch", title: "Clean architecture", description: "DDD patterns", category: "code" },
  ],
  useToolsCatalog: () => [],
  usePendingApprovalsCatalog: () => [],
}));

vi.mock("@/hooks/use-mcp-catalog-suggestions", () => ({
  useMcpCatalogSuggestions: () => ({
    servers: [
      {
        server_key: "supabase",
        display_name: "Supabase",
        description: "Postgres + auth",
        tagline: "Database",
        transport_type: "http_sse",
        command_template: [],
        env_fields: [],
        category: "data",
        expected_tools: [],
      },
      {
        server_key: "github",
        display_name: "GitHub",
        description: "Repo ops",
        tagline: "DevOps",
        transport_type: "http_sse",
        command_template: [],
        env_fields: [],
        category: "development",
        expected_tools: [],
      },
    ],
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

const agentCatalog = [
  {
    id: "ATLAS",
    label: "ATLAS",
    color: "#ff5a5a",
    colorRgb: "255, 90, 90",
    initials: "MA",
    status: "active" as const,
    model: "Claude Opus 4.6",
  },
];

interface HarnessProps {
  onMentionsChange?: (mentions: Mention[]) => void;
  onSubmit?: () => void;
  initialValue?: string;
}

function ComposerHarness({ onMentionsChange, onSubmit, initialValue = "" }: HarnessProps) {
  const [value, setValue] = useState(initialValue);
  return (
    <ChatComposer
      value={value}
      onChange={setValue}
      onSubmit={onSubmit ?? (() => {})}
      agentId="ATLAS"
      onMentionsChange={onMentionsChange}
    />
  );
}

function renderHarness(props: HarnessProps = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLanguage="en-US">
        <AgentCatalogProvider initialAgents={agentCatalog}>
          <ComposerHarness {...props} />
        </AgentCatalogProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("ChatComposer mention menu", () => {
  it("opens a flat list of skills + mcp options when '@' is typed", async () => {
    const user = userEvent.setup();
    renderHarness();

    const editable = screen.getByRole("textbox", { name: /Send a message/i });
    await user.click(editable);
    await user.keyboard("@");

    await screen.findByRole("listbox");
    expect(screen.getByRole("option", { name: /Python dev/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Supabase/i })).toBeInTheDocument();
    // Group eyebrows have been removed in favour of a minimal list.
    expect(screen.queryByText(/^Skills$/i)).toBeNull();
    expect(screen.queryByText(/^MCP servers$/i)).toBeNull();
  });

  it("does NOT trigger inside an email-like token", async () => {
    const user = userEvent.setup();
    renderHarness();

    const editable = screen.getByRole("textbox", { name: /Send a message/i });
    await user.click(editable);
    await user.keyboard("ryan@gmail");

    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("renders a top-of-textarea badge and reports the mention to the parent", async () => {
    const user = userEvent.setup();
    const onMentionsChange = vi.fn();
    renderHarness({ onMentionsChange });

    const editable = screen.getByRole("textbox", { name: /Send a message/i }) as HTMLTextAreaElement;
    await user.click(editable);
    await user.keyboard("@py");

    await screen.findByRole("listbox");
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(document.querySelector('[data-mention-slug="python_dev"]')).not.toBeNull();
    });
    // The @-trigger token has been stripped from the textarea; the badge above
    // is the only representation of the mention.
    expect(editable.value).not.toContain("@py");

    await waitFor(() => {
      expect(onMentionsChange).toHaveBeenCalledWith([
        { kind: "skill", slug: "python_dev" },
      ]);
    });
  });

  it("filters by query as the user types", async () => {
    const user = userEvent.setup();
    renderHarness();

    const editable = screen.getByRole("textbox", { name: /Send a message/i });
    await user.click(editable);
    await user.keyboard("@supa");

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Supabase/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole("option", { name: /Python dev/i })).toBeNull();
    expect(screen.queryByRole("option", { name: /GitHub/i })).toBeNull();
  });

  it("drops the tracked mention when the badge's remove button is clicked", async () => {
    const user = userEvent.setup();
    const onMentionsChange = vi.fn();
    renderHarness({ onMentionsChange });

    const editable = screen.getByRole("textbox", { name: /Send a message/i });
    await user.click(editable);
    await user.keyboard("@py");
    await screen.findByRole("listbox");
    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(document.querySelector('[data-mention-slug="python_dev"]')).not.toBeNull();
    });

    const removeBtn = screen.getByRole("button", { name: /Remove Python dev/i });
    await user.click(removeBtn);

    await waitFor(() => {
      expect(document.querySelector('[data-mention-slug="python_dev"]')).toBeNull();
    });
    await waitFor(() => {
      expect(onMentionsChange).toHaveBeenLastCalledWith([]);
    });
  });
});
