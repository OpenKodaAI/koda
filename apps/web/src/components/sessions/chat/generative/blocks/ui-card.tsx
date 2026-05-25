"use client";

import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SessionRichText } from "@/components/sessions/session-rich-text";
import type { z } from "zod";
import type { uiCardBlockSchema } from "@/lib/contracts/generative-ui";

export type UiCardBlock = z.infer<typeof uiCardBlockSchema>;

export interface UiCardProps {
  block: UiCardBlock;
  onAction?: (actionId: string) => void;
}

export function UiCard({ block, onAction }: UiCardProps) {
  const { eyebrow, title, body, media, footer_actions } = block.payload;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col">
          {eyebrow ? (
            <span className="font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono,0.12em)] text-[var(--text-quaternary)] mb-0.5">
              {eyebrow}
            </span>
          ) : null}
          <CardTitle>{title}</CardTitle>
        </div>
      </CardHeader>
      {(media || body) && (
        <CardContent>
          {media ? (
            // Generative-UI media is dynamic external content; next/image's
            // remote-loader allowlist would block arbitrary hosts emitted by
            // the agent, so a plain <img> is correct here.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={media.src}
              alt={media.alt}
              className="mb-3 w-full rounded-[var(--radius-chip)] border border-[color:var(--border-subtle)]"
            />
          ) : null}
          {body ? (
            <div className="text-[var(--font-size-md)] leading-[1.55] text-[var(--text-primary)]">
              <SessionRichText content={body} variant="assistant" />
            </div>
          ) : null}
        </CardContent>
      )}
      {footer_actions && footer_actions.length > 0 ? (
        <CardFooter className="gap-2 justify-end">
          {footer_actions.map((action) => {
            if (action.action.kind === "link") {
              return (
                <a
                  key={action.id}
                  href={action.action.href}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-panel-sm)] px-3 text-[0.8125rem] text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
                >
                  {action.label}
                </a>
              );
            }
            const variant =
              action.tone === "accent"
                ? "accent"
                : action.tone === "primary"
                  ? "primary"
                  : "ghost";
            return (
              <Button
                key={action.id}
                size="sm"
                variant={variant}
                onClick={() => onAction?.(action.id)}
              >
                {action.label}
              </Button>
            );
          })}
        </CardFooter>
      ) : null}
    </Card>
  );
}
