export const agentBoardAssets = {
  workspaceFolder: "/agent-board/workspace-folder.svg",
  actionSpark: "/agent-board/action-spark.svg",
  boardDoc: "/agent-board/board-doc.svg",
  signalStack: "/agent-board/signal-stack.svg",
  teamLink: "/agent-board/team-link.svg",
  sendMark: "/agent-board/send-mark.svg",
  plus: "/agent-board/squad-plus.svg",
} as const;

export type AgentBoardAssetKey = keyof typeof agentBoardAssets;
