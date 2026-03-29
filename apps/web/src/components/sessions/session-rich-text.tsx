"use client";

import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import { ExternalLink } from "@/components/ui/external-link";
import { cn } from "@/lib/utils";

interface SessionRichTextProps {
  content: string;
  className?: string;
  variant?: "assistant" | "user";
}

const markdownComponents: Components = {
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
};

function normalizeSessionMarkdown(content: string) {
  return content
    .replace(/\r\n/g, "\n")
    .replace(/([^\n])\s+(#{1,6}\s)/g, "$1\n\n$2")
    .replace(/(#{1,6}[^\n*|]+?)\s+(\*\*[^*]+:\*\*)/g, "$1\n\n- $2")
    .replace(/(#{1,6}[^\n|]+?)\s+(\|(?:[^|\n]+\|){2,})/g, "$1\n\n$2")
    .replace(/(#{1,6}[^\n]+?)\s+-\s+/g, "$1\n- ")
    .replace(/\s+---\s+(#{1,6}\s)/g, "\n\n---\n\n$1")
    .replace(/\|\s+\|/g, "|\n|")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function SessionRichText({
  content,
  className,
  variant = "assistant",
}: SessionRichTextProps) {
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
        components={markdownComponents}
      >
        {normalizeSessionMarkdown(content)}
      </ReactMarkdown>
    </div>
  );
}
