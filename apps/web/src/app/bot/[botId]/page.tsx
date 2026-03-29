import { redirect } from "next/navigation";
import {
  ControlPlaneRequestError,
  getControlPlaneBot,
} from "@/lib/control-plane";

export default async function BotRedirectPage({
  params,
}: {
  params: Promise<{ botId: string }>;
}) {
  const { botId } = await params;

  try {
    await getControlPlaneBot(botId);
  } catch (error) {
    if (error instanceof ControlPlaneRequestError && error.status === 404) {
      redirect("/");
    }
    throw error;
  }

  redirect(`/?bot=${botId}`);
}
