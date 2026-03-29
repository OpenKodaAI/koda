import type { HTMLAttributes, ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";

vi.mock("framer-motion", () => {
  const createMotion =
    (Tag: "div" | "button" | "aside") => {
      function MotionMock({ children, ...props }: HTMLAttributes<HTMLElement>) {
        return <Tag {...props}>{children}</Tag>;
      }

      MotionMock.displayName = `Motion${Tag[0]?.toUpperCase() ?? "D"}${Tag.slice(1)}Mock`;
      return MotionMock;
    };

  return {
    AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
    motion: new Proxy(
      {},
      {
        get: (_target, key: string) => {
          if (key === "button") return createMotion("button");
          if (key === "aside") return createMotion("aside");
          return createMotion("div");
        },
      },
    ),
  };
});

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/hooks/use-runtime-task", () => ({
  useRuntimeTask: vi.fn(),
}));

vi.mock("@/components/runtime/runtime-terminal-panel", () => ({
  RuntimeTerminalPanel: () => <div>terminal mock</div>,
}));

vi.mock("@/components/runtime/runtime-browser-panel", () => ({
  RuntimeBrowserPanel: () => <div>browser mock</div>,
}));

describe("RuntimeTaskRoom", () => {
  it("renders a single stage with tabs and opens details in a secondary panel", async () => {
    const { useRuntimeTask } = await import("@/hooks/use-runtime-task");
    vi.mocked(useRuntimeTask).mockReturnValue({
      bundle: {
        botId: "ATLAS",
        fetchedAt: "2026-03-19T00:00:00.000Z",
        availability: {
          health: "available",
          database: "available",
          runtime: "available",
          browser: "available",
          attach: "available",
          errors: [],
        },
        task: {
          id: 42,
          status: "running",
          query_text: "Acompanhar execução de ponta a ponta",
          current_phase: "running",
          started_at: "2026-03-19T00:00:00.000Z",
          last_heartbeat_at: "2026-03-19T00:01:00.000Z",
        },
        environment: {
          id: 7,
          task_id: 42,
          status: "active",
          current_phase: "running",
          branch_name: "task/42",
          workspace_path: "/tmp/runtime-42",
          runtime_dir: "/tmp/runtime-42/.runtime",
          last_heartbeat_at: "2026-03-19T00:01:00.000Z",
        },
        warnings: [],
        guardrails: [],
        events: [
          {
            seq: 1,
            type: "task_started",
            severity: "info",
            ts: "2026-03-19T00:01:00.000Z",
            payload: { message: "Execução iniciada" },
          },
        ],
        artifacts: [],
        checkpoints: [],
        terminals: [],
        browser: {
          status: "running",
          transport: "local_headful",
          novnc_port: null,
        },
        browserSessions: [],
        workspaceTree: [],
        workspaceStatus: { text: "M src/app.tsx" },
        workspaceDiff: { text: "+ novo fluxo" },
        services: [],
        resources: [
          {
            id: 1,
            task_id: 42,
            cpu_percent: 14,
            rss_kb: 2048,
            process_count: 3,
            workspace_disk_bytes: 1024 * 1024,
            created_at: "2026-03-19T00:01:00.000Z",
          },
        ],
        loopCycles: [],
        sessions: {
          attach_sessions: [],
          browser_sessions: [],
          terminals: [],
        },
        errors: [],
      },
      loading: false,
      refreshing: false,
      error: null,
      connected: true,
      refresh: vi.fn(),
      mutate: vi.fn(),
      fetchResource: vi.fn(),
    });

    const { RuntimeTaskRoom } = await import("@/components/runtime/runtime-task-room");

    render(
      <I18nProvider initialLanguage="pt-BR">
        <RuntimeTaskRoom botId="ATLAS" taskId={42} />
      </I18nProvider>,
    );

    expect(screen.getByText("Task #42")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Terminal" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Browser|Navegador/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Atividade" })).toBeInTheDocument();
    expect(screen.getByText("terminal mock")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Detalhes" }));

    expect(screen.getByRole("tab", { name: "Arquivos" })).toBeInTheDocument();
    expect(screen.getByText("/tmp/runtime-42")).toBeInTheDocument();
    expect(screen.getByText(/Git status|Status do Git/i)).toBeInTheDocument();
  });
});
