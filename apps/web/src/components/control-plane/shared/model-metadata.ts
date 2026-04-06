/* -------------------------------------------------------------------------- */
/*  Static model metadata — context window, speed/intelligence tiers, cost   */
/*  Synced from koda/provider_models.py _GENERAL_MODEL_METADATA              */
/* -------------------------------------------------------------------------- */

export type ModelMeta = {
  displayName: string;
  description: string;
  speed: number;          // 1-5
  intelligence: number;   // 1-5
  contextWindow: number;  // tokens
  inputCostPer1M?: number;
  outputCostPer1M?: number;
};

/**
 * Known model metadata. Keys are `model_id` strings as returned by providers.
 * When a model is not in this map, the UI falls back to generic display.
 */
export const MODEL_METADATA: Record<string, ModelMeta> = {
  /* ── Anthropic ─────────────────────────────────────────── */
  "claude-opus-4-6": {
    displayName: "Claude Opus 4.6",
    description: "Modelo de raciocinio mais avancado com pensamento estendido.",
    speed: 2,
    intelligence: 5,
    contextWindow: 1_000_000,
    inputCostPer1M: 5,
    outputCostPer1M: 25,
  },
  "claude-sonnet-4-6": {
    displayName: "Claude Sonnet 4.6",
    description: "Equilibrio entre velocidade e inteligencia para tarefas complexas.",
    speed: 4,
    intelligence: 4,
    contextWindow: 1_000_000,
    inputCostPer1M: 3,
    outputCostPer1M: 15,
  },
  "claude-haiku-4-5-20251001": {
    displayName: "Claude Haiku 4.5",
    description: "Modelo rapido e economico para tarefas de alta vazao.",
    speed: 5,
    intelligence: 3,
    contextWindow: 200_000,
    inputCostPer1M: 1,
    outputCostPer1M: 5,
  },
  "claude-opus-4-1": {
    displayName: "Claude Opus 4.1",
    description: "Claude Opus 4.1 com raciocinio avancado.",
    speed: 2,
    intelligence: 5,
    contextWindow: 200_000,
    inputCostPer1M: 5,
    outputCostPer1M: 25,
  },
  "claude-opus-4-1-20250805": {
    displayName: "Claude Opus 4.1 (snapshot)",
    description: "Claude Opus 4.1 snapshot.",
    speed: 2,
    intelligence: 5,
    contextWindow: 200_000,
    inputCostPer1M: 5,
    outputCostPer1M: 25,
  },
  "claude-sonnet-4-5": {
    displayName: "Claude Sonnet 4.5",
    description: "Claude Sonnet 4.5 com raciocinio forte.",
    speed: 4,
    intelligence: 4,
    contextWindow: 200_000,
    inputCostPer1M: 3,
    outputCostPer1M: 15,
  },
  "claude-sonnet-4-20250514": {
    displayName: "Claude Sonnet 4",
    description: "Claude Sonnet 4 snapshot.",
    speed: 4,
    intelligence: 4,
    contextWindow: 200_000,
    inputCostPer1M: 3,
    outputCostPer1M: 15,
  },
  "claude-3-7-sonnet-latest": {
    displayName: "Claude 3.7 Sonnet",
    description: "Claude 3.7 Sonnet com raciocinio estendido.",
    speed: 4,
    intelligence: 4,
    contextWindow: 200_000,
    inputCostPer1M: 3,
    outputCostPer1M: 15,
  },
  "claude-3-7-sonnet-20250219": {
    displayName: "Claude 3.7 Sonnet (snapshot)",
    description: "Claude 3.7 Sonnet snapshot.",
    speed: 4,
    intelligence: 4,
    contextWindow: 200_000,
    inputCostPer1M: 3,
    outputCostPer1M: 15,
  },
  "claude-3-5-haiku-latest": {
    displayName: "Claude 3.5 Haiku",
    description: "Claude 3.5 Haiku rapido e eficiente.",
    speed: 5,
    intelligence: 3,
    contextWindow: 200_000,
    inputCostPer1M: 0.8,
    outputCostPer1M: 4,
  },

  /* ── OpenAI ────────────────────────────────────────────── */
  "gpt-5.4": {
    displayName: "GPT-5.4",
    description: "Modelo de ultima geracao com raciocinio avancado e contexto massivo.",
    speed: 3,
    intelligence: 5,
    contextWindow: 1_050_000,
    inputCostPer1M: 2.5,
    outputCostPer1M: 15,
  },
  "gpt-5.4-mini": {
    displayName: "GPT-5.4 Mini",
    description: "Versao compacta e rapida do GPT-5.4.",
    speed: 5,
    intelligence: 3,
    contextWindow: 400_000,
    inputCostPer1M: 0.75,
    outputCostPer1M: 4.5,
  },
  "gpt-5.4-nano": {
    displayName: "GPT-5.4 Nano",
    description: "Versao ultrarapida para tarefas simples e alta vazao.",
    speed: 5,
    intelligence: 2,
    contextWindow: 400_000,
    inputCostPer1M: 0.2,
    outputCostPer1M: 1.25,
  },
  "gpt-5.4-pro": {
    displayName: "GPT-5.4 Pro",
    description: "Versao premium do GPT-5.4 com raciocinio estendido.",
    speed: 2,
    intelligence: 5,
    contextWindow: 1_050_000,
    inputCostPer1M: 5,
    outputCostPer1M: 30,
  },
  "gpt-5.3-codex": {
    displayName: "GPT-5.3 Codex",
    description: "Especializado em codigo e raciocinio tecnico.",
    speed: 3,
    intelligence: 4,
    contextWindow: 400_000,
    inputCostPer1M: 1.75,
    outputCostPer1M: 14,
  },
  "gpt-5.3-codex-spark": {
    displayName: "GPT-5.3 Codex Spark",
    description: "Versao agil do GPT-5.3 Codex para iteracao rapida.",
    speed: 3,
    intelligence: 4,
    contextWindow: 400_000,
    inputCostPer1M: 1.75,
    outputCostPer1M: 14,
  },
  "gpt-5.2-codex": {
    displayName: "GPT-5.2 Codex",
    description: "Codex para tarefas de engenharia de software.",
    speed: 3,
    intelligence: 4,
    contextWindow: 400_000,
    inputCostPer1M: 1.75,
    outputCostPer1M: 14,
  },
  "gpt-5.2": {
    displayName: "GPT-5.2",
    description: "Modelo GPT-5.2 de proposito geral.",
    speed: 3,
    intelligence: 4,
    contextWindow: 400_000,
    inputCostPer1M: 1.25,
    outputCostPer1M: 10,
  },
  "gpt-5.2-pro": {
    displayName: "GPT-5.2 Pro",
    description: "GPT-5.2 Pro com raciocinio avancado.",
    speed: 2,
    intelligence: 5,
    contextWindow: 400_000,
    inputCostPer1M: 5,
    outputCostPer1M: 30,
  },
  "gpt-5.1-codex-max": {
    displayName: "GPT-5.1 Codex Max",
    description: "Codex 5.1 Max para projetos complexos e longos.",
    speed: 3,
    intelligence: 4,
    contextWindow: 400_000,
    inputCostPer1M: 2.5,
    outputCostPer1M: 15,
  },
  "gpt-5.1-codex-mini": {
    displayName: "GPT-5.1 Codex Mini",
    description: "Codex 5.1 Mini para tarefas de codigo rapidas.",
    speed: 4,
    intelligence: 3,
    contextWindow: 400_000,
    inputCostPer1M: 0.75,
    outputCostPer1M: 4.5,
  },
  "gpt-5.1-codex": {
    displayName: "GPT-5.1 Codex",
    description: "Codex 5.1 para engenharia de software.",
    speed: 3,
    intelligence: 4,
    contextWindow: 400_000,
    inputCostPer1M: 1.75,
    outputCostPer1M: 14,
  },
  "gpt-5.1": {
    displayName: "GPT-5.1",
    description: "Modelo GPT-5.1 de proposito geral.",
    speed: 3,
    intelligence: 4,
    contextWindow: 400_000,
    inputCostPer1M: 1.25,
    outputCostPer1M: 10,
  },
  "gpt-5": {
    displayName: "GPT-5",
    description: "Modelo GPT de quinta geracao com capacidades avancadas.",
    speed: 3,
    intelligence: 5,
    contextWindow: 400_000,
    inputCostPer1M: 1.25,
    outputCostPer1M: 10,
  },
  "gpt-5-mini": {
    displayName: "GPT-5 Mini",
    description: "Versao compacta e eficiente do GPT-5.",
    speed: 5,
    intelligence: 3,
    contextWindow: 400_000,
    inputCostPer1M: 0.25,
    outputCostPer1M: 2,
  },
  "gpt-5-nano": {
    displayName: "GPT-5 Nano",
    description: "Modelo ultrarapido para tarefas simples de alta vazao.",
    speed: 5,
    intelligence: 2,
    contextWindow: 400_000,
    inputCostPer1M: 0.05,
    outputCostPer1M: 0.4,
  },
  "gpt-5-pro": {
    displayName: "GPT-5 Pro",
    description: "GPT-5 Pro com raciocinio estendido e precisao maxima.",
    speed: 2,
    intelligence: 5,
    contextWindow: 400_000,
    inputCostPer1M: 5,
    outputCostPer1M: 30,
  },
  "gpt-5-codex": {
    displayName: "GPT-5 Codex",
    description: "GPT-5 Codex para engenharia de software.",
    speed: 3,
    intelligence: 4,
    contextWindow: 400_000,
    inputCostPer1M: 1.25,
    outputCostPer1M: 10,
  },
  "gpt-4.1": {
    displayName: "GPT-4.1",
    description: "GPT-4.1 com janela de contexto larga.",
    speed: 3,
    intelligence: 4,
    contextWindow: 1_000_000,
    inputCostPer1M: 2,
    outputCostPer1M: 8,
  },
  "gpt-4.1-mini": {
    displayName: "GPT-4.1 Mini",
    description: "GPT-4.1 Mini rapido e economico.",
    speed: 5,
    intelligence: 3,
    contextWindow: 1_000_000,
    inputCostPer1M: 0.4,
    outputCostPer1M: 1.6,
  },
  "gpt-4.1-nano": {
    displayName: "GPT-4.1 Nano",
    description: "GPT-4.1 Nano para tarefas simples de alta vazao.",
    speed: 5,
    intelligence: 2,
    contextWindow: 1_000_000,
    inputCostPer1M: 0.1,
    outputCostPer1M: 0.4,
  },
  "gpt-4o": {
    displayName: "GPT-4o",
    description: "GPT-4o multimodal rapido.",
    speed: 4,
    intelligence: 4,
    contextWindow: 128_000,
    inputCostPer1M: 2.5,
    outputCostPer1M: 10,
  },
  "gpt-4o-mini": {
    displayName: "GPT-4o Mini",
    description: "GPT-4o Mini economico e rapido.",
    speed: 5,
    intelligence: 3,
    contextWindow: 128_000,
    inputCostPer1M: 0.15,
    outputCostPer1M: 0.6,
  },
  "o4-mini": {
    displayName: "o4 Mini",
    description: "Modelo de raciocinio compacto e eficiente.",
    speed: 3,
    intelligence: 4,
    contextWindow: 200_000,
    inputCostPer1M: 1.1,
    outputCostPer1M: 4.4,
  },
  "o3": {
    displayName: "o3",
    description: "Modelo de raciocinio avancado da OpenAI.",
    speed: 2,
    intelligence: 5,
    contextWindow: 200_000,
    inputCostPer1M: 2,
    outputCostPer1M: 8,
  },
  "o3-mini": {
    displayName: "o3 Mini",
    description: "Versao compacta do o3 com bom custo-beneficio.",
    speed: 3,
    intelligence: 4,
    contextWindow: 200_000,
    inputCostPer1M: 1.1,
    outputCostPer1M: 4.4,
  },
  "o3-pro": {
    displayName: "o3 Pro",
    description: "o3 Pro com raciocinio profundo e alta fidelidade.",
    speed: 1,
    intelligence: 5,
    contextWindow: 200_000,
    inputCostPer1M: 20,
    outputCostPer1M: 80,
  },

  /* ── Google ────────────────────────────────────────────── */
  "gemini-2.5-pro": {
    displayName: "Gemini 2.5 Pro",
    description: "Modelo avancado com janela de contexto massiva e raciocinio.",
    speed: 3,
    intelligence: 5,
    contextWindow: 1_000_000,
    inputCostPer1M: 1.25,
    outputCostPer1M: 10,
  },
  "gemini-2.5-flash": {
    displayName: "Gemini 2.5 Flash",
    description: "Rapido e eficiente com grande janela de contexto.",
    speed: 5,
    intelligence: 4,
    contextWindow: 1_000_000,
    inputCostPer1M: 0.3,
    outputCostPer1M: 2.5,
  },
  "gemini-2.5-flash-lite": {
    displayName: "Gemini 2.5 Flash-Lite",
    description: "Versao leve e ultrarapida do Flash.",
    speed: 5,
    intelligence: 3,
    contextWindow: 1_000_000,
    inputCostPer1M: 0.1,
    outputCostPer1M: 0.4,
  },
  "gemini-2.0-flash": {
    displayName: "Gemini 2.0 Flash",
    description: "Modelo rapido de geracao anterior.",
    speed: 5,
    intelligence: 3,
    contextWindow: 1_000_000,
    inputCostPer1M: 0.1,
    outputCostPer1M: 0.4,
  },
  "gemini-3-flash-preview": {
    displayName: "Gemini 3 Flash Preview",
    description: "Preview do Gemini 3 Flash com melhorias de velocidade.",
    speed: 5,
    intelligence: 4,
    contextWindow: 1_000_000,
    inputCostPer1M: 0.3,
    outputCostPer1M: 2.5,
  },
  "gemini-3.1-flash-lite-preview": {
    displayName: "Gemini 3.1 Flash-Lite Preview",
    description: "Preview do Gemini 3.1 Flash-Lite ultrarapido.",
    speed: 5,
    intelligence: 3,
    contextWindow: 1_000_000,
    inputCostPer1M: 0.1,
    outputCostPer1M: 0.4,
  },
  "gemini-3.1-pro-preview": {
    displayName: "Gemini 3.1 Pro Preview",
    description: "Preview do Gemini 3.1 Pro com raciocinio avancado.",
    speed: 3,
    intelligence: 5,
    contextWindow: 1_000_000,
    inputCostPer1M: 1.25,
    outputCostPer1M: 10,
  },
  "gemini-3.0-flash": {
    displayName: "Gemini 3.0 Flash",
    description: "Gemini 3.0 Flash legado.",
    speed: 5,
    intelligence: 4,
    contextWindow: 1_000_000,
    inputCostPer1M: 0.3,
    outputCostPer1M: 2.5,
  },
  "gemini-3.0-flash-lite": {
    displayName: "Gemini 3.0 Flash-Lite",
    description: "Gemini 3.0 Flash-Lite legado.",
    speed: 5,
    intelligence: 3,
    contextWindow: 1_000_000,
    inputCostPer1M: 0.1,
    outputCostPer1M: 0.4,
  },

  /* ── Ollama ────────────────────────────────────────────── */
  /* Ollama models are discovered dynamically via /api/tags.
     No static entries needed — metadata flows through the
     functional catalog from the backend.                    */
};

export function getModelMeta(modelId: string): ModelMeta | null {
  return MODEL_METADATA[modelId] ?? null;
}

export function formatContextWindow(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(tokens % 1_000_000 === 0 ? 0 : 1)}M tokens`;
  if (tokens >= 1_000) return `${Math.round(tokens / 1_000)}k tokens`;
  return `${tokens} tokens`;
}

export function formatCost(costPer1M: number): string {
  if (costPer1M < 1) return `$${costPer1M.toFixed(2)}`;
  return `$${costPer1M.toFixed(costPer1M % 1 === 0 ? 0 : 2)}`;
}
