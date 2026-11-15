/**
 * Create and clone answer 409 when the agent id is already taken, also after
 * the control plane normalises it (`my-agent` and `My Agent` are both
 * `MY_AGENT`). The dashboard lets the server pick ids, so this is rare, and
 * the screens show it with `controlPlane.agent.idConflict`.
 */
export function isAgentIdConflict(error: unknown): boolean {
  return (error as { status?: unknown } | null)?.status === 409;
}
