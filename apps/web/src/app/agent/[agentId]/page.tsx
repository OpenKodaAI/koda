import { redirect } from "next/navigation";
import {
  ControlPlaneRequestError,
  getControlPlaneAgent,
} from "@/lib/control-plane";

export default async function AgentRedirectPage({
  params,
}: {
  params: Promise<{ agentId: string }>;
}) {
  const { agentId: agentId } = await params;

  try {
    await getControlPlaneAgent(agentId);
  } catch (error) {
    if (error instanceof ControlPlaneRequestError && error.status === 404) {
      redirect("/");
    }
    throw error;
  }

  redirect(`/?agent=${agentId}`);
}
