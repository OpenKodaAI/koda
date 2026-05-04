"use client";

import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { mutateControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import {
  blockSubmitBodySchema,
  type BlockSubmitBody,
} from "@/lib/contracts/sessions";

interface UseBlockSubmitArgs {
  agentId: string | null | undefined;
  sessionId: string | null | undefined;
  blockId: string;
}

interface UseBlockSubmitResult {
  submit: (body: BlockSubmitBody) => Promise<unknown | null>;
  isPending: boolean;
  isSubmitted: boolean;
  error: string | null;
}

/**
 * Submit user input from a generative-UI block to the agent. Uses an in-flight
 * lock keyed on `blockId` to prevent double-submits, and marks `isSubmitted`
 * after a successful response so the renderer can disable the form locally
 * (optimistic state) until the server replies with the next message.
 */
export function useBlockSubmit({
  agentId,
  sessionId,
  blockId,
}: UseBlockSubmitArgs): UseBlockSubmitResult {
  const queryClient = useQueryClient();
  const [isPending, setIsPending] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inflightRef = useRef(false);

  const submit = useCallback(
    async (body: BlockSubmitBody): Promise<unknown | null> => {
      if (!agentId || !sessionId) {
        setError("Missing agent or session id");
        return null;
      }
      if (inflightRef.current || isSubmitted) {
        return null;
      }
      const parsed = blockSubmitBodySchema.safeParse(body);
      if (!parsed.success) {
        setError(parsed.error.issues[0]?.message ?? "Invalid form payload");
        return null;
      }

      inflightRef.current = true;
      setIsPending(true);
      setError(null);
      try {
        const response = await mutateControlPlaneDashboardJson<unknown>(
          `/agents/${encodeURIComponent(agentId)}/sessions/${encodeURIComponent(
            sessionId,
          )}/blocks/${encodeURIComponent(blockId)}/submit`,
          {
            body: parsed.data,
            method: "POST",
            fallbackError: "Unable to submit",
          },
        );

        setIsSubmitted(true);
        void queryClient.invalidateQueries({
          queryKey: queryKeys.dashboard.sessionDetail(agentId, sessionId),
        });
        return response;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unable to submit";
        setError(message);
        return null;
      } finally {
        inflightRef.current = false;
        setIsPending(false);
      }
    },
    [agentId, blockId, isSubmitted, queryClient, sessionId],
  );

  return { submit, isPending, isSubmitted, error };
}
