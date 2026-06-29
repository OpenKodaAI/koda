"use client";

import { keepPreviousData } from "@tanstack/react-query";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useStableQueryData } from "@/hooks/use-stable-query-data";
import type { SetupChecklistSnapshot } from "@/components/dashboard/setup-checklist-card";
import {
  onboardingReadinessSchema,
  type OnboardingReadiness,
} from "@/lib/contracts/onboarding-readiness";

interface OnboardingProvider {
  configured?: boolean;
  verified?: boolean;
}

interface OnboardingAgent {
  id?: string;
  telegram_token_configured?: boolean;
}

interface OnboardingResponse {
  providers?: OnboardingProvider[];
  agents?: OnboardingAgent[];
  status?: string;
}

const EMPTY_SNAPSHOT: SetupChecklistSnapshot = {
  providerReady: false,
  agentReady: false,
  telegramReady: false,
  channelReady: false,
  firstTaskReady: false,
  firstTraceReady: false,
  readinessStatus: "pending",
  primaryAgentId: "",
  readinessActions: [],
};

export function useSetupChecklist(): {
  snapshot: SetupChecklistSnapshot;
  isLoading: boolean;
} {
  const query = useControlPlaneQuery<OnboardingResponse & { readiness?: OnboardingReadiness }, SetupChecklistSnapshot>({
    queryKey: ["control-plane", "onboarding-readiness"] as const,
    queryFn: async () => {
      const [statusRes, readinessRes] = await Promise.all([
        fetch("/api/control-plane/onboarding/status", {
          credentials: "same-origin",
          cache: "no-store",
        }),
        fetch("/api/control-plane/onboarding/readiness", {
          credentials: "same-origin",
          cache: "no-store",
        }),
      ]);
      if (!statusRes.ok) {
        throw new Error(`onboarding/status returned ${statusRes.status}`);
      }
      const status = (await statusRes.json()) as OnboardingResponse;
      if (!readinessRes.ok) {
        return status;
      }
      const readinessPayload = await readinessRes.json();
      const parsed = onboardingReadinessSchema.safeParse(readinessPayload);
      return { ...status, readiness: parsed.success ? parsed.data : undefined };
    },
    select: (payload) => {
      const readiness = payload.readiness;
      const checks = readiness?.checks ?? [];
      const byKey = Object.fromEntries(checks.map((check) => [check.key, check.status]));
      return {
        providerReady: (payload.providers ?? []).some((p) => Boolean(p.verified)),
        agentReady: (payload.agents ?? []).length > 0,
        telegramReady: (payload.agents ?? []).some((a) =>
          Boolean(a.telegram_token_configured),
        ),
        channelReady: byKey.channel === "passed",
        firstTaskReady: byKey.first_task === "passed",
        firstTraceReady: byKey.first_trace === "passed",
        readinessStatus: readiness?.status ?? "pending",
        primaryAgentId: readiness?.primary_agent_id ?? "",
        readinessActions: readiness?.actions ?? [],
      };
    },
    placeholderData: keepPreviousData,
    notifyOnChangeProps: ["data", "error"],
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    refetchInterval: 30_000,
  });

  const stable = useStableQueryData<SetupChecklistSnapshot>({
    data: query.data,
    resetKey: "setup-checklist",
    isPending: query.isPending,
    isFetching: query.isFetching,
    error: query.error,
  });

  return {
    snapshot: stable.data ?? EMPTY_SNAPSHOT,
    isLoading: stable.initialLoading,
  };
}
