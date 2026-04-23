"use client";

import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { mutateControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import type { ApprovalDecision, PendingApproval } from "@/lib/contracts/sessions";

interface UseApprovalActionArgs {
  agentId: string | null | undefined;
  sessionId: string | null | undefined;
}

interface SubmitArgs {
  approvalId: string;
  decision: ApprovalDecision;
  rationale?: string | null;
}

interface UseApprovalActionResult {
  submit: (args: SubmitArgs) => Promise<PendingApproval | null>;
  isPending: boolean;
  error: string | null;
}

export function useApprovalAction({
  agentId,
  sessionId,
}: UseApprovalActionArgs): UseApprovalActionResult {
  const queryClient = useQueryClient();
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(
    async ({
      approvalId,
      decision,
      rationale,
    }: SubmitArgs): Promise<PendingApproval | null> => {
      if (!agentId) {
        setError("missing bot id");
        return null;
      }

      setIsPending(true);
      setError(null);
      try {
        const response = await mutateControlPlaneDashboardJson<{
          approval: PendingApproval;
        }>(`/agents/${encodeURIComponent(agentId)}/approvals/${encodeURIComponent(approvalId)}`, {
          body: { decision, rationale: rationale ?? null },
          method: "POST",
          fallbackError: "Unable to resolve approval",
        });

        if (sessionId) {
          void queryClient.invalidateQueries({
            queryKey: queryKeys.dashboard.sessionDetail(agentId, sessionId),
          });
        }

        return response?.approval ?? null;
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Unable to resolve approval";
        setError(message);
        return null;
      } finally {
        setIsPending(false);
      }
    },
    [agentId, sessionId, queryClient],
  );

  return { submit, isPending, error };
}
