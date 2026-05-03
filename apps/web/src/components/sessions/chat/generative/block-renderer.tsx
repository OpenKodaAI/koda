"use client";

import { useMemo } from "react";
import {
  generativeBlockSchema,
  parseGenerativeBlockEnvelope,
  type GenerativeBlock,
} from "@/lib/contracts/generative-ui";
import { BlockSkeleton } from "@/components/sessions/chat/generative/block-skeleton";
import { UnsupportedBlock } from "@/components/sessions/chat/generative/unsupported-block";
import { UiCard } from "@/components/sessions/chat/generative/blocks/ui-card";
import { UiCallout } from "@/components/sessions/chat/generative/blocks/ui-callout";
import { UiChart } from "@/components/sessions/chat/generative/blocks/ui-chart";
import { UiChoice } from "@/components/sessions/chat/generative/blocks/ui-choice";
import { UiForm } from "@/components/sessions/chat/generative/blocks/ui-form";
import { UiSteps } from "@/components/sessions/chat/generative/blocks/ui-steps";
import { UiTable } from "@/components/sessions/chat/generative/blocks/ui-table";

export interface BlockRendererProps {
  /** Raw payload from the stream (or persisted in SessionMessage.blocks). */
  raw: unknown;
  /** Fired when a block emits an action — only used by interactive variants. */
  onAction?: (blockId: string, actionId: string) => void;
  /** Forwarded to interactive blocks so they know where to POST the submit. */
  agentId?: string | null;
  sessionId?: string | null;
}

function dispatchBlock(
  block: GenerativeBlock,
  onAction: BlockRendererProps["onAction"],
  agentId: string | null | undefined,
  sessionId: string | null | undefined,
) {
  const emit = onAction
    ? (actionId: string) => onAction(block.id, actionId)
    : undefined;
  switch (block.block_type) {
    case "ui_card":
      return <UiCard block={block} onAction={emit} />;
    case "ui_callout":
      return <UiCallout block={block} onAction={emit} />;
    case "ui_steps":
      return <UiSteps block={block} />;
    case "ui_table":
      return <UiTable block={block} />;
    case "ui_chart":
      return <UiChart block={block} />;
    case "ui_form":
      return <UiForm block={block} agentId={agentId} sessionId={sessionId} />;
    case "ui_choice":
      return <UiChoice block={block} agentId={agentId} sessionId={sessionId} />;
    default: {
      const exhaustive: never = block;
      void exhaustive;
      return <UnsupportedBlock blockType="unknown" />;
    }
  }
}

export function BlockRenderer({ raw, onAction, agentId, sessionId }: BlockRendererProps) {
  const envelope = useMemo(() => parseGenerativeBlockEnvelope(raw), [raw]);
  const parseResult = useMemo(
    () => generativeBlockSchema.safeParse(raw),
    [raw],
  );

  if (envelope?.state === "streaming") {
    return <BlockSkeleton kind={envelope.block_type} />;
  }

  if (envelope?.state === "error") {
    return <UnsupportedBlock blockType={envelope.block_type} raw={raw} />;
  }

  if (!parseResult.success) {
    return <UnsupportedBlock blockType={envelope?.block_type} raw={raw} />;
  }

  return dispatchBlock(parseResult.data, onAction, agentId, sessionId);
}
