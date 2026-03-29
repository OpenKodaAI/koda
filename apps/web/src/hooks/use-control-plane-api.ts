"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAsyncAction } from "@/hooks/use-async-action";
import { requestJson, requestJsonAllowError } from "@/lib/http-client";

export function useControlPlaneApi() {
  const router = useRouter();
  const { runAction, isPending, getStatus, pendingKeys } = useAsyncAction();

  const withBusy = useCallback(
    async <T>(
      key: string,
      asyncFn: () => Promise<T>,
      successMessage?: string,
    ): Promise<T | undefined> => {
      return runAction(key, asyncFn, {
        successMessage: successMessage ?? "Operation completed successfully",
        onSuccess: async () => {
          router.refresh();
        },
      });
    },
    [router, runAction],
  );

  return {
    requestJson,
    requestJsonAllowError,
    busyKey: pendingKeys[0] ?? null,
    withBusy,
    isPending,
    getStatus,
  };
}
