import SquadDetailPageClient from "@/components/features/squads/squad-detail-page-client";

type Params = { squadId: string };

export default async function SquadDetailPage({ params }: { params: Promise<Params> }) {
  const { squadId } = await params;
  return <SquadDetailPageClient squadId={squadId} />;
}
