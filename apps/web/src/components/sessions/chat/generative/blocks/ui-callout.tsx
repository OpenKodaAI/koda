"use client";

import { Button } from "@/components/ui/button";
import { InlineAlert } from "@/components/ui/inline-alert";
import { SessionRichText } from "@/components/sessions/session-rich-text";
import type { z } from "zod";
import type { uiCalloutBlockSchema } from "@/lib/contracts/generative-ui";

export type UiCalloutBlock = z.infer<typeof uiCalloutBlockSchema>;

export interface UiCalloutProps {
  block: UiCalloutBlock;
  onAction?: (actionId: string) => void;
}

export function UiCallout({ block, onAction }: UiCalloutProps) {
  const { tone, title, body, action } = block.payload;

  return (
    <InlineAlert
      tone={tone}
      action={
        action ? (
          <Button size="sm" variant="ghost" onClick={() => onAction?.(action.id)}>
            {action.label}
          </Button>
        ) : null
      }
    >
      {title ? <p className="m-0 font-medium">{title}</p> : null}
      <div className={title ? "mt-1" : ""}>
        <SessionRichText content={body} variant="assistant" />
      </div>
    </InlineAlert>
  );
}
