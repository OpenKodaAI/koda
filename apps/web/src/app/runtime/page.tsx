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
  searchParams: Promise<{ agent?: string | string[]; mock?: string | string[] }>;
}) {
  const { agent, mock } = await searchParams;
  const initialBotIds = Array.isArray(agent) ? agent : agent ? [agent] : undefined;
  const mockMode = Array.isArray(mock) ? mock.includes("1") || mock.includes("true") : mock === "1" || mock === "true";
  return <RuntimeOverviewScreen initialBotIds={initialBotIds} mock={mockMode} />;
}
