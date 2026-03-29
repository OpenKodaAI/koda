import { RuntimeTaskRoom } from "@/components/runtime/runtime-task-room";

export default async function RuntimeTaskPage({
  params,
}: {
  params: Promise<{ botId: string; taskId: string }>;
}) {
  const { botId, taskId } = await params;
  return <RuntimeTaskRoom botId={botId} taskId={Number(taskId)} />;
}
