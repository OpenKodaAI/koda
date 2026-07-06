"use client";

import {
  type QueryFunction,
  useMutation,
  useQuery,
  useQueryClient,
  type InvalidateQueryFilters,
  type QueryKey,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { toAppError } from "@/lib/errors";
import { getTierQueryOptions, type QueryTier } from "@/lib/query/options";

type AppQueryOptions<
  TQueryFnData,
  TData = TQueryFnData,
  TQueryKey extends QueryKey = QueryKey,
> = Omit<UseQueryOptions<TQueryFnData, Error, TData, TQueryKey>, "queryKey" | "queryFn"> & {
  queryKey: TQueryKey;
  queryFn: QueryFunction<TQueryFnData, TQueryKey>;
  tier?: QueryTier;
};

type InvalidateTarget = QueryKey | InvalidateQueryFilters;

function normalizeInvalidateTarget(target: InvalidateTarget): InvalidateQueryFilters {
  if (Array.isArray(target)) {
    return { queryKey: target };
  }

  return target as InvalidateQueryFilters;
}

export function useControlPlaneQuery<
  TQueryFnData,
  TData = TQueryFnData,
  TQueryKey extends QueryKey = QueryKey,
>({
  tier = "detail",
  queryFn,
  ...options
}: AppQueryOptions<TQueryFnData, TData, TQueryKey>) {
  return useQuery<TQueryFnData, Error, TData, TQueryKey>({
    ...getTierQueryOptions(tier),
    ...options,
    queryFn: async (context) => {
      try {
        return await queryFn(context);
      } catch (error) {
        throw toAppError(error);
      }
    },
  });
}

export function useRuntimeQuery<
  TQueryFnData,
  TData = TQueryFnData,
  TQueryKey extends QueryKey = QueryKey,
>(options: AppQueryOptions<TQueryFnData, TData, TQueryKey>) {
  return useControlPlaneQuery({
    tier: "live",
    ...options,
  });
}

type AppMutationOptions<TData, TVariables, TContext> = UseMutationOptions<
  TData,
  Error,
  TVariables,
  TContext
> & {
  invalidate?: InvalidateTarget[];
};

export function useAppMutation<TData = unknown, TVariables = void, TContext = unknown>({
  invalidate = [],
  mutationFn,
  onSuccess,
  ...options
}: AppMutationOptions<TData, TVariables, TContext>) {
  const queryClient = useQueryClient();

  return useMutation<TData, Error, TVariables, TContext>({
    ...options,
    mutationFn: async (variables, context) => {
      try {
        return await mutationFn!(variables, context);
      } catch (error) {
        throw toAppError(error);
      }
    },
    onSuccess: async (data, variables, context, meta) => {
      if (invalidate.length > 0) {
        await Promise.all(
          invalidate.map((target) =>
            queryClient.invalidateQueries(normalizeInvalidateTarget(target)),
          ),
        );
      }

      await onSuccess?.(data, variables, context, meta);
    },
  });
}
