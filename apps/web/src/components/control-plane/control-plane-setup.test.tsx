import type { ComponentProps } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ControlPlaneSetup } from "@/components/control-plane/control-plane-setup";
import type {
  ControlPlaneAuthStatus,
  ControlPlaneOnboardingStatus,
} from "@/lib/control-plane";

const refreshMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock }),
}));

function renderSetup(props: ComponentProps<typeof ControlPlaneSetup>) {
  return render(
    <I18nProvider initialLanguage="pt-BR">
      <ControlPlaneSetup {...props} />
    </I18nProvider>,
  );
}

function makeStatus(): ControlPlaneOnboardingStatus {
  return {
    control_plane: {
      ready: true,
    },
    storage: {
      database: {
        ready: true,
        reason: "postgres ready",
      },
      object_storage: {
        ready: true,
        reason: "bucket ready",
      },
    },
    providers: [
      {
        provider_id: "claude",
        title: "Anthropic",
        supported_auth_modes: ["api_key"],
        configured: false,
        verified: false,
        connection_status: {},
      },
    ],
    agents: [],
    system: {
      owner_name: "Larissa",
      owner_email: "larissa@example.com",
      owner_github: "larissamiyoshi",
      default_provider: "claude",
      allowed_user_ids: [],
    },
    steps: {
      provider_configured: false,
      access_configured: false,
      agent_ready: false,
      storage_ready: true,
      onboarding_complete: false,
    },
    openapi_url: "/openapi/control-plane.json",
    setup_url: "/setup",
  };
}

function makeAuthStatus(overrides: Partial<ControlPlaneAuthStatus> = {}): ControlPlaneAuthStatus {
  return {
    authenticated: false,
    has_owner: false,
    bootstrap_required: true,
    auth_mode: "local_account",
    session_required: false,
    recovery_available: true,
    session_subject: null,
    operator: null,
    ...overrides,
  };
}

describe("ControlPlaneSetup", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    refreshMock.mockReset();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("exchanges a setup code and advances to owner registration", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          registration_token: "kodar_example",
          expires_at: "2026-04-05T10:00:00+00:00",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    globalThis.fetch = fetchMock as typeof fetch;

    renderSetup({
      initialStatus: makeStatus(),
      authStatus: makeAuthStatus(),
    });

    await user.type(screen.getByLabelText(/setup code/i), "abcd-efgh-jklm");
    await user.click(screen.getByRole("button", { name: /continue with setup code/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/control-plane/auth/bootstrap/exchange");
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      code: "ABCD-EFGH-JKLM",
    });

    expect(await screen.findByRole("heading", { name: /create the local owner account/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/^username$/i)).toBeInTheDocument();
  });

  it("registers the owner account and refreshes the route", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          auth: makeAuthStatus({
            authenticated: true,
            has_owner: true,
            bootstrap_required: false,
            session_required: true,
            operator: {
              display_name: "Larissa",
              username: "larissa",
              email: "larissa@example.com",
            },
          }),
          operator: {
            display_name: "Larissa",
            username: "larissa",
            email: "larissa@example.com",
          },
        }),
        {
          status: 201,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    globalThis.fetch = fetchMock as typeof fetch;

    renderSetup({
      initialStatus: makeStatus(),
      authStatus: makeAuthStatus(),
      initialRegistrationToken: "kodar_example",
      initialRegistrationExpiresAt: "2026-04-05T10:00:00+00:00",
    });

    await screen.findByRole("heading", { name: /create the local owner account/i });

    await user.type(screen.getByLabelText(/^username$/i), "larissa");
    await user.clear(screen.getByLabelText(/^email$/i));
    await user.type(screen.getByLabelText(/^email$/i), "larissa@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "supersecret");
    await user.click(screen.getByRole("button", { name: /create owner account/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/control-plane/auth/register-owner");
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toMatchObject({
      registration_token: "kodar_example",
      username: "larissa",
      email: "larissa@example.com",
      password: "supersecret",
    });
    await waitFor(() => expect(refreshMock).toHaveBeenCalledTimes(1));
  });

  it("signs in with the local owner account", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          auth: makeAuthStatus({
            authenticated: true,
            has_owner: true,
            bootstrap_required: false,
            session_required: true,
            operator: {
              display_name: "Larissa",
              username: "larissa",
              email: "larissa@example.com",
            },
          }),
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    globalThis.fetch = fetchMock as typeof fetch;

    renderSetup({
      initialStatus: makeStatus(),
      authStatus: makeAuthStatus({
        has_owner: true,
        bootstrap_required: false,
        session_required: true,
      }),
    });

    await user.type(screen.getByLabelText(/username or email/i), "larissa@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "supersecret");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/control-plane/auth/login");
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      identifier: "larissa@example.com",
      password: "supersecret",
    });
    await waitFor(() => expect(refreshMock).toHaveBeenCalledTimes(1));
  });

  it("submits first-run configuration without forcing agent creation", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(input).toBe("/api/control-plane/onboarding/bootstrap");
      return new Response(
        JSON.stringify({
          ok: true,
          status: {
            ...makeStatus(),
            has_owner: true,
            steps: {
              provider_configured: true,
              access_configured: true,
              agent_ready: false,
              storage_ready: true,
              onboarding_complete: true,
            },
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    });
    globalThis.fetch = fetchMock as typeof fetch;

    renderSetup({
      initialStatus: makeStatus(),
      authStatus: makeAuthStatus({
        authenticated: true,
        has_owner: true,
        bootstrap_required: false,
        session_required: true,
        operator: {
          display_name: "Larissa",
          username: "larissa",
          email: "larissa@example.com",
        },
      }),
    });

    await user.type(screen.getByLabelText(/allowed telegram user ids/i), "123456789");
    await user.type(screen.getByLabelText(/^api key$/i), "sk-ant-test");
    await user.click(
      screen.getByRole("button", { name: /apply setup and open the control plane/i }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const requestBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(requestBody.access).toEqual({ allowed_user_ids: "123456789" });
    expect(requestBody.provider).toMatchObject({
      provider_id: "claude",
      auth_mode: "api_key",
      api_key: "sk-ant-test",
    });
    expect(requestBody.agent).toEqual({});
    await waitFor(() => expect(refreshMock).toHaveBeenCalledTimes(1));
  });
});
