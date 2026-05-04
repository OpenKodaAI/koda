import type { AgentDisplay } from "@/lib/agent-constants";
import type {
  RuntimeEvent,
  RuntimeOverview,
  RuntimeResourceSample,
  RuntimeTaskBundle,
  RuntimeWorkspaceFile,
  RuntimeWorkspaceSearch,
  RuntimeWorkspaceTreeEntry,
} from "@/lib/runtime-types";

const MOCK_AGENTS: AgentDisplay[] = [
  { id: "atlas", label: "Atlas", color: "#77BFA3", colorRgb: "119 191 163" },
  { id: "nova", label: "Nova", color: "#D97757", colorRgb: "217 119 87" },
  { id: "orion", label: "Orion", color: "#8EA7E9", colorRgb: "142 167 233" },
];

const TASKS = [
  {
    agentId: "atlas",
    taskId: 4107,
    query: "Revisar sinais de embeddings e validar recuperação semântica",
    phase: "running",
    status: "running",
  },
  {
    agentId: "nova",
    taskId: 4108,
    query: "Publicar ajustes visuais do onboarding e verificar responsividade",
    phase: "browser_active",
    status: "running",
  },
  {
    agentId: "orion",
    taskId: 4109,
    query: "Preparar rotina diária de acompanhamento de integrações",
    phase: "queued",
    status: "queued",
  },
  {
    agentId: "atlas",
    taskId: 4110,
    query: "Consolidar artefatos da execução e gerar checkpoint",
    phase: "saving_checkpoint",
    status: "retained",
  },
];

const EVENT_TYPES = [
  "task.accepted",
  "environment.ready",
  "terminal.output",
  "resource.sample",
  "checkpoint.created",
  "artifact.indexed",
  "browser.snapshot",
];

function isoAgo(seconds: number, tick = 0) {
  return new Date(Date.now() - seconds * 1000 + tick * 900).toISOString();
}

function getMockAgents(agents: AgentDisplay[]) {
  return agents.length > 0 ? agents.slice(0, 3) : MOCK_AGENTS;
}

function resolveAgent(agents: AgentDisplay[], agentId: string) {
  return getMockAgents(agents).find((agent) => agent.id === agentId) ?? getMockAgents(agents)[0];
}

function taskFor(agentId: string, taskId?: number) {
  return TASKS.find((item) => item.agentId === agentId && item.taskId === taskId) ?? TASKS.find((item) => item.agentId === agentId) ?? TASKS[0];
}

export function getMockRuntimeAgentIds(agents: AgentDisplay[]) {
  return getMockAgents(agents).map((agent) => agent.id);
}

export function buildMockRuntimeOverviews(agents: AgentDisplay[], tick: number) {
  const selectedAgents = getMockAgents(agents);
  return Object.fromEntries(
    selectedAgents.map((agent, agentIndex) => {
      const agentTasks = TASKS.filter((task) => task.agentId === MOCK_AGENTS[agentIndex]?.id || task.agentId === agent.id);
      const mappedTasks = agentTasks.length > 0 ? agentTasks : TASKS.slice(agentIndex, agentIndex + 1);
      const environments = mappedTasks.map((task, index) => ({
        id: task.taskId + 700,
        task_id: task.taskId,
        status: task.status,
        current_phase: index === 0 && tick % 4 === 0 ? "thinking" : task.phase,
        workspace_path: `/workspace/koda/.runtime/${agent.id}/${task.taskId}`,
        runtime_dir: `/tmp/koda-runtime/${task.taskId}`,
        branch_name: `codex/runtime-sample-${task.taskId}`,
        progress_percent: Math.min(96, 34 + tick * 3 + index * 12),
        updated_at: isoAgo(18 + index * 50, tick),
        last_heartbeat_at: isoAgo(6 + index * 12, tick),
        created_at: isoAgo(480 + index * 120, tick),
        retention_expires_at: isoAgo(-7200, tick),
      }));

      const overview: RuntimeOverview = {
        agentId: agent.id,
        agentLabel: agent.label,
        agentColor: agent.color,
        baseUrl: "mock://runtime",
        fetchedAt: new Date().toISOString(),
        health: {
          status: "available",
          active_tasks: environments.filter((item) => item.status !== "retained").length,
          active_processes: 5 + agentIndex,
        },
        snapshot: {
          root_dir: "/workspace/koda",
          active_environments: environments.filter((item) => item.status !== "retained").length,
          retained_environments: environments.filter((item) => item.status === "retained").length,
          cleanup_backlog: agentIndex === 1 ? 1 : 0,
          recovery_backlog: 0,
          queues: mappedTasks.map((task, index) => ({
            task_id: task.taskId,
            status: task.status,
            queue_position: index,
            query_text: task.query,
            queued_at: isoAgo(520 + index * 80, tick),
            updated_at: isoAgo(22 + index * 40, tick),
          })),
          browser_sessions_active: agentIndex === 1 ? 1 : 0,
          attach_sessions_terminal: 1,
          attach_sessions_browser: agentIndex === 1 ? 1 : 0,
          service_endpoints: 2,
        },
        readiness: { ready: true, reasons: [] },
        availability: {
          health: "available",
          database: "available",
          runtime: "available",
          browser: agentIndex === 1 ? "available" : "partial",
          attach: "available",
          errors: [],
        },
        queues: mappedTasks.map((task, index) => ({
          task_id: task.taskId,
          status: task.status,
          queue_position: index,
          query_text: task.query,
          queued_at: isoAgo(520 + index * 80, tick),
          updated_at: isoAgo(22 + index * 40, tick),
        })),
        environments,
        incidents: agentIndex === 1 ? ["Browser sampling is slower than the terminal stream."] : [],
        activeTaskIds: environments.filter((item) => item.status !== "retained").map((item) => item.task_id),
        retainedTaskIds: environments.filter((item) => item.status === "retained").map((item) => item.task_id),
      };
      return [agent.id, overview];
    }),
  );
}

function buildEvents(taskId: number, tick: number): RuntimeEvent[] {
  const count = Math.min(EVENT_TYPES.length, 4 + (tick % 4));
  return EVENT_TYPES.slice(0, count).map((type, index) => ({
    seq: index + 1,
    task_id: taskId,
    env_id: taskId + 700,
    phase: index > 3 ? "running" : "setup",
    type,
    severity: index === 0 ? "info" : "debug",
    payload: {
      message:
        type === "terminal.output"
          ? "pnpm test:web -- --run runtime-overview"
          : type === "resource.sample"
            ? "CPU and memory sample collected"
            : "Runtime sample advanced",
    },
    ts: isoAgo((count - index) * 12, tick),
  }));
}

function buildResources(taskId: number, tick: number): RuntimeResourceSample[] {
  return Array.from({ length: 8 }, (_, index) => ({
    id: taskId * 10 + index,
    task_id: taskId,
    env_id: taskId + 700,
    cpu_percent: 18 + ((tick + index * 7) % 38),
    rss_kb: 320_000 + ((tick + index) % 6) * 28_000,
    process_count: 6 + (index % 3),
    workspace_disk_bytes: 42_000_000 + index * 900_000,
    created_at: isoAgo((8 - index) * 9, tick),
  }));
}

export function buildMockRuntimeTaskBundle(
  agents: AgentDisplay[],
  agentId: string,
  taskId: number,
  tick: number,
): RuntimeTaskBundle {
  const agent = resolveAgent(agents, agentId);
  const task = taskFor(agent.id, taskId);
  const effectiveTaskId = taskId || task.taskId;
  const progress = Math.min(98, 42 + tick * 2);

  return {
    agentId: agent.id,
    fetchedAt: new Date().toISOString(),
    availability: {
      health: "available",
      database: "available",
      runtime: "available",
      browser: "available",
      attach: "available",
      errors: [],
    },
    task: {
      id: effectiveTaskId,
      status: "running",
      query_text: task.query,
      provider: "openai-compatible",
      model: "gpt-5.2",
      attempt: 1,
      max_attempts: 3,
      cost_usd: 0.18,
      started_at: isoAgo(540, tick),
      current_phase: tick % 3 === 0 ? "thinking" : "running",
      last_heartbeat_at: isoAgo(4, tick),
      env_id: effectiveTaskId + 700,
    },
    environment: {
      id: effectiveTaskId + 700,
      task_id: effectiveTaskId,
      status: "running",
      current_phase: tick % 3 === 0 ? "thinking" : "running",
      workspace_path: `/workspace/koda/.runtime/${agent.id}/${effectiveTaskId}`,
      runtime_dir: `/tmp/koda-runtime/${effectiveTaskId}`,
      branch_name: `codex/runtime-sample-${effectiveTaskId}`,
      progress_percent: progress,
      is_pinned: false,
      last_heartbeat_at: isoAgo(4, tick),
      updated_at: isoAgo(4, tick),
      retention_expires_at: isoAgo(-7200, tick),
    },
    warnings: [
      {
        id: 1,
        task_id: effectiveTaskId,
        warning_type: "sample_mode",
        message: "Visual mock: values update locally and do not affect the real runtime.",
        created_at: isoAgo(90, tick),
      },
    ],
    guardrails: [],
    events: buildEvents(effectiveTaskId, tick),
    artifacts: [
      { id: 1, task_id: effectiveTaskId, artifact_kind: "log", label: "runtime.log", path: "logs/runtime.log", created_at: isoAgo(80, tick) },
      { id: 2, task_id: effectiveTaskId, artifact_kind: "report", label: "summary.md", path: "reports/summary.md", created_at: isoAgo(40, tick) },
    ],
    checkpoints: [
      { id: 1, task_id: effectiveTaskId, status: "created", checkpoint_dir: ".koda/checkpoints/001", commit_sha: "a12f9c4", created_at: isoAgo(70, tick) },
    ],
    terminals: [
      {
        id: 1,
        task_id: effectiveTaskId,
        terminal_kind: "operator",
        label: "Runtime",
        interactive: true,
        preview: [
          "$ pnpm test:web -- --run runtime-overview",
          "✓ runtime overview renders live rows",
          "✓ task room receives resource samples",
          `$ sample tick ${tick}: cpu ${18 + (tick % 38)}%`,
          "",
        ].join("\r\n"),
        updated_at: isoAgo(2, tick),
      },
    ],
    browser: {
      status: "available",
      visual_available: true,
      transport: "mock",
      display_id: 99,
      runtime_dir: `/tmp/koda-runtime/${effectiveTaskId}/browser`,
      unavailable_reason: "Browser streaming is represented by the mock state.",
    },
    browserSessions: [],
    workspaceTree: [
      { name: "apps", path: "apps", is_dir: true },
      { name: "runtime-notes.md", path: "runtime-notes.md", is_dir: false, size: 928 },
      { name: "sample-output.json", path: "sample-output.json", is_dir: false, size: 428 },
    ],
    workspaceStatus: {
      ok: true,
      text: " M apps/web/src/components/runtime/runtime-overview.tsx\n?? apps/web/src/lib/runtime-mocks.ts",
    },
    workspaceDiff: {
      ok: true,
      text: "+ live mock resource sample\n+ visual runtime walkthrough",
    },
    services: [
      { id: 1, task_id: effectiveTaskId, label: "preview", host: "127.0.0.1", port: 3000, protocol: "http", status: "running", url: "http://127.0.0.1:3000" },
    ],
    resources: buildResources(effectiveTaskId, tick),
    loopCycles: [
      { id: 1, task_id: effectiveTaskId, cycle_index: 1, phase: "plan", goal: "Map runtime surfaces", created_at: isoAgo(420, tick) },
      { id: 2, task_id: effectiveTaskId, cycle_index: 2, phase: "verify", goal: "Sample live state", created_at: isoAgo(80, tick) },
    ],
    sessions: { attach_sessions: [], browser_sessions: [], terminals: [] },
    errors: [],
  };
}

export function readMockWorkspaceFile(path: string): RuntimeWorkspaceFile {
  if (path.endsWith(".json")) {
    return {
      path,
      content: JSON.stringify({ status: "running", samples: 8, source: "mock-runtime" }, null, 2),
    };
  }

  return {
    path,
    content: [
      "# Runtime sample",
      "",
      "This file is generated by the visual mock mode.",
      "It lets the Files tab behave like a real execution workspace.",
      "",
    ].join("\n"),
  };
}

export function readMockWorkspaceTree(path: string): RuntimeWorkspaceTreeEntry[] {
  if (path === "apps") {
    return [
      { name: "web", path: "apps/web", is_dir: true },
      { name: "runtime-overview.tsx", path: "apps/web/src/components/runtime/runtime-overview.tsx", is_dir: false, size: 18_400 },
    ];
  }
  if (path === "apps/web") {
    return [
      { name: "src", path: "apps/web/src", is_dir: true },
      { name: "package.json", path: "apps/web/package.json", is_dir: false, size: 3_240 },
    ];
  }
  return [];
}

export function readMockWorkspaceSearch(query: string): RuntimeWorkspaceSearch {
  const trimmed = query.trim();
  if (!trimmed) return { ok: true, query, items: [], truncated: false, searched_files: 0 };
  const samples = [
    {
      path: "runtime-notes.md",
      line: "This runtime workspace behaves like a compact IDE.",
      line_number: 4,
    },
    {
      path: "apps/web/src/components/runtime/runtime-overview.tsx",
      line: "export function RuntimeOverview() { return null; }",
      line_number: 12,
    },
    {
      path: "apps/web/src/lib/runtime-mocks.ts",
      line: "export const mockRuntimeSearch = true;",
      line_number: 38,
    },
  ];
  const lower = trimmed.toLowerCase();
  const items = samples.flatMap((sample) => {
    const index = sample.line.toLowerCase().indexOf(lower);
    if (index === -1 && !sample.path.toLowerCase().includes(lower)) return [];
    const start = Math.max(index, 0);
    const end = index >= 0 ? index + trimmed.length : start;
    return [
      {
        path: sample.path,
        line_number: sample.line_number,
        column: start + 1,
        line: sample.line,
        preview: sample.line,
        match: index >= 0 ? sample.line.slice(start, end) : sample.path.split("/").pop() || sample.path,
        start,
        end,
      },
    ];
  });
  return { ok: true, query, items, truncated: false, searched_files: samples.length };
}
