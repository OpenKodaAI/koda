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
  searchParams: Promise<{ agent?: string | string[] }>;
}) {
  const { agent } = await searchParams;
  const initialBotIds = Array.isArray(agent) ? agent : agent ? [agent] : undefined;
  return <RuntimeOverviewScreen initialBotIds={initialBotIds} />;
}
