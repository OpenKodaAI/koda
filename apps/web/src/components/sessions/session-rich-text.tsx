"use client";

import { Children, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import {
  RoomAgentMentionBadge,
  splitRoomAgentMentions,
  type RoomAgentMentionMeta,
} from "@/components/sessions/chat/room-agent-mention";
import { ExternalLink } from "@/components/ui/external-link";
import { cn } from "@/lib/utils";

interface SessionRichTextProps {
  content: string;
  className?: string;
  variant?: "assistant" | "user";
  mentionsByToken?: ReadonlyMap<string, RoomAgentMentionMeta>;
  mentionVariant?: "badge" | "inline";
}

type MentionRenderOptions = {
  mentionsByToken: ReadonlyMap<string, RoomAgentMentionMeta>;
  variant: "badge" | "inline";
};

function normalizeMarkdownFragment(content: string) {
  return content
    .replace(/([a-z0-9áàâãéêíóôõúç])([.!?])(?=([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]))/g, "$1$2 $3")
    .replace(/([^\s])(\*\*[^*\n]{1,80}:\*\*)/g, "$1\n\n$2")
    .replace(/([^\s])(__[^_\n]{1,80}:__)/g, "$1\n\n$2")
    .replace(/([^\n])\s+(\d{1,2}\.\s+[`*_A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇ])/g, "$1\n$2")
    .replace(/([^\n])\s+(#{1,6}\s)/g, "$1\n\n$2")
    .replace(/(#{1,6}[^\n*|]+?)\s+(\*\*[^*]+:\*\*)/g, "$1\n\n- $2")
    .replace(/(#{1,6}[^\n|]+?)\s+(\|(?:[^|\n]+\|){2,})/g, "$1\n\n$2")
    .replace(/(#{1,6}[^\n]+?)\s+-\s+/g, "$1\n- ")
    .replace(/\s+---\s+(#{1,6}\s)/g, "\n\n---\n\n$1")
    .replace(/\|\s+\|/g, "|\n|")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function normalizeSessionMarkdown(content: string) {
  return content
    .replace(/\r\n/g, "\n")
    .replace(/\u00a0/g, " ")
    .split(/(```[\s\S]*?```)/g)
    .map((part) => (part.startsWith("```") ? part : normalizeMarkdownFragment(part)))
    .join("\n\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function renderMentionText(
  text: string,
  options: MentionRenderOptions,
  keyPrefix: string,
): ReactNode {
  const segments = splitRoomAgentMentions(text, options.mentionsByToken);
  return segments.map((segment, index) => {
    if (segment.kind === "text") {
      return segment.text;
    }
    if (options.variant === "inline") {
      return (
        <span
          key={`${keyPrefix}-mention-${segment.mention.id}-${index}`}
          className="font-medium text-[var(--tone-info-dot)]"
        >
          {segment.raw}
        </span>
      );
    }
    return (
      <RoomAgentMentionBadge
        key={`${keyPrefix}-mention-${segment.mention.id}-${index}`}
        mention={segment.mention}
        className="mx-0.5 translate-y-[-1px]"
      />
    );
  });
}

function renderMentionChildren(
  children: ReactNode,
  options: MentionRenderOptions | null,
  keyPrefix: string,
): ReactNode {
  if (!options) return children;
  return Children.map(children, (child, index) => {
    if (typeof child === "string") {
      return renderMentionText(child, options, `${keyPrefix}-${index}`);
    }
    return child;
  });
}

function createMarkdownComponents(options: MentionRenderOptions | null): Components {
  return {
    a: ({ href, children, ...props }) => (
      <ExternalLink href={href ?? "#"} {...props}>
        {children}
      </ExternalLink>
    ),
    table: ({ children }) => (
      <div className="session-richtext__table-wrap">
        <table>{children}</table>
      </div>
    ),
    p: ({ children }) => (
      <p>{renderMentionChildren(children, options, "p")}</p>
    ),
    li: ({ children }) => (
      <li>{renderMentionChildren(children, options, "li")}</li>
    ),
    h1: ({ children }) => (
      <h1>{renderMentionChildren(children, options, "h1")}</h1>
    ),
    h2: ({ children }) => (
      <h2>{renderMentionChildren(children, options, "h2")}</h2>
    ),
    h3: ({ children }) => (
      <h3>{renderMentionChildren(children, options, "h3")}</h3>
    ),
    h4: ({ children }) => (
      <h4>{renderMentionChildren(children, options, "h4")}</h4>
    ),
    h5: ({ children }) => (
      <h5>{renderMentionChildren(children, options, "h5")}</h5>
    ),
    h6: ({ children }) => (
      <h6>{renderMentionChildren(children, options, "h6")}</h6>
    ),
    th: ({ children, align }) => (
      <th align={align}>{renderMentionChildren(children, options, "th")}</th>
    ),
    td: ({ children, align }) => (
      <td align={align}>{renderMentionChildren(children, options, "td")}</td>
    ),
  };
}

export function SessionRichText({
  content,
  className,
  variant = "assistant",
  mentionsByToken,
  mentionVariant = "badge",
}: SessionRichTextProps) {
  const mentionOptions =
    mentionsByToken && mentionsByToken.size > 0
      ? { mentionsByToken, variant: mentionVariant }
      : null;
  return (
    <div
      className={cn(
        "session-richtext",
        variant === "user" && "session-richtext--user",
        className
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={createMarkdownComponents(mentionOptions)}
      >
        {normalizeSessionMarkdown(content)}
      </ReactMarkdown>
    </div>
  );
}
