"use client";

import {
  Children,
  cloneElement,
  isValidElement,
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
  children,
}: {
  label: string;
  description?: string;
  children: ReactNode;
}) {
  const { tl } = useAppI18n();
  return (
    <label className="flex flex-col gap-2 px-1 py-1">
      <div className="flex min-h-[3.1rem] flex-col">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
            {tl(label)}
          </div>
          {description ? (
            <p className="mt-0.5 max-w-[42rem] text-[11px] leading-snug text-[var(--text-quaternary)]">
              {tl(description)}
            </p>
          ) : null}
        </div>
      </div>
      {localizeNode(children, tl)}
    </label>
  );
}
