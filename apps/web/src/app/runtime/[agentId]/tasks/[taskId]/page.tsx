import { RuntimeTaskRoom } from "@/components/runtime/runtime-task-room";

export default async function RuntimeTaskPage({
  params,
}: {
  params: Promise<{ agentId: string; taskId: string }>;
}) {
  const { agentId: agentId, taskId } = await params;
  return <RuntimeTaskRoom agentId={agentId} taskId={Number(taskId)} />;
}
