"use client";

import { Children, createContext, type ReactNode, useContext, useMemo } from "react";
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

// The mention options reach the markdown components through context, so the components
// themselves are created once. ReactMarkdown renders each element with the component given
// for its tag; a component created during render is a new type every time, and React would
// then replace every paragraph, list item, heading, cell and link of the message on each
// re-render of the thread.
const MentionOptionsContext = createContext<MentionRenderOptions | null>(null);

function WithMentions({ tag, children }: { tag: string; children: ReactNode }) {
  const options = useContext(MentionOptionsContext);
  return <>{renderMentionChildren(children, options, tag)}</>;
}

const MARKDOWN_COMPONENTS: Components = {
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
    <p>
      <WithMentions tag="p">{children}</WithMentions>
    </p>
  ),
  li: ({ children }) => (
    <li>
      <WithMentions tag="li">{children}</WithMentions>
    </li>
  ),
  // A message sits under the page's h1, so its headings render one level
  // down (M8-E1-T3); the class keeps the size of the markdown level.
  h1: ({ children }) => (
    <h2 className="session-richtext__h1">
      <WithMentions tag="h1">{children}</WithMentions>
    </h2>
  ),
  h2: ({ children }) => (
    <h3 className="session-richtext__h2">
      <WithMentions tag="h2">{children}</WithMentions>
    </h3>
  ),
  h3: ({ children }) => (
    <h4 className="session-richtext__h3">
      <WithMentions tag="h3">{children}</WithMentions>
    </h4>
  ),
  h4: ({ children }) => (
    <h5 className="session-richtext__h4">
      <WithMentions tag="h4">{children}</WithMentions>
    </h5>
  ),
  h5: ({ children }) => (
    <h6 className="session-richtext__h5">
      <WithMentions tag="h5">{children}</WithMentions>
    </h6>
  ),
  h6: ({ children }) => (
    <h6 className="session-richtext__h6">
      <WithMentions tag="h6">{children}</WithMentions>
    </h6>
  ),
  th: ({ children, align }) => (
    <th align={align}>
      <WithMentions tag="th">{children}</WithMentions>
    </th>
  ),
  td: ({ children, align }) => (
    <td align={align}>
      <WithMentions tag="td">{children}</WithMentions>
    </td>
  ),
};

const REMARK_PLUGINS = [remarkGfm, remarkBreaks];

export function SessionRichText({
  content,
  className,
  variant = "assistant",
  mentionsByToken,
  mentionVariant = "badge",
}: SessionRichTextProps) {
  const mentionOptions = useMemo(
    () =>
      mentionsByToken && mentionsByToken.size > 0
        ? { mentionsByToken, variant: mentionVariant }
        : null,
    [mentionsByToken, mentionVariant],
  );
  return (
    <div
      className={cn(
        "session-richtext",
        variant === "user" && "session-richtext--user",
        className
      )}
    >
      <MentionOptionsContext.Provider value={mentionOptions}>
        <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={MARKDOWN_COMPONENTS}>
          {normalizeSessionMarkdown(content)}
        </ReactMarkdown>
      </MentionOptionsContext.Provider>
    </div>
  );
}
