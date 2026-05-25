import EvaluationsPageClient from "@/components/features/evaluations/evaluations-page-client";

export default async function EvaluationsPage({
  searchParams,
}: {
  searchParams: Promise<{ agent?: string | string[] }>;
}) {
  const { agent } = await searchParams;
  const initialAgentId = Array.isArray(agent) ? agent[0] : agent;
  return <EvaluationsPageClient initialAgentId={initialAgentId} />;
}
