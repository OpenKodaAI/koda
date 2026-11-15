// Stub Koda control plane and agent runtime for the stub-backed Playwright specs.
//
// Serves just enough for an operator to sign in and use the routines page: one
// agent (ATLAS) whose runtime base URL points back at this server, and one
// interval routine. Unknown GETs answer with empty collections. Writes answer
// 200 so a request the UI should not have sent still reaches the page.
//
// Usage: node tests/e2e-stub/stub-control-plane.mjs <port>
import http from "node:http";

const port = Number.parseInt(process.argv[2] ?? process.env.KODA_STUB_CONTROL_PLANE_PORT ?? "3418", 10);
const runtimeBaseUrl = `http://127.0.0.1:${port}`;
const sessionToken = "kodas_e2e_stub_session_token_0123456789abcdef";
const cp = "/api/control-plane";

const operator = { id: "op-1", username: "owner", email: "owner@example.com", display_name: "Owner" };
const authOk = {
  authenticated: true,
  has_owner: true,
  bootstrap_required: false,
  auth_mode: "local_account",
  session_required: true,
  onboarding_complete: true,
  recovery_available: true,
  session_subject: "operator:owner",
  operator,
};
const authNo = {
  authenticated: false,
  has_owner: true,
  bootstrap_required: false,
  auth_mode: "local_account",
  session_required: true,
  recovery_available: true,
};

const appearance = { label: "ATLAS", color: "#D97757", color_rgb: "217, 119, 87" };
const agent = {
  id: "ATLAS",
  display_name: "ATLAS",
  status: "active",
  appearance,
  storage_namespace: "atlas",
  runtime_endpoint: {
    health_port: port,
    health_url: `${runtimeBaseUrl}/health`,
    runtime_base_url: runtimeBaseUrl,
  },
  metadata: {},
  organization: { workspace_id: null, workspace_name: null, squad_id: null, squad_name: null },
  applied_version: 1,
  desired_version: 1,
};
const agents = { items: [agent], total: 1, limit: 50, offset: 0, has_more: false };

const general = {
  version: 1,
  values: {
    account: { scheduler_default_timezone: "America/Sao_Paulo", project_dirs: [], default_work_dir: "" },
    models: { providers_enabled: [], default_provider: "", fallback_order: [], functional_defaults: {} },
    resources: { global_tools: [], integrations: {} },
    memory_and_knowledge: {},
    variables: [],
    provider_connections: {},
  },
  source_badges: {},
  catalogs: {
    providers: [],
    model_functions: [],
    functional_model_catalog: {},
    global_tools: [],
    usage_profiles: [],
    memory_profiles: [],
    knowledge_profiles: [],
    provenance_policies: [],
    knowledge_layers: [],
    approval_modes: [],
    autonomy_tiers: [],
  },
  review: { warnings: [], hidden_sections: [] },
};

const routine = {
  id: 7,
  bot_id: "ATLAS",
  user_id: 1,
  chat_id: 2,
  job_type: "agent_query",
  trigger_type: "interval",
  schedule_expr: "1h",
  cron_expression: "1h",
  timezone: "America/Sao_Paulo",
  payload: { name: "Check deploy health", query: "Check deploy health and report regressions" },
  summary: "Check deploy health and report regressions",
  command: "Check deploy health and report regressions",
  description: "",
  created_at: null,
  updated_at: null,
  enabled: 1,
  status: "active",
  work_dir: "/repo",
  next_run_at: "2026-12-01T12:00:00+00:00",
  config_version: 3,
  notification_policy: { mode: "summary_complete" },
  verification_policy: { mode: "post_write_if_any" },
};
const detail = { job: routine, runs: [], events: [] };
const preview = {
  next_runs: ["2026-12-01T12:00:00+00:00", "2026-12-01T13:00:00+00:00", "2026-12-01T14:00:00+00:00"],
};

function send(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, { "content-type": "application/json", "content-length": Buffer.byteLength(body) });
  res.end(body);
}

function handleGet(req, res, pathname) {
  const authed = req.headers.authorization === `Bearer ${sessionToken}`;
  if (pathname === "/health") return send(res, 200, { status: "healthy" });
  if (pathname === `${cp}/auth/status`) return send(res, 200, authed ? authOk : authNo);
  if (pathname === `${cp}/onboarding/status`) {
    return send(res, 200, { has_owner: true, bootstrap_required: false, onboarding_complete: true });
  }
  if (pathname === `${cp}/system-settings/general`) return send(res, 200, general);
  if (pathname === `${cp}/agents`) return send(res, 200, agents);
  if (pathname === `${cp}/agents/ATLAS`) return send(res, 200, agent);
  if (pathname === `${cp}/workspaces`) {
    return send(res, 200, {
      items: [],
      virtual_buckets: { no_workspace: { id: null, label: "No workspace", agent_count: 1 } },
      total_agent_count: 1,
    });
  }
  if (pathname === `${cp}/dashboard/schedules`) {
    return send(res, 200, {
      items: [routine],
      page: { limit: 25, offset: 0, returned: 1, next_offset: null, has_more: false },
    });
  }
  if (pathname.startsWith(`${cp}/dashboard/`)) return send(res, 200, []);
  if (pathname === "/api/runtime/schedules/preview") return send(res, 200, preview);
  if (pathname === "/api/runtime/schedules/7") return send(res, 200, detail);
  return send(res, 200, { items: [] });
}

function handleWrite(req, res, pathname) {
  if (req.method === "POST" && pathname === `${cp}/auth/login`) {
    return send(res, 200, { session_token: sessionToken, auth: authOk, operator });
  }
  if (pathname.startsWith("/api/runtime/schedules")) return send(res, 200, { ok: true, ...detail });
  return send(res, 200, { ok: true });
}

http
  .createServer((req, res) => {
    const pathname = new URL(req.url ?? "/", runtimeBaseUrl).pathname;
    req.resume();
    req.on("end", () => {
      if (req.method === "GET" || req.method === "HEAD") handleGet(req, res, pathname);
      else handleWrite(req, res, pathname);
    });
  })
  .listen(port, "127.0.0.1", () => {
    console.log(`stub control plane on ${runtimeBaseUrl}`);
  });
