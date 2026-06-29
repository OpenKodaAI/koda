import type { MemoryTypeKey } from "./types";

export const MEMORY_TYPE_ORDER: MemoryTypeKey[] = [
  "fact",
  "procedure",
  "event",
  "preference",
  "decision",
  "problem",
  "task",
  "commit",
  "relationship",
];

export const MEMORY_TYPE_META: Record<
  MemoryTypeKey,
  { label: string; color: string; accent: string }
> = {
  fact: {
    label: "Fato",
    color: "#7F9BD0",
    accent: "#314A76",
  },
  procedure: {
    label: "Procedimento",
    color: "#8DA6E0",
    accent: "#3B4E7A",
  },
  event: {
    label: "Evento",
    color: "#67B7C1",
    accent: "#245D63",
  },
  preference: {
    label: "Preferência",
    color: "#C393C3",
    accent: "#6A426B",
  },
  decision: {
    label: "Decisão",
    color: "#8BA6C7",
    accent: "#38506C",
  },
  problem: {
    label: "Problema",
    color: "#D07E96",
    accent: "#74394B",
  },
  task: {
    label: "Tarefa",
    color: "#D3A24E",
    accent: "#6F4F1D",
  },
  commit: {
    label: "Compromisso",
    color: "#7EB88E",
    accent: "#355A40",
  },
  relationship: {
    label: "Relação",
    color: "#A88DDB",
    accent: "#564381",
  },
};

export function isMemoryTypeKey(value: string): value is MemoryTypeKey {
  return value in MEMORY_TYPE_META;
}

export function getMemoryTypeMeta(type: MemoryTypeKey) {
  return MEMORY_TYPE_META[type];
}

export function getMemoryTypeLabel(
  type: MemoryTypeKey,
  translate?: (key: string, options?: Record<string, unknown>) => string
) {
  if (!translate) {
    return MEMORY_TYPE_META[type].label;
  }

  return translate(`memory.types.${type}`, {
    defaultValue: MEMORY_TYPE_META[type].label,
  });
}
