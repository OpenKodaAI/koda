"use client";

import {
  cloneElement,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";

type LiteralTranslator = (value: string, options?: Record<string, unknown>) => string;

const STRING_PROPS = new Set([
  "aria-label",
  "description",
  "emptyMessage",
  "helperText",
  "label",
  "placeholder",
  "title",
]);

const STRUCTURED_PROPS = new Set(["breadcrumb", "options"]);

function localizeStructuredValue(value: unknown, tl: LiteralTranslator): unknown {
  if (typeof value === "string") {
    return tl(value);
  }

  if (Array.isArray(value)) {
    return value.map((item) => localizeStructuredValue(item, tl));
  }

  if (isValidElement(value)) {
    return localizeReactNode(value, tl);
  }

  if (value && typeof value === "object") {
    const nextEntries = Object.entries(value as Record<string, unknown>).map(([key, itemValue]) => {
      if (typeof itemValue === "string" && (key === "label" || key === "description" || key === "title")) {
        return [key, tl(itemValue)] as const;
      }

      return [key, itemValue] as const;
    });

    return Object.fromEntries(nextEntries);
  }

  return value;
}

export function localizeReactNode(node: ReactNode, tl: LiteralTranslator): ReactNode {
  if (typeof node === "string") {
    return tl(node);
  }

  if (Array.isArray(node)) {
    return node.map((child) => localizeReactNode(child, tl));
  }

  if (!isValidElement(node)) {
    return node;
  }

  const element = node as ReactElement<Record<string, unknown>>;
  const nextProps: Record<string, unknown> = {};
  let hasChanges = false;

  for (const [propName, propValue] of Object.entries(element.props)) {
    if (propName === "children") {
      const nextChildren = localizeReactNode(propValue as ReactNode, tl);
      if (nextChildren !== propValue) {
        nextProps.children = nextChildren;
        hasChanges = true;
      }
      continue;
    }

    if (typeof propValue === "string" && STRING_PROPS.has(propName)) {
      nextProps[propName] = tl(propValue);
      hasChanges = true;
      continue;
    }

    if (STRUCTURED_PROPS.has(propName)) {
      const nextValue = localizeStructuredValue(propValue, tl);
      if (nextValue !== propValue) {
        nextProps[propName] = nextValue;
        hasChanges = true;
      }
    }
  }

  return hasChanges ? cloneElement(element, nextProps) : node;
}

export function LocalizedTree({ children }: { children: ReactNode }) {
  const { tl } = useAppI18n();
  return <>{localizeReactNode(children, tl)}</>;
}
