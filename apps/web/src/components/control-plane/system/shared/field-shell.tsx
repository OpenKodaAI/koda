"use client";

import {
  Children,
  cloneElement,
  isValidElement,
  useId,
  type ReactElement,
  type ReactNode,
} from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";

function localizeNode(node: ReactNode, tl: (value: string) => string): ReactNode {
  if (typeof node === "string") {
    return tl(node);
  }

  if (Array.isArray(node)) {
    return Children.map(node, (child) => localizeNode(child, tl));
  }

  if (!isValidElement(node)) {
    return node;
  }

  const element = node as ReactElement<Record<string, unknown>>;
  const nextProps: Record<string, unknown> = {};
  let hasChanges = false;

  for (const propName of ["placeholder", "title", "aria-label"] as const) {
    const value = element.props[propName];
    if (typeof value === "string") {
      nextProps[propName] = tl(value);
      hasChanges = true;
    }
  }

  if ("children" in element.props) {
    const currentChildren = element.props.children as ReactNode;
    const nextChildren = localizeNode(currentChildren, tl);
    if (nextChildren !== currentChildren) {
      nextProps.children = nextChildren;
      hasChanges = true;
    }
  }

  return hasChanges ? cloneElement(element, nextProps) : node;
}

export function FieldShell({
  label,
  description,
  error,
  children,
}: {
  label: string;
  description?: string;
  error?: string | null;
  children: ReactNode;
}) {
  const { tl } = useAppI18n();
  const errorId = useId();
  const hasError = Boolean(error);
  return (
    <label
      className="flex flex-col gap-1.5"
      aria-invalid={hasError || undefined}
      aria-describedby={hasError ? errorId : undefined}
    >
      <span className="eyebrow">{tl(label)}</span>
      {description ? (
        <span className="max-w-[42rem] text-xs leading-relaxed text-[var(--text-quaternary)]">
          {tl(description)}
        </span>
      ) : null}
      {localizeNode(children, tl)}
      {hasError ? (
        <span
          id={errorId}
          role="alert"
          className="text-xs text-[var(--tone-danger-text)]"
        >
          {tl(error as string)}
        </span>
      ) : null}
    </label>
  );
}
