import SquadThreadPageClient from "@/components/features/squads/squad-thread-page-client";

type Params = { threadId: string };

export default async function SquadThreadPage({ params }: { params: Promise<Params> }) {
  const { threadId } = await params;
  return <SquadThreadPageClient threadId={threadId} />;
}
