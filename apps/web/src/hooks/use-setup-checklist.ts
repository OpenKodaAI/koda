"use client";

import { keepPreviousData } from "@tanstack/react-query";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import type { SetupChecklistSnapshot } from "@/components/dashboard/setup-checklist-card";

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
};

export function useSetupChecklist(): {
  snapshot: SetupChecklistSnapshot;
  isLoading: boolean;
} {
  const query = useControlPlaneQuery<OnboardingResponse, SetupChecklistSnapshot>({
    queryKey: ["control-plane", "onboarding-status"] as const,
    queryFn: async () => {
      const res = await fetch("/api/control-plane/onboarding/status", {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!res.ok) {
        throw new Error(`onboarding/status returned ${res.status}`);
      }
      return (await res.json()) as OnboardingResponse;
    },
    select: (payload) => ({
      providerReady: (payload.providers ?? []).some((p) => Boolean(p.verified)),
      agentReady: (payload.agents ?? []).length > 0,
      telegramReady: (payload.agents ?? []).some((a) =>
        Boolean(a.telegram_token_configured),
      ),
    }),
    placeholderData: keepPreviousData,
    notifyOnChangeProps: ["data", "error"],
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    refetchInterval: 30_000,
  });

  return {
    snapshot: query.data ?? EMPTY_SNAPSHOT,
    isLoading: query.isLoading && !query.data,
  };
}
