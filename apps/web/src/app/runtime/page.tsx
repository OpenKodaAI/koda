import dynamic from "next/dynamic";
import { RuntimeRouteLoading } from "@/components/layout/route-loading";

const RuntimeOverviewScreen = dynamic(
  () =>
    import("@/components/runtime/runtime-overview").then((module) => ({
      default: module.RuntimeOverviewScreen,
    })),
  {
    loading: () => <RuntimeRouteLoading />,
  },
);

export default async function RuntimePage({
  searchParams,
}: {
  searchParams: Promise<{ bot?: string | string[] }>;
}) {
  const { bot } = await searchParams;
  const initialBotIds = Array.isArray(bot) ? bot : bot ? [bot] : undefined;
  return <RuntimeOverviewScreen initialBotIds={initialBotIds} />;
}
