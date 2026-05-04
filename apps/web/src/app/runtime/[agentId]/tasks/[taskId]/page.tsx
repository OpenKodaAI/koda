import { RuntimeTaskRoom } from "@/components/runtime/runtime-task-room";

export default async function RuntimeTaskPage({
  params,
  searchParams,
}: {
  params: Promise<{ agentId: string; taskId: string }>;
  searchParams: Promise<{ mock?: string | string[] }>;
}) {
  const { agentId: agentId, taskId } = await params;
  const { mock } = await searchParams;
  const mockMode = Array.isArray(mock) ? mock.includes("1") || mock.includes("true") : mock === "1" || mock === "true";
  return <RuntimeTaskRoom agentId={agentId} taskId={Number(taskId)} mock={mockMode} />;
}
