"""Canonical provider model catalogs grouped by product functionality."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

EffortKind = Literal["enum", "tokens"]


@dataclass(frozen=True, slots=True)
class ModelFunctionDefinition:
    id: str
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class ProviderModelDefinition:
    provider_id: str
    model_id: str
    title: str
    function_id: str
    description: str = ""
    status: str = "current"
    context_window: int = 0
    input_cost_per_1m: float = 0.0
    output_cost_per_1m: float = 0.0
    speed_tier: int = 3
    intelligence_tier: int = 3


_MODEL_FUNCTIONS: tuple[ModelFunctionDefinition, ...] = (
    ModelFunctionDefinition("general", "Geral", "Conversas, raciocinio e execucao principal dos agents."),
    ModelFunctionDefinition("image", "Imagem", "Geracao ou edicao de imagem."),
    ModelFunctionDefinition("video", "Video", "Geracao ou transformacao de video."),
    ModelFunctionDefinition("audio", "Audio", "Sintese de fala ou audio generativo."),
    ModelFunctionDefinition("transcription", "Transcricao", "Speech-to-text e transcricao de audio."),
    ModelFunctionDefinition("music", "Musica", "Geracao de musica e trilhas."),
)

MODEL_FUNCTION_IDS: tuple[str, ...] = tuple(item.id for item in _MODEL_FUNCTIONS)

# Models available ONLY via API key (not available with ChatGPT subscription).
# These are added to the catalog only when auth_mode == "api_key".
_API_KEY_EXTRA_MODELS: dict[str, dict[str, str]] = {
    "claude": {
        "claude-3-5-haiku-latest": "Claude 3.5 Haiku",
        "claude-3-7-sonnet-latest": "Claude 3.7 Sonnet",
        "claude-3-7-sonnet-20250219": "Claude 3.7 Sonnet (snapshot)",
        "claude-sonnet-4-20250514": "Claude Sonnet 4",
        "claude-sonnet-4-5": "Claude Sonnet 4.5",
        "claude-opus-4-1": "Claude Opus 4.1",
        "claude-opus-4-1-20250805": "Claude Opus 4.1 (snapshot)",
    },
    "codex": {
        "o4-mini": "o4 mini",
        "o3": "o3",
        "o3-mini": "o3 mini",
        "o3-pro": "o3 Pro",
        "gpt-4o": "GPT-4o",
        "gpt-4o-mini": "GPT-4o mini",
        "gpt-4.1": "GPT-4.1",
        "gpt-4.1-mini": "GPT-4.1 mini",
        "gpt-4.1-nano": "GPT-4.1 nano",
        "gpt-5": "GPT-5",
        "gpt-5-mini": "GPT-5 mini",
        "gpt-5-nano": "GPT-5 nano",
        "gpt-5-pro": "GPT-5 Pro",
        "gpt-5-codex": "GPT-5 Codex",
        "gpt-5.4-pro": "GPT-5.4 Pro",
        "gpt-5.4-nano": "GPT-5.4 nano",
        "gpt-5.2-pro": "GPT-5.2 Pro",
        "gpt-5.1": "GPT-5.1",
        "gpt-5.1-codex": "GPT-5.1 Codex",
    },
}


def resolve_api_key_extra_model_ids(provider_id: str) -> list[str]:
    """Return model IDs available only via API key authentication."""
    return list(_API_KEY_EXTRA_MODELS.get(provider_id.strip().lower(), {}).keys())


_DYNAMIC_GENERAL_MODEL_LABELS: dict[str, dict[str, str]] = {
    "claude": {
        "claude-opus-4-7": "Claude Opus 4.7",
        "claude-sonnet-4-6": "Claude Sonnet 4.6",
        "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
        "claude-opus-4-6": "Claude Opus 4.6 (legacy)",
        "claude-sonnet-4-5-20250929": "Claude Sonnet 4.5 (snapshot)",
        "claude-opus-4-5-20251101": "Claude Opus 4.5 (snapshot)",
        "claude-opus-4-1-20250805": "Claude Opus 4.1 (snapshot)",
    },
    "codex": {
        "gpt-5.5": "GPT-5.5",
        "gpt-5.4": "GPT-5.4",
        "gpt-5.4-mini": "GPT-5.4 Mini",
        "gpt-5.4-nano": "GPT-5.4 Nano",
        "gpt-5.3-codex": "GPT-5.3 Codex",
        "gpt-5.3-codex-spark": "GPT-5.3 Codex Spark",
        "gpt-5.2": "GPT-5.2",
    },
    "gemini": {
        "gemini-2.5-flash-lite": "Gemini 2.5 Flash-Lite",
        "gemini-2.5-flash": "Gemini 2.5 Flash",
        "gemini-2.5-pro": "Gemini 2.5 Pro",
        "gemini-3-flash-preview": "Gemini 3 Flash Preview",
        "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash-Lite Preview",
        "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview",
        "gemini-3.0-flash": "Gemini 3.0 Flash (legacy)",
        "gemini-3.0-flash-lite": "Gemini 3.0 Flash-Lite (legacy)",
    },
    "ollama": {},  # Ollama models are discovered dynamically via /api/tags
    "perplexity": {
        "sonar": "Sonar",
        "sonar-pro": "Sonar Pro",
        "sonar-reasoning": "Sonar Reasoning",
        "sonar-reasoning-pro": "Sonar Reasoning Pro",
        "sonar-deep-research": "Sonar Deep Research",
    },
    "mistral": {
        "mistral-large-latest": "Mistral Large",
        "mistral-medium-latest": "Mistral Medium",
        "mistral-small-latest": "Mistral Small",
        "codestral-latest": "Codestral",
        "pixtral-large-latest": "Pixtral Large",
        "pixtral-12b-2409": "Pixtral 12B",
        "magistral-medium-latest": "Magistral Medium",
        "magistral-small-latest": "Magistral Small",
        "ministral-8b-latest": "Ministral 8B",
        "ministral-3b-latest": "Ministral 3B",
        "mistral-saba-latest": "Mistral Saba",
    },
    "qwen": {
        "qwen3-max": "Qwen3 Max",
        "qwen3-plus": "Qwen3 Plus",
        "qwen3-flash": "Qwen3 Flash",
        "qwen3-vl-max": "Qwen3-VL Max",
        "qwen3-vl-plus": "Qwen3-VL Plus",
        "qwen3-vl-flash": "Qwen3-VL Flash",
        "qwen3-coder-plus": "Qwen3 Coder Plus",
        "qwen3-coder-flash": "Qwen3 Coder Flash",
        "qwen3-omni-30b-a3b": "Qwen3 Omni 30B (multimodal)",
        "qwen-max": "Qwen Max",
        "qwen-plus": "Qwen Plus",
        "qwen-turbo": "Qwen Turbo",
        "qwen-long": "Qwen Long (1M tokens)",
        "qwen2.5-72b-instruct": "Qwen 2.5 72B Instruct",
        "qwen2.5-coder-32b-instruct": "Qwen 2.5 Coder 32B",
        "qwen-vl-max": "Qwen-VL Max",
        "qwen-vl-plus": "Qwen-VL Plus",
        "qwq-32b": "QwQ 32B",
        "qvq-72b-preview": "QvQ 72B (vision reasoning, preview)",
    },
    "kimi": {
        "kimi-k2.6": "Kimi K2.6",
        "kimi-k2.5": "Kimi K2.5",
        "kimi-k2-0905-preview": "Kimi K2 (preview 0905)",
        "kimi-k2-0711-preview": "Kimi K2 (snapshot 0711)",
        "kimi-latest": "Kimi Latest",
        "kimi-thinking-preview": "Kimi Thinking (preview)",
        "moonshot-v1-128k": "Moonshot v1 128K",
        "moonshot-v1-32k": "Moonshot v1 32K",
        "moonshot-v1-8k": "Moonshot v1 8K",
        "moonshot-v1-auto": "Moonshot v1 Auto",
    },
    "groq": {
        "openai/gpt-oss-120b": "GPT-OSS 120B",
        "openai/gpt-oss-20b": "GPT-OSS 20B",
        "openai/gpt-oss-safeguard-20b": "GPT-OSS Safeguard 20B",
        "moonshotai/kimi-k2-instruct": "Kimi K2 (Instruct)",
        "qwen/qwen3-32b": "Qwen3 32B",
        "llama-3.3-70b-versatile": "Llama 3.3 70B Versatile",
        "llama-3.1-8b-instant": "Llama 3.1 8B Instant",
        "llama-3.2-1b-preview": "Llama 3.2 1B (preview)",
        "llama-3.2-3b-preview": "Llama 3.2 3B (preview)",
        "llama-3.2-11b-vision-preview": "Llama 3.2 11B Vision",
        "llama-3.2-90b-vision-preview": "Llama 3.2 90B Vision",
        "mixtral-8x7b-32768": "Mixtral 8x7B 32K",
        "gemma2-9b-it": "Gemma2 9B",
        "qwen-2.5-32b": "Qwen 2.5 32B",
        "qwen-2.5-coder-32b": "Qwen 2.5 Coder 32B",
        "deepseek-r1-distill-llama-70b": "DeepSeek R1 Distill (Llama 70B)",
    },
    "deepseek": {
        "deepseek-v4-pro": "DeepSeek V4 Pro",
        "deepseek-v4-flash": "DeepSeek V4 Flash",
        "deepseek-chat": "DeepSeek Chat (alias)",
        "deepseek-reasoner": "DeepSeek Reasoner (alias)",
    },
    "xai": {
        "grok-4.20-multi-agent": "Grok 4.20 Multi-Agent",
        "grok-4.3": "Grok 4.3",
        "grok-4.1-fast": "Grok 4.1 Fast (2M context)",
        "grok-4-fast": "Grok 4 Fast",
        "grok-4-0709": "Grok 4",
        "grok-3": "Grok 3",
        "grok-3-mini": "Grok 3 Mini",
        "grok-3-fast": "Grok 3 Fast",
        "grok-3-mini-fast": "Grok 3 Mini Fast",
        "grok-2-vision-1212": "Grok 2 Vision",
        "grok-2-1212": "Grok 2",
    },
    "openrouter": {
        "openrouter/auto": "OpenRouter Auto",
        "~openai/gpt-mini-latest": "OpenAI GPT Mini Latest",
        "~google/gemini-flash-latest": "Google Gemini Flash Latest",
        "~google/gemini-pro-latest": "Google Gemini Pro Latest",
        "~anthropic/claude-sonnet-latest": "Anthropic Claude Sonnet Latest",
        "~openai/gpt-latest": "OpenAI GPT Latest",
        "openrouter/pareto-code": "Pareto Code Router",
    },
}

# ── Real pricing & metadata for general (dynamic) models ─────────────
# Keyed by (provider_id, model_id). All costs in USD per 1M tokens.
# Sources: platform.claude.com/docs, developers.openai.com/api/docs/pricing,
#          ai.google.dev/gemini-api/docs/pricing  (verified 2026-04)
_GENERAL_MODEL_METADATA: dict[tuple[str, str], dict[str, Any]] = {
    # ── Anthropic ────────────────────────────────────────────────────
    ("claude", "claude-opus-4-7"): {
        "description": "Modelo de raciocinio agentic mais capaz com adaptive thinking.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 25.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high", "xhigh", "max"),
        "effort_default": "medium",
    },
    ("claude", "claude-opus-4-6"): {
        "description": "Geracao anterior de Opus, mantida para compatibilidade.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 25.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high", "xhigh", "max"),
        "effort_default": "medium",
    },
    ("claude", "claude-opus-4-5-20251101"): {
        "description": "Snapshot Opus 4.5 (1101).",
        "context_window": 200_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 25.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high", "xhigh", "max"),
        "effort_default": "medium",
    },
    ("claude", "claude-sonnet-4-5-20250929"): {
        "description": "Snapshot Sonnet 4.5 (0929).",
        "context_window": 200_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high", "xhigh", "max"),
        "effort_default": "medium",
    },
    ("claude", "claude-sonnet-4-6"): {
        "description": "Equilibrio entre velocidade e inteligencia para tarefas complexas.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high", "xhigh", "max"),
        "effort_default": "medium",
    },
    ("claude", "claude-haiku-4-5-20251001"): {
        "description": "Modelo rapido e economico para tarefas de alta vazao.",
        "context_window": 200_000,
        "input_cost_per_1m": 1.00,
        "output_cost_per_1m": 5.00,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    # API-key-only Claude models
    ("claude", "claude-opus-4-1"): {
        "description": "Claude Opus 4.1 com raciocinio avancado.",
        "context_window": 200_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 25.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high", "xhigh", "max"),
        "effort_default": "medium",
    },
    ("claude", "claude-opus-4-1-20250805"): {
        "description": "Claude Opus 4.1 snapshot.",
        "context_window": 200_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 25.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high", "xhigh", "max"),
        "effort_default": "medium",
    },
    ("claude", "claude-sonnet-4-5"): {
        "description": "Claude Sonnet 4.5 com raciocinio forte.",
        "context_window": 200_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high", "xhigh", "max"),
        "effort_default": "medium",
    },
    ("claude", "claude-sonnet-4-20250514"): {
        "description": "Claude Sonnet 4 snapshot.",
        "context_window": 200_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high", "xhigh", "max"),
        "effort_default": "medium",
    },
    ("claude", "claude-3-7-sonnet-latest"): {
        "description": "Claude 3.7 Sonnet com raciocinio estendido.",
        "context_window": 200_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high", "xhigh", "max"),
        "effort_default": "medium",
    },
    ("claude", "claude-3-7-sonnet-20250219"): {
        "description": "Claude 3.7 Sonnet snapshot.",
        "context_window": 200_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high", "xhigh", "max"),
        "effort_default": "medium",
    },
    ("claude", "claude-3-5-haiku-latest"): {
        "description": "Claude 3.5 Haiku rapido e eficiente.",
        "context_window": 200_000,
        "input_cost_per_1m": 0.80,
        "output_cost_per_1m": 4.00,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    # ── OpenAI ───────────────────────────────────────────────────────
    ("codex", "gpt-5.5"): {
        "description": "Frontier OpenAI lancado em abril/2026 com 1M de contexto.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 18.00,
        "speed_tier": 3,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5.4"): {
        "description": "Geracao anterior de frontier, mantida para compatibilidade.",
        "context_window": 1_050_000,
        "input_cost_per_1m": 2.50,
        "output_cost_per_1m": 15.00,
        "speed_tier": 3,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5.4-mini"): {
        "description": "Versao compacta e rapida do GPT-5.4.",
        "context_window": 400_000,
        "input_cost_per_1m": 0.75,
        "output_cost_per_1m": 4.50,
        "speed_tier": 5,
        "intelligence_tier": 3,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5.4-nano"): {
        "description": "Versao ultrarapida para tarefas simples e alta vazao.",
        "context_window": 400_000,
        "input_cost_per_1m": 0.20,
        "output_cost_per_1m": 1.25,
        "speed_tier": 5,
        "intelligence_tier": 2,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5.4-pro"): {
        "description": "Versao premium do GPT-5.4 com raciocinio estendido.",
        "context_window": 1_050_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 30.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "high",
    },
    ("codex", "gpt-5.3-codex"): {
        "description": "Especializado em codigo e raciocinio tecnico.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.75,
        "output_cost_per_1m": 14.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5.3-codex-spark"): {
        "description": "Versao agil do GPT-5.3 Codex para iteracao rapida.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.75,
        "output_cost_per_1m": 14.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5.2-codex"): {
        "description": "Codex para tarefas de engenharia de software.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.75,
        "output_cost_per_1m": 14.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5.2"): {
        "description": "Modelo GPT-5.2 de proposito geral.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.25,
        "output_cost_per_1m": 10.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5.1-codex-max"): {
        "description": "Codex 5.1 Max para projetos complexos e longos.",
        "context_window": 400_000,
        "input_cost_per_1m": 2.50,
        "output_cost_per_1m": 15.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5.1-codex-mini"): {
        "description": "Codex 5.1 Mini para tarefas de codigo rapidas.",
        "context_window": 400_000,
        "input_cost_per_1m": 0.75,
        "output_cost_per_1m": 4.50,
        "speed_tier": 4,
        "intelligence_tier": 3,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5"): {
        "description": "Modelo GPT de quinta geracao com capacidades avancadas.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.25,
        "output_cost_per_1m": 10.00,
        "speed_tier": 3,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5-mini"): {
        "description": "Versao compacta e eficiente do GPT-5.",
        "context_window": 400_000,
        "input_cost_per_1m": 0.25,
        "output_cost_per_1m": 2.00,
        "speed_tier": 5,
        "intelligence_tier": 3,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5-nano"): {
        "description": "Modelo ultrarapido para tarefas simples de alta vazao.",
        "context_window": 400_000,
        "input_cost_per_1m": 0.05,
        "output_cost_per_1m": 0.40,
        "speed_tier": 5,
        "intelligence_tier": 2,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5-pro"): {
        "description": "GPT-5 Pro com raciocinio estendido e precisao maxima.",
        "context_window": 400_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 30.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "high",
    },
    ("codex", "gpt-5-codex"): {
        "description": "GPT-5 Codex para engenharia de software.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.25,
        "output_cost_per_1m": 10.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5.2-pro"): {
        "description": "GPT-5.2 Pro com raciocinio avancado.",
        "context_window": 400_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 30.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "high",
    },
    ("codex", "gpt-5.1"): {
        "description": "Modelo GPT-5.1 de proposito geral.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.25,
        "output_cost_per_1m": 10.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-5.1-codex"): {
        "description": "Codex 5.1 para engenharia de software.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.75,
        "output_cost_per_1m": 14.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("minimal", "low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "gpt-4.1"): {
        "description": "GPT-4.1 com janela de contexto larga.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 2.00,
        "output_cost_per_1m": 8.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
    },
    ("codex", "gpt-4.1-mini"): {
        "description": "GPT-4.1 Mini rapido e economico.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 0.40,
        "output_cost_per_1m": 1.60,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("codex", "gpt-4.1-nano"): {
        "description": "GPT-4.1 Nano para tarefas simples de alta vazao.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 0.10,
        "output_cost_per_1m": 0.40,
        "speed_tier": 5,
        "intelligence_tier": 2,
    },
    ("codex", "o4-mini"): {
        "description": "Modelo de raciocinio compacto e eficiente.",
        "context_window": 200_000,
        "input_cost_per_1m": 1.10,
        "output_cost_per_1m": 4.40,
        "speed_tier": 3,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "o3"): {
        "description": "Modelo de raciocinio avancado da OpenAI.",
        "context_window": 200_000,
        "input_cost_per_1m": 2.00,
        "output_cost_per_1m": 8.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "o3-mini"): {
        "description": "Versao compacta do o3 com bom custo-beneficio.",
        "context_window": 200_000,
        "input_cost_per_1m": 1.10,
        "output_cost_per_1m": 4.40,
        "speed_tier": 3,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high"),
        "effort_default": "medium",
    },
    ("codex", "o3-pro"): {
        "description": "o3 Pro com raciocinio profundo e alta fidelidade.",
        "context_window": 200_000,
        "input_cost_per_1m": 20.00,
        "output_cost_per_1m": 80.00,
        "speed_tier": 1,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high"),
        "effort_default": "high",
    },
    ("codex", "gpt-4o"): {
        "description": "GPT-4o multimodal rapido.",
        "context_window": 128_000,
        "input_cost_per_1m": 2.50,
        "output_cost_per_1m": 10.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("codex", "gpt-4o-mini"): {
        "description": "GPT-4o Mini economico e rapido.",
        "context_window": 128_000,
        "input_cost_per_1m": 0.15,
        "output_cost_per_1m": 0.60,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    # ── Google Gemini ────────────────────────────────────────────────
    ("gemini", "gemini-2.5-pro"): {
        "description": "Modelo avancado com janela de contexto massiva e raciocinio.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 1.25,
        "output_cost_per_1m": 10.00,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("gemini", "gemini-2.5-flash"): {
        "description": "Rapido e eficiente com grande janela de contexto.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 0.30,
        "output_cost_per_1m": 2.50,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("gemini", "gemini-2.5-flash-lite"): {
        "description": "Versao leve e ultrarapida do Flash.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 0.10,
        "output_cost_per_1m": 0.40,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("gemini", "gemini-2.0-flash"): {
        "description": "Modelo rapido de geracao anterior.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 0.10,
        "output_cost_per_1m": 0.40,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("gemini", "gemini-3-flash-preview"): {
        "description": "Preview do Gemini 3 Flash com melhorias de velocidade.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 0.30,
        "output_cost_per_1m": 2.50,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("gemini", "gemini-3.1-flash-lite-preview"): {
        "description": "Preview do Gemini 3.1 Flash-Lite ultrarapido.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 0.10,
        "output_cost_per_1m": 0.40,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("gemini", "gemini-3.1-pro-preview"): {
        "description": "Preview do Gemini 3.1 Pro com raciocinio avancado.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 1.25,
        "output_cost_per_1m": 10.00,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("gemini", "gemini-3.0-flash"): {
        "description": "Gemini 3.0 Flash legado.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 0.30,
        "output_cost_per_1m": 2.50,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("gemini", "gemini-3.0-flash-lite"): {
        "description": "Gemini 3.0 Flash-Lite legado.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 0.10,
        "output_cost_per_1m": 0.40,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    # Ollama models are discovered dynamically — no static metadata needed.
    # ── Perplexity (Q1 2026 pricing) ─────────────────────────────────
    ("perplexity", "sonar"): {
        "description": "Sonar com pesquisa web em tempo real.",
        "context_window": 127_000,
        "input_cost_per_1m": 1.00,
        "output_cost_per_1m": 1.00,
        "speed_tier": 4,
        "intelligence_tier": 3,
    },
    ("perplexity", "sonar-pro"): {
        "description": "Sonar Pro com fontes citadas e contexto maior.",
        "context_window": 200_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
    },
    ("perplexity", "sonar-reasoning"): {
        "description": "Sonar com raciocinio explicito e pesquisa web.",
        "context_window": 127_000,
        "input_cost_per_1m": 1.00,
        "output_cost_per_1m": 5.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high"),
        "effort_default": "medium",
    },
    ("perplexity", "sonar-reasoning-pro"): {
        "description": "Sonar Reasoning Pro para tarefas analiticas complexas.",
        "context_window": 127_000,
        "input_cost_per_1m": 2.00,
        "output_cost_per_1m": 8.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high"),
        "effort_default": "medium",
    },
    ("perplexity", "sonar-deep-research"): {
        "description": "Sonar Deep Research executa multiplas buscas e produz relatorios densos.",
        "context_window": 200_000,
        "input_cost_per_1m": 2.00,
        "output_cost_per_1m": 8.00,
        "speed_tier": 1,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high"),
        "effort_default": "high",
    },
    # ── Mistral La Plateforme (Q1 2026, plus pixtral-12b/saba added Q2 2026) ─
    ("mistral", "mistral-large-latest"): {
        "description": "Mistral Large — equilibrio entre raciocinio e custo.",
        "context_window": 131_000,
        "input_cost_per_1m": 2.00,
        "output_cost_per_1m": 6.00,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("mistral", "mistral-medium-latest"): {
        "description": "Mistral Medium — generalista de uso diario.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.40,
        "output_cost_per_1m": 2.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("mistral", "mistral-small-latest"): {
        "description": "Mistral Small — agil e barato.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.20,
        "output_cost_per_1m": 0.60,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("mistral", "codestral-latest"): {
        "description": "Codestral — modelo dedicado a codigo (auto-complete e edicao).",
        "context_window": 256_000,
        "input_cost_per_1m": 0.30,
        "output_cost_per_1m": 0.90,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("mistral", "pixtral-large-latest"): {
        "description": "Pixtral Large com visao e contexto longo.",
        "context_window": 131_000,
        "input_cost_per_1m": 2.00,
        "output_cost_per_1m": 6.00,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("mistral", "magistral-medium-latest"): {
        "description": "Magistral Medium com cadeia de raciocinio.",
        "context_window": 131_000,
        "input_cost_per_1m": 2.00,
        "output_cost_per_1m": 5.00,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("mistral", "magistral-small-latest"): {
        "description": "Magistral Small com cadeia de raciocinio enxuta.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.50,
        "output_cost_per_1m": 1.50,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("mistral", "ministral-8b-latest"): {
        "description": "Ministral 8B — pequeno e barato para borda.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.10,
        "output_cost_per_1m": 0.10,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("mistral", "ministral-3b-latest"): {
        "description": "Ministral 3B — menor da familia, ultra-barato.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.04,
        "output_cost_per_1m": 0.04,
        "speed_tier": 5,
        "intelligence_tier": 2,
    },
    ("mistral", "pixtral-12b-2409"): {
        "description": "Pixtral 12B — modelo pequeno multimodal com visao.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.15,
        "output_cost_per_1m": 0.15,
        "speed_tier": 4,
        "intelligence_tier": 3,
    },
    ("mistral", "mistral-saba-latest"): {
        "description": "Mistral Saba — modelo otimizado para idiomas regionais (arabe, indico).",
        "context_window": 131_000,
        "input_cost_per_1m": 0.20,
        "output_cost_per_1m": 0.60,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    # ── Qwen via DashScope International (Q1 2026, USD) ──────────────
    ("qwen", "qwen-max"): {
        "description": "Qwen Max — top de linha da familia.",
        "context_window": 32_000,
        "input_cost_per_1m": 1.60,
        "output_cost_per_1m": 6.40,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("qwen", "qwen-plus"): {
        "description": "Qwen Plus — generalista com bom custo-beneficio.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.40,
        "output_cost_per_1m": 1.20,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("qwen", "qwen-turbo"): {
        "description": "Qwen Turbo — barato e rapido.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.05,
        "output_cost_per_1m": 0.20,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("qwen", "qwen-long"): {
        "description": "Qwen Long — janela de 1M tokens.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 0.50,
        "output_cost_per_1m": 2.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
    },
    ("qwen", "qwen3-coder-plus"): {
        "description": "Qwen3 Coder Plus — agente de codigo de longa horizonte.",
        "context_window": 256_000,
        "input_cost_per_1m": 1.00,
        "output_cost_per_1m": 5.00,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("qwen", "qwen3-coder-flash"): {
        "description": "Qwen3 Coder Flash — agil para edicoes pontuais.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.10,
        "output_cost_per_1m": 0.50,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("qwen", "qwen2.5-72b-instruct"): {
        "description": "Qwen 2.5 72B Instruct.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.50,
        "output_cost_per_1m": 1.50,
        "speed_tier": 3,
        "intelligence_tier": 4,
    },
    ("qwen", "qwen2.5-coder-32b-instruct"): {
        "description": "Qwen 2.5 Coder 32B — codigo especializado.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.30,
        "output_cost_per_1m": 1.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("qwen", "qwen-vl-max"): {
        "description": "Qwen-VL Max com visao multimodal.",
        "context_window": 32_000,
        "input_cost_per_1m": 1.60,
        "output_cost_per_1m": 6.40,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("qwen", "qwen-vl-plus"): {
        "description": "Qwen-VL Plus com visao multimodal.",
        "context_window": 32_000,
        "input_cost_per_1m": 0.40,
        "output_cost_per_1m": 1.20,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("qwen", "qwq-32b"): {
        "description": "QwQ 32B — modelo de raciocinio ponderado.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.50,
        "output_cost_per_1m": 1.50,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("qwen", "qwen3-max"): {
        "description": "Qwen3 Max — flagship Qwen3, raciocinio e geracao avancados.",
        "context_window": 256_000,
        "input_cost_per_1m": 1.60,
        "output_cost_per_1m": 6.40,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("qwen", "qwen3-plus"): {
        "description": "Qwen3 Plus — generalista de uso diario com excelente custo-beneficio.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.40,
        "output_cost_per_1m": 1.20,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("qwen", "qwen3-flash"): {
        "description": "Qwen3 Flash — barato e rapido para automacao em larga escala.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.05,
        "output_cost_per_1m": 0.20,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("qwen", "qwen3-vl-max"): {
        "description": "Qwen3-VL Max — flagship multimodal com visao + raciocinio.",
        "context_window": 256_000,
        "input_cost_per_1m": 1.60,
        "output_cost_per_1m": 6.40,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("qwen", "qwen3-vl-plus"): {
        "description": "Qwen3-VL Plus — multimodal generalista.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.40,
        "output_cost_per_1m": 1.20,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("qwen", "qwen3-vl-flash"): {
        "description": "Qwen3-VL Flash — multimodal rapido (snapshot 2026-01-22).",
        "context_window": 131_000,
        "input_cost_per_1m": 0.10,
        "output_cost_per_1m": 0.30,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("qwen", "qwen3-omni-30b-a3b"): {
        "description": "Qwen3 Omni — entrada de audio/video/imagem/texto, saida de texto e voz.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.40,
        "output_cost_per_1m": 1.20,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("qwen", "qvq-72b-preview"): {
        "description": "QvQ 72B — raciocinio explicito sobre imagens (preview).",
        "context_window": 131_000,
        "input_cost_per_1m": 1.20,
        "output_cost_per_1m": 4.80,
        "speed_tier": 2,
        "intelligence_tier": 5,
    },
    # ── Kimi / Moonshot (Q1 2026) ────────────────────────────────────
    ("kimi", "kimi-k2.6"): {
        "description": "Kimi K2.6 — multimodal de proxima geracao para coding agentic e UI/UX.",
        "context_window": 256_000,
        "input_cost_per_1m": 0.74,
        "output_cost_per_1m": 3.49,
        "cached_input_cost_per_1m": 0.18,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("kimi", "kimi-k2.5"): {
        "description": "Kimi K2.5 — multimodal nativo com swarm de agentes self-directed.",
        "context_window": 256_000,
        "input_cost_per_1m": 0.60,
        "output_cost_per_1m": 2.50,
        "cached_input_cost_per_1m": 0.15,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("kimi", "kimi-k2-0905-preview"): {
        "description": "Kimi K2 (preview 0905) — geracao anterior, flagship com janela grande.",
        "context_window": 256_000,
        "input_cost_per_1m": 0.60,
        "output_cost_per_1m": 2.50,
        "cached_input_cost_per_1m": 0.15,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("kimi", "kimi-k2-0711-preview"): {
        "description": "Kimi K2 (snapshot 0711).",
        "context_window": 256_000,
        "input_cost_per_1m": 0.60,
        "output_cost_per_1m": 2.50,
        "cached_input_cost_per_1m": 0.15,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("kimi", "kimi-latest"): {
        "description": "Kimi Latest — flagship rolling.",
        "context_window": 200_000,
        "input_cost_per_1m": 2.00,
        "output_cost_per_1m": 5.00,
        "cached_input_cost_per_1m": 0.50,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("kimi", "moonshot-v1-128k"): {
        "description": "Moonshot v1 com janela de 128K.",
        "context_window": 128_000,
        "input_cost_per_1m": 2.00,
        "output_cost_per_1m": 5.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
    },
    ("kimi", "moonshot-v1-32k"): {
        "description": "Moonshot v1 com janela de 32K.",
        "context_window": 32_000,
        "input_cost_per_1m": 1.20,
        "output_cost_per_1m": 3.60,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("kimi", "moonshot-v1-8k"): {
        "description": "Moonshot v1 com janela de 8K — barato.",
        "context_window": 8_000,
        "input_cost_per_1m": 0.30,
        "output_cost_per_1m": 0.90,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("kimi", "moonshot-v1-auto"): {
        "description": "Moonshot v1 com selecao automatica de janela.",
        "context_window": 128_000,
        "input_cost_per_1m": 1.20,
        "output_cost_per_1m": 3.60,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("kimi", "kimi-thinking-preview"): {
        "description": "Kimi Thinking — raciocinio explicito.",
        "context_window": 200_000,
        "input_cost_per_1m": 2.00,
        "output_cost_per_1m": 5.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
    },
    ("kimi", "kimi-vision-2024-12-09"): {
        "description": "Kimi Vision com entendimento multimodal.",
        "context_window": 128_000,
        "input_cost_per_1m": 2.00,
        "output_cost_per_1m": 5.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
    },
    # ── Groq (LPU inference, Q1 2026) ────────────────────────────────
    ("groq", "llama-3.3-70b-versatile"): {
        "description": "Llama 3.3 70B Versatile via LPU — alta velocidade.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.59,
        "output_cost_per_1m": 0.79,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("groq", "llama-3.1-8b-instant"): {
        "description": "Llama 3.1 8B Instant — ultra-rapido e barato.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.05,
        "output_cost_per_1m": 0.08,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("groq", "llama-3.2-1b-preview"): {
        "description": "Llama 3.2 1B (preview) — micro, latencia minima.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.04,
        "output_cost_per_1m": 0.04,
        "speed_tier": 5,
        "intelligence_tier": 2,
    },
    ("groq", "llama-3.2-3b-preview"): {
        "description": "Llama 3.2 3B (preview) — pequeno e rapido.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.06,
        "output_cost_per_1m": 0.06,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("groq", "llama-3.2-11b-vision-preview"): {
        "description": "Llama 3.2 11B Vision (preview).",
        "context_window": 131_000,
        "input_cost_per_1m": 0.18,
        "output_cost_per_1m": 0.18,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("groq", "llama-3.2-90b-vision-preview"): {
        "description": "Llama 3.2 90B Vision (preview).",
        "context_window": 131_000,
        "input_cost_per_1m": 0.90,
        "output_cost_per_1m": 0.90,
        "speed_tier": 4,
        "intelligence_tier": 5,
    },
    ("groq", "mixtral-8x7b-32768"): {
        "description": "Mixtral 8x7B com janela de 32K.",
        "context_window": 32_768,
        "input_cost_per_1m": 0.24,
        "output_cost_per_1m": 0.24,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("groq", "gemma2-9b-it"): {
        "description": "Gemma2 9B Instruct — rapido e generalista.",
        "context_window": 8_000,
        "input_cost_per_1m": 0.20,
        "output_cost_per_1m": 0.20,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("groq", "qwen-2.5-32b"): {
        "description": "Qwen 2.5 32B via Groq.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.79,
        "output_cost_per_1m": 0.79,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("groq", "qwen-2.5-coder-32b"): {
        "description": "Qwen 2.5 Coder 32B via Groq.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.79,
        "output_cost_per_1m": 0.79,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("groq", "deepseek-r1-distill-llama-70b"): {
        "description": "DeepSeek R1 Distill (Llama 70B) com raciocinio.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.75,
        "output_cost_per_1m": 0.99,
        "speed_tier": 5,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high"),
        "effort_default": "medium",
    },
    ("groq", "openai/gpt-oss-120b"): {
        "description": "GPT-OSS 120B — flagship open-weight da OpenAI hospedado no Groq.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.15,
        "output_cost_per_1m": 0.75,
        "speed_tier": 5,
        "intelligence_tier": 5,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high"),
        "effort_default": "medium",
    },
    ("groq", "openai/gpt-oss-20b"): {
        "description": "GPT-OSS 20B — versao menor open-weight da OpenAI.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.10,
        "output_cost_per_1m": 0.50,
        "speed_tier": 5,
        "intelligence_tier": 4,
        "effort_kind": "enum",
        "effort_enum_values": ("low", "medium", "high"),
        "effort_default": "medium",
    },
    ("groq", "openai/gpt-oss-safeguard-20b"): {
        "description": "GPT-OSS Safeguard 20B — substitui llama-guard para policy-following e moderacao.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.10,
        "output_cost_per_1m": 0.50,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("groq", "moonshotai/kimi-k2-instruct"): {
        "description": "Kimi K2 Instruct hospedado no Groq.",
        "context_window": 131_000,
        "input_cost_per_1m": 1.00,
        "output_cost_per_1m": 3.00,
        "speed_tier": 5,
        "intelligence_tier": 5,
    },
    ("groq", "qwen/qwen3-32b"): {
        "description": "Qwen3 32B via Groq — substitui o mistral-saba-24b deprecado.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.79,
        "output_cost_per_1m": 0.79,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    # ── DeepSeek (Q2 2026 — V4 primary, V3 chat/reasoner sao aliases) ─
    ("deepseek", "deepseek-v4-pro"): {
        "description": "DeepSeek V4 Pro — flagship com modos thinking/non-thinking, contexto 1M.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 0.55,
        "output_cost_per_1m": 2.19,
        "cached_input_cost_per_1m": 0.14,
        "speed_tier": 3,
        "intelligence_tier": 5,
        "effort_kind": "tokens",
        "effort_token_min": 0,
        "effort_token_max": 8_000,
        "effort_default": 2_000,
    },
    ("deepseek", "deepseek-v4-flash"): {
        "description": "DeepSeek V4 Flash — barato e rapido, mesmos modos thinking/non-thinking.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 0.27,
        "output_cost_per_1m": 1.10,
        "cached_input_cost_per_1m": 0.07,
        "speed_tier": 5,
        "intelligence_tier": 4,
        "effort_kind": "tokens",
        "effort_token_min": 0,
        "effort_token_max": 8_000,
        "effort_default": 1_000,
    },
    ("deepseek", "deepseek-chat"): {
        "description": "DeepSeek Chat — alias de compatibilidade (deprecado em 2026/07/24, mapeia para V4 Flash).",
        "context_window": 64_000,
        "input_cost_per_1m": 0.27,
        "output_cost_per_1m": 1.10,
        "cached_input_cost_per_1m": 0.07,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("deepseek", "deepseek-reasoner"): {
        "description": "DeepSeek Reasoner — alias deprecado em 2026/07/24 (mapeia para V4 Pro thinking).",
        "context_window": 64_000,
        "input_cost_per_1m": 0.55,
        "output_cost_per_1m": 2.19,
        "cached_input_cost_per_1m": 0.14,
        "speed_tier": 2,
        "intelligence_tier": 5,
        "effort_kind": "tokens",
        "effort_token_min": 0,
        "effort_token_max": 8_000,
        "effort_default": 2_000,
    },
    # ── xAI Grok (Q1 2026, plus 4.3/4.1-fast/4-fast added Q2 2026) ───
    ("xai", "grok-4.3"): {
        "description": "Grok 4.3 — modelo recomendado pela xAI, mais inteligente e rapido da geracao.",
        "context_window": 256_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "cached_input_cost_per_1m": 0.75,
        "speed_tier": 4,
        "intelligence_tier": 5,
    },
    ("xai", "grok-4.1-fast"): {
        "description": "Grok 4.1 Fast — janela de 2M tokens com preco baixissimo.",
        "context_window": 2_000_000,
        "input_cost_per_1m": 0.20,
        "output_cost_per_1m": 0.50,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("xai", "grok-4-fast"): {
        "description": "Grok 4 Fast — variante de alta velocidade do Grok 4.",
        "context_window": 256_000,
        "input_cost_per_1m": 0.30,
        "output_cost_per_1m": 0.60,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("xai", "grok-4-0709"): {
        "description": "Grok 4 — flagship com raciocinio avancado.",
        "context_window": 256_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "cached_input_cost_per_1m": 0.75,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("xai", "grok-3"): {
        "description": "Grok 3 — generalista produtivo.",
        "context_window": 131_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "cached_input_cost_per_1m": 0.75,
        "speed_tier": 4,
        "intelligence_tier": 5,
    },
    ("xai", "grok-3-mini"): {
        "description": "Grok 3 Mini — barato e rapido.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.30,
        "output_cost_per_1m": 0.50,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("xai", "grok-3-fast"): {
        "description": "Grok 3 Fast — premium para latencia minima.",
        "context_window": 131_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 25.00,
        "speed_tier": 5,
        "intelligence_tier": 5,
    },
    ("xai", "grok-3-mini-fast"): {
        "description": "Grok 3 Mini Fast — barato com prioridade de fila.",
        "context_window": 131_000,
        "input_cost_per_1m": 0.60,
        "output_cost_per_1m": 4.00,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("xai", "grok-2-vision-1212"): {
        "description": "Grok 2 Vision — multimodal.",
        "context_window": 32_000,
        "input_cost_per_1m": 2.00,
        "output_cost_per_1m": 10.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("xai", "grok-2-1212"): {
        "description": "Grok 2 — generalista da geracao anterior.",
        "context_window": 131_000,
        "input_cost_per_1m": 2.00,
        "output_cost_per_1m": 10.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    # ── OpenRouter curated aliases (dynamic catalog fills provider/model IDs) ─
    ("openrouter", "openrouter/auto"): {
        "description": "Roteador automatico do OpenRouter para escolher modelos e fallback conforme disponibilidade.",
        "context_window": 2_000_000,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("openrouter", "~openai/gpt-mini-latest"): {
        "description": "Alias OpenRouter para o modelo mini mais recente da OpenAI.",
        "context_window": 400_000,
        "input_cost_per_1m": 0.75,
        "output_cost_per_1m": 4.50,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("openrouter", "~google/gemini-flash-latest"): {
        "description": "Alias OpenRouter para Gemini Flash recente, bom equilibrio de latencia e contexto longo.",
        "context_window": 1_048_576,
        "input_cost_per_1m": 0.50,
        "output_cost_per_1m": 3.00,
        "speed_tier": 5,
        "intelligence_tier": 4,
    },
    ("openrouter", "~google/gemini-pro-latest"): {
        "description": "Alias OpenRouter para Gemini Pro recente, focado em contexto longo e tarefas complexas.",
        "context_window": 1_048_576,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("openrouter", "~anthropic/claude-sonnet-latest"): {
        "description": "Alias OpenRouter para Claude Sonnet recente, forte em raciocinio e agentes.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "speed_tier": 4,
        "intelligence_tier": 5,
    },
    ("openrouter", "~openai/gpt-latest"): {
        "description": "Alias OpenRouter para o modelo GPT generalista mais recente da OpenAI.",
        "context_window": 1_050_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 30.00,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("openrouter", "openrouter/pareto-code"): {
        "description": "Roteador OpenRouter orientado a tarefas de codigo.",
        "context_window": 2_000_000,
        "speed_tier": 4,
        "intelligence_tier": 5,
    },
}

_STATIC_PROVIDER_MODELS: tuple[ProviderModelDefinition, ...] = (
    ProviderModelDefinition(
        "codex", "gpt-image-2", "GPT Image 2", "image", "Modelo oficial da OpenAI para geracao de imagem."
    ),
    ProviderModelDefinition(
        "codex", "gpt-image-1.5", "GPT Image 1.5", "image", "Modelo oficial da OpenAI para imagem."
    ),
    ProviderModelDefinition(
        "codex", "gpt-audio-1.5", "GPT Audio 1.5", "audio", "Modelo de audio multimodal da OpenAI."
    ),
    ProviderModelDefinition(
        "codex",
        "whisper-1",
        "Whisper API",
        "transcription",
        "Transcricao via OpenAI Whisper API.",
    ),
    ProviderModelDefinition(
        "codex",
        "gpt-4o-transcribe",
        "GPT-4o Transcribe",
        "transcription",
        "Transcricao principal da OpenAI.",
    ),
    ProviderModelDefinition(
        "codex",
        "gpt-4o-mini-transcribe",
        "GPT-4o mini Transcribe",
        "transcription",
        "Transcricao economica da OpenAI.",
    ),
    ProviderModelDefinition(
        "gemini",
        "gemini-2.5-flash-image-preview",
        "Gemini 2.5 Flash Image Preview (Nano Banana 1)",
        "image",
        "Versao preview do Gemini 2.5 Flash Image, popularmente chamada de Nano Banana.",
        status="preview",
    ),
    ProviderModelDefinition(
        "gemini",
        "gemini-2.5-flash-image",
        "Gemini 2.5 Flash Image (Nano Banana)",
        "image",
        "Modelo estavel do Gemini 2.5 Flash Image para geracao e edicao de imagem.",
    ),
    ProviderModelDefinition(
        "gemini",
        "gemini-3-pro-image-preview",
        "Gemini 3 Pro Image Preview (Nano Banana 2)",
        "image",
        "Modelo Gemini 3 Pro Image Preview para geracao e edicao premium de imagem.",
        status="preview",
    ),
    ProviderModelDefinition(
        "gemini",
        "imagen-4.0-generate-001",
        "Imagen 4 Standard",
        "image",
        "Geracao de imagem com Imagen 4.",
    ),
    ProviderModelDefinition(
        "gemini",
        "imagen-4.0-ultra-generate-001",
        "Imagen 4 Ultra",
        "image",
        "Geracao premium de imagem com Imagen 4 Ultra.",
    ),
    ProviderModelDefinition(
        "gemini",
        "veo-3.0-generate-preview",
        "Veo 3",
        "video",
        "Geracao de video com audio.",
        status="preview",
    ),
    ProviderModelDefinition(
        "gemini",
        "veo-3.0-fast-generate-preview",
        "Veo 3 Fast",
        "video",
        "Versao acelerada do Veo 3.",
        status="preview",
    ),
    ProviderModelDefinition(
        "gemini",
        "veo-3.1-generate-preview",
        "Veo 3.1",
        "video",
        "Geracao de video com audio e melhorias de image-to-video no Gemini API.",
        status="preview",
    ),
    ProviderModelDefinition(
        "gemini",
        "veo-3.1-fast-generate-preview",
        "Veo 3.1 Fast",
        "video",
        "Variante acelerada do Veo 3.1 para video com audio e image-to-video.",
        status="preview",
    ),
    ProviderModelDefinition(
        "gemini",
        "gemini-2.5-flash-native-audio-preview-09-2025",
        "Gemini 2.5 Flash Native Audio",
        "audio",
        "Modelo oficial de audio nativo da Gemini.",
        status="preview",
    ),
    ProviderModelDefinition(
        "gemini",
        "lyria-realtime-exp",
        "Lyria Realtime",
        "music",
        "Geracao musical em tempo real.",
        status="experimental",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_v3",
        "Eleven v3",
        "audio",
        "Modelo flagship de TTS da ElevenLabs.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_ttv_v3",
        "Eleven v3 Text to Voice",
        "audio",
        "Voice design da familia Eleven v3.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_multilingual_v2",
        "Eleven Multilingual v2",
        "audio",
        "Stable multilingual TTS model.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_flash_v2_5",
        "Eleven Flash v2.5",
        "audio",
        "Modelo rapido e economico para voz.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_flash_v2",
        "Eleven Flash v2",
        "audio",
        "Versao anterior focada em baixa latencia.",
        status="legacy",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_turbo_v2_5",
        "Eleven Turbo v2.5",
        "audio",
        "Modelo turbo para sintese de fala.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_multilingual_sts_v2",
        "Eleven Multilingual STS v2",
        "audio",
        "Multilingual speech-to-speech.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_multilingual_ttv_v2",
        "Eleven Multilingual TTV v2",
        "audio",
        "Multilingual text-to-voice designer.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_english_sts_v2",
        "Eleven English STS v2",
        "audio",
        "Speech-to-speech focado em ingles.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_text_to_sound_v2",
        "Eleven Text to Sound v2",
        "audio",
        "Geracao de efeitos sonoros.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_multilingual_v1",
        "Eleven Multilingual v1",
        "audio",
        "Previous multilingual model.",
        status="deprecated",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_monolingual_v1",
        "Eleven Monolingual v1",
        "audio",
        "Modelo ingles anterior.",
        status="deprecated",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "scribe_v2",
        "Scribe v2",
        "transcription",
        "Transcricao principal da ElevenLabs.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "scribe_v2_realtime",
        "Scribe v2 Realtime",
        "transcription",
        "Transcricao em tempo real.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "scribe_v1",
        "Scribe v1",
        "transcription",
        "Transcricao legada da ElevenLabs.",
        status="legacy",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "music_v1",
        "Eleven Music",
        "music",
        "Geracao musical da ElevenLabs.",
    ),
    ProviderModelDefinition("kokoro", "kokoro-v1", "Kokoro v1", "audio", "Modelo local de TTS."),
    ProviderModelDefinition(
        "supertonic",
        "supertonic-3",
        "Supertonic 3",
        "audio",
        "Modelo local ONNX de TTS multilingue com 31 idiomas.",
    ),
    ProviderModelDefinition(
        "supertonic",
        "supertonic-2",
        "Supertonic 2",
        "audio",
        "Modelo local ONNX legado com cobertura multilingue menor.",
        status="legacy",
    ),
    ProviderModelDefinition(
        "supertonic",
        "supertonic",
        "Supertonic",
        "audio",
        "Modelo local ONNX legado em ingles.",
        status="legacy",
    ),
    ProviderModelDefinition(
        "whispercpp",
        "whisper-cpp-local",
        "Whisper CPP (local)",
        "transcription",
        "Transcricao local gratuita executada pela API do agent com whisper.cpp.",
    ),
    # ── Mistral non-general (Q2 2026) ────────────────────────────────
    ProviderModelDefinition(
        "mistral",
        "mistral-ocr-latest",
        "Mistral OCR",
        "transcription",
        "Extracao de texto de documentos (PDF/imagens) via Mistral OCR — $2/1k paginas.",
    ),
    # ── Qwen non-general (Q1 2026) ───────────────────────────────────
    ProviderModelDefinition(
        "qwen",
        "qwen3-tts-flash",
        "Qwen3 TTS Flash",
        "audio",
        "Sintese de fala da familia Qwen3 com voice cloning e voice design (10 idiomas).",
    ),
    ProviderModelDefinition(
        "qwen",
        "qwen-tts",
        "Qwen TTS",
        "audio",
        "Sintese de fala Qwen com vozes nativas (geracao anterior).",
        status="legacy",
    ),
    ProviderModelDefinition(
        "qwen",
        "cosyvoice-v2",
        "CosyVoice v2",
        "audio",
        "TTS multilingue baseado em CosyVoice integrado ao DashScope.",
    ),
    ProviderModelDefinition(
        "qwen",
        "qwen-image-plus",
        "Qwen Image Plus",
        "image",
        "Modelo text-to-image com renderizacao avancada de texto (chines/ingles).",
    ),
    ProviderModelDefinition(
        "qwen",
        "wan2.2-t2v-plus",
        "Wan 2.2 Text-to-Video",
        "video",
        "Geracao de video a partir de texto (alta qualidade).",
    ),
    ProviderModelDefinition(
        "qwen",
        "wan2.2-i2v-plus",
        "Wan 2.2 Image-to-Video",
        "video",
        "Animacao de imagens (image-to-video) com Wan 2.2.",
    ),
    ProviderModelDefinition(
        "qwen",
        "paraformer-v2",
        "Paraformer v2",
        "transcription",
        "ASR multilingue otimizado para portugues, ingles, mandarim e outras linguas.",
    ),
    ProviderModelDefinition(
        "qwen",
        "sensevoice-v1",
        "SenseVoice v1",
        "transcription",
        "Reconhecimento de fala multilingue com deteccao de emocao.",
    ),
    # ── Groq non-general (Q2 2026) ───────────────────────────────────
    ProviderModelDefinition(
        "groq",
        "whisper-large-v3",
        "Whisper Large v3",
        "transcription",
        "Transcricao de audio com qualidade de referencia, hospedado no Groq.",
    ),
    ProviderModelDefinition(
        "groq",
        "whisper-large-v3-turbo",
        "Whisper Large v3 Turbo",
        "transcription",
        "Versao acelerada do Whisper Large v3 (substitui distil-whisper-large-v3-en).",
    ),
    # ── xAI Grok non-general (Q2 2026) ───────────────────────────────
    ProviderModelDefinition(
        "xai",
        "grok-image-1",
        "Grok Image",
        "image",
        "Geracao de imagem da xAI — $0.02/imagem.",
    ),
    ProviderModelDefinition(
        "xai",
        "grok-image-pro",
        "Grok Image Pro",
        "image",
        "Geracao de imagem premium da xAI — $0.07/imagem (qualidade superior).",
    ),
    ProviderModelDefinition(
        "xai",
        "grok-realtime",
        "Grok Realtime Voice",
        "audio",
        "API de voz em tempo real (Voice Agent) — $0.05/minuto.",
    ),
)


def resolve_model_function_catalog() -> list[dict[str, Any]]:
    return [{"id": item.id, "title": item.title, "description": item.description} for item in _MODEL_FUNCTIONS]


def _general_model_title(provider_id: str, model_id: str) -> str:
    lookup = _DYNAMIC_GENERAL_MODEL_LABELS.get(provider_id, {})
    return lookup.get(model_id, model_id)


def resolve_known_general_model_ids(provider_id: str) -> list[str]:
    normalized_provider = provider_id.strip().lower()
    return list(_DYNAMIC_GENERAL_MODEL_LABELS.get(normalized_provider, {}).keys())


_EFFORT_CAPABILITY_OVERRIDES: dict[tuple[str, str], dict[str, Any] | None] = {
    # OpenAI/Codex current reasoning controls.
    ("codex", "gpt-5.5"): {"kind": "enum", "values": ("none", "low", "medium", "high", "xhigh"), "default": "medium"},
    ("codex", "gpt-5.4"): {"kind": "enum", "values": ("none", "low", "medium", "high", "xhigh"), "default": "medium"},
    ("codex", "gpt-5.4-mini"): {
        "kind": "enum",
        "values": ("none", "low", "medium", "high", "xhigh"),
        "default": "medium",
    },
    ("codex", "gpt-5.4-nano"): {
        "kind": "enum",
        "values": ("none", "low", "medium", "high", "xhigh"),
        "default": "medium",
    },
    ("codex", "gpt-5.4-pro"): {
        "kind": "enum",
        "values": ("none", "low", "medium", "high", "xhigh"),
        "default": "high",
    },
    ("codex", "gpt-5.1"): {"kind": "enum", "values": ("none", "low", "medium", "high"), "default": "none"},
    ("codex", "gpt-5.1-codex"): {
        "kind": "enum",
        "values": ("none", "low", "medium", "high"),
        "default": "none",
    },
    ("codex", "gpt-5.1-codex-max"): {
        "kind": "enum",
        "values": ("none", "low", "medium", "high"),
        "default": "none",
    },
    ("codex", "gpt-5.1-codex-mini"): {
        "kind": "enum",
        "values": ("none", "low", "medium", "high"),
        "default": "none",
    },
    ("codex", "gpt-5-pro"): {"kind": "enum", "values": ("high",), "default": "high"},
    # Claude Code CLI model-specific effort support.
    ("claude", "claude-opus-4-7"): {
        "kind": "enum",
        "values": ("low", "medium", "high", "xhigh", "max"),
        "default": "xhigh",
    },
    ("claude", "claude-opus-4-6"): {
        "kind": "enum",
        "values": ("low", "medium", "high", "max"),
        "default": "high",
    },
    ("claude", "claude-sonnet-4-6"): {
        "kind": "enum",
        "values": ("low", "medium", "high", "max"),
        "default": "high",
    },
    ("claude", "claude-opus-4-5-20251101"): None,
    ("claude", "claude-sonnet-4-5-20250929"): None,
    ("claude", "claude-opus-4-1"): None,
    ("claude", "claude-opus-4-1-20250805"): None,
    ("claude", "claude-sonnet-4-5"): None,
    ("claude", "claude-sonnet-4-20250514"): None,
    ("claude", "claude-3-7-sonnet-latest"): None,
    ("claude", "claude-3-7-sonnet-20250219"): None,
    # Perplexity reasoning effort.
    ("perplexity", "sonar-reasoning"): {
        "kind": "enum",
        "values": ("minimal", "low", "medium", "high"),
        "default": "medium",
    },
    ("perplexity", "sonar-reasoning-pro"): {
        "kind": "enum",
        "values": ("minimal", "low", "medium", "high"),
        "default": "medium",
    },
    ("perplexity", "sonar-deep-research"): {
        "kind": "enum",
        "values": ("minimal", "low", "medium", "high"),
        "default": "medium",
    },
    # DeepSeek thinking mode uses enum effort plus an explicit thinking toggle.
    ("deepseek", "deepseek-v4-pro"): {"kind": "enum", "values": ("high", "max"), "default": "high"},
    ("deepseek", "deepseek-v4-flash"): {"kind": "enum", "values": ("high", "max"), "default": "high"},
    ("deepseek", "deepseek-reasoner"): {"kind": "enum", "values": ("high", "max"), "default": "high"},
    # Groq reasoning support is model-specific.
    ("groq", "deepseek-r1-distill-llama-70b"): None,
    ("groq", "openai/gpt-oss-120b"): {
        "kind": "enum",
        "values": ("low", "medium", "high"),
        "default": "medium",
    },
    ("groq", "openai/gpt-oss-20b"): {
        "kind": "enum",
        "values": ("low", "medium", "high"),
        "default": "medium",
    },
    ("groq", "qwen/qwen3-32b"): {"kind": "enum", "values": ("none", "default"), "default": "default"},
    # xAI documents configurable reasoning only for the multi-agent model.
    ("xai", "grok-4.20-multi-agent"): {
        "kind": "enum",
        "values": ("low", "medium", "high", "xhigh"),
        "default": "medium",
    },
}


def get_model_effort_capability(provider_id: str, model_id: str) -> dict[str, Any] | None:
    """Return effort capability for a model, or None if it does not support effort.

    Output shape:
      enum  -> {"kind": "enum",   "values": tuple[str, ...], "default": str | None}
      tokens-> {"kind": "tokens", "min": int, "max": int,    "default": int | None}
    """
    normalized_provider = provider_id.strip().lower()
    normalized_model = model_id.strip()
    override_key = (normalized_provider, normalized_model)
    if override_key in _EFFORT_CAPABILITY_OVERRIDES:
        override = _EFFORT_CAPABILITY_OVERRIDES[override_key]
        return dict(override) if override is not None else None
    meta = _GENERAL_MODEL_METADATA.get((normalized_provider, normalized_model))
    if not meta:
        return None
    kind = meta.get("effort_kind")
    if kind == "enum":
        values = tuple(meta.get("effort_enum_values", ()))
        if not values:
            return None
        return {
            "kind": "enum",
            "values": values,
            "default": meta.get("effort_default"),
        }
    if kind == "tokens":
        return {
            "kind": "tokens",
            "min": int(meta.get("effort_token_min", 0)),
            "max": int(meta.get("effort_token_max", 0)),
            "default": meta.get("effort_default"),
        }
    return None


def _prettify_ollama_model_id(model_id: str) -> str:
    """Generate a human-readable display name from an Ollama model ID."""
    name = model_id.split(":")[0]
    name = name.replace("-", " ").replace("_", " ")
    # Capitalize each word, with special casing for known names
    _BRAND_CASE: dict[str, str] = {
        "llama": "Llama",
        "qwen": "Qwen",
        "gemma": "Gemma",
        "phi": "Phi",
        "mistral": "Mistral",
        "deepseek": "DeepSeek",
        "gpt": "GPT",
        "codellama": "CodeLlama",
        "starcoder": "StarCoder",
        "devstral": "Devstral",
        "wizardcoder": "WizardCoder",
        "orca": "Orca",
        "vicuna": "Vicuna",
        "falcon": "Falcon",
        "yi": "Yi",
        "solar": "Solar",
        "command": "Command",
        "mixtral": "Mixtral",
        "internlm": "InternLM",
        "codegemma": "CodeGemma",
    }
    words = name.split()
    result: list[str] = []
    for word in words:
        lower = word.lower()
        matched = False
        for brand_key, brand_val in _BRAND_CASE.items():
            if lower.startswith(brand_key):
                result.append(brand_val + word[len(brand_key) :])
                matched = True
                break
        if not matched:
            result.append(word.capitalize())
    tag = model_id.split(":", 1)[1] if ":" in model_id else ""
    if tag and tag != "latest":
        result.append(tag.upper() if tag.replace(".", "").replace("-", "").isdigit() else tag.capitalize())
    return " ".join(result)


def _parse_parameter_size_gb(raw: str) -> float:
    """Parse parameter size string (e.g. '7B', '120B', '0.5B') to billions."""
    if not raw:
        return 0.0
    raw = raw.strip().upper()
    if raw.endswith("B"):
        try:
            return float(raw[:-1])
        except ValueError:
            return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _ollama_speed_tier(param_billions: float) -> int:
    if param_billions <= 0:
        return 3
    if param_billions <= 3:
        return 5
    if param_billions <= 14:
        return 4
    if param_billions <= 40:
        return 3
    if param_billions <= 100:
        return 2
    return 1


def _ollama_intelligence_tier(param_billions: float) -> int:
    if param_billions <= 0:
        return 3
    if param_billions <= 3:
        return 2
    if param_billions <= 14:
        return 3
    if param_billions <= 40:
        return 4
    return 5


def _ollama_context_window(param_billions: float) -> int:
    if param_billions <= 0:
        return 8_000
    if param_billions <= 7:
        return 32_000
    if param_billions <= 30:
        return 64_000
    return 128_000


def resolve_provider_function_model_catalog(
    provider_id: str,
    *,
    available_models: list[str] | None = None,
    ollama_catalog_items: list[dict[str, Any]] | None = None,
    whisper_catalog_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    normalized_provider = provider_id.strip().lower()
    general_models = list(
        dict.fromkeys(
            [str(model).strip() for model in (available_models or []) if str(model).strip()]
            + resolve_known_general_model_ids(normalized_provider)
        )
    )
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    # Build lookup for Ollama catalog items (dynamic data from /api/tags)
    ollama_lookup: dict[str, dict[str, Any]] = {}
    if normalized_provider == "ollama" and ollama_catalog_items:
        for cat_item in ollama_catalog_items:
            mid = str(cat_item.get("model_id") or cat_item.get("name") or "").strip()
            if mid:
                ollama_lookup[mid] = cat_item

    if normalized_provider == "whispercpp" and whisper_catalog_items is not None:
        for cat_item in whisper_catalog_items:
            if not bool(cat_item.get("downloaded")):
                continue
            variant_id = str(cat_item.get("variant_id") or cat_item.get("model_id") or "").strip()
            if not variant_id:
                continue
            entry_key = ("transcription", variant_id)
            if entry_key in seen:
                continue
            seen.add(entry_key)
            bytes_on_disk = int(cat_item.get("bytes") or 0) or None
            approx_size = int(cat_item.get("approx_size_bytes") or 0) or None
            items.append(
                {
                    "provider_id": normalized_provider,
                    "model_id": variant_id,
                    "title": str(cat_item.get("label") or variant_id),
                    "function_id": "transcription",
                    "description": str(cat_item.get("description") or "Transcricao local via whisper.cpp."),
                    "status": "current",
                    "context_window": 0,
                    "input_cost_per_1m": 0,
                    "output_cost_per_1m": 0,
                    "speed_tier": 3,
                    "intelligence_tier": 3,
                    "filename": str(cat_item.get("filename") or "") or None,
                    "local_path": str(cat_item.get("local_path") or "") or None,
                    "size_bytes": bytes_on_disk or approx_size,
                    "downloaded": True,
                }
            )

    for model_id in general_models:
        normalized_model = str(model_id).strip()
        if not normalized_model:
            continue
        entry_key = ("general", normalized_model)
        if entry_key in seen:
            continue
        seen.add(entry_key)
        meta = _GENERAL_MODEL_METADATA.get((normalized_provider, normalized_model), {})

        # For Ollama, generate metadata dynamically from catalog data
        if normalized_provider == "ollama" and not meta:
            cat = ollama_lookup.get(normalized_model, {})
            family = str(cat.get("family") or "").strip()
            param_size_raw = str(cat.get("parameter_size") or "").strip()
            quantization = str(cat.get("quantization_level") or "").strip()
            param_b = _parse_parameter_size_gb(param_size_raw)

            desc_parts: list[str] = []
            if family:
                desc_parts.append(f"Familia {family}")
            if param_size_raw:
                desc_parts.append(f"{param_size_raw} parametros")
            if quantization:
                desc_parts.append(f"quantizacao {quantization}")
            description = (", ".join(desc_parts) + ".") if desc_parts else "Modelo local Ollama."

            meta = {
                "description": description,
                "context_window": _ollama_context_window(param_b),
                "speed_tier": _ollama_speed_tier(param_b),
                "intelligence_tier": _ollama_intelligence_tier(param_b),
            }

        title = _general_model_title(normalized_provider, normalized_model)
        if normalized_provider == "ollama" and title == normalized_model:
            title = _prettify_ollama_model_id(normalized_model)

        entry: dict[str, Any] = {
            "provider_id": normalized_provider,
            "model_id": normalized_model,
            "title": title,
            "function_id": "general",
            "description": meta.get("description", "Modelo geral do provider."),
            "status": "current",
            "context_window": meta.get("context_window", 0),
            "input_cost_per_1m": meta.get("input_cost_per_1m", 0),
            "output_cost_per_1m": meta.get("output_cost_per_1m", 0),
            "speed_tier": meta.get("speed_tier", 3),
            "intelligence_tier": meta.get("intelligence_tier", 3),
        }

        effort_capability = get_model_effort_capability(normalized_provider, normalized_model)
        if effort_capability is not None:
            entry["effort_kind"] = effort_capability["kind"]
            if effort_capability["kind"] == "enum":
                entry["effort_enum_values"] = list(effort_capability["values"])
            else:
                entry["effort_token_min"] = effort_capability["min"]
                entry["effort_token_max"] = effort_capability["max"]
            if effort_capability.get("default") is not None:
                entry["effort_default"] = effort_capability["default"]

        # Pass Ollama-specific fields for the frontend tooltip
        if normalized_provider == "ollama":
            cat = ollama_lookup.get(normalized_model, {})
            entry["family"] = str(cat.get("family") or "").strip() or None
            entry["parameter_size"] = str(cat.get("parameter_size") or "").strip() or None
            entry["quantization_level"] = str(cat.get("quantization_level") or "").strip() or None
            entry["format"] = str(cat.get("format") or "").strip() or None
            entry["size_bytes"] = int(cat.get("size") or 0) or None

        items.append(entry)

    for definition in _STATIC_PROVIDER_MODELS:
        if normalized_provider == "whispercpp" and whisper_catalog_items is not None:
            continue
        if definition.provider_id != normalized_provider:
            continue
        entry_key = (definition.function_id, definition.model_id)
        if entry_key in seen:
            continue
        seen.add(entry_key)
        items.append(
            {
                "provider_id": definition.provider_id,
                "model_id": definition.model_id,
                "title": definition.title,
                "function_id": definition.function_id,
                "description": definition.description,
                "status": definition.status,
                "context_window": definition.context_window,
                "input_cost_per_1m": definition.input_cost_per_1m,
                "output_cost_per_1m": definition.output_cost_per_1m,
                "speed_tier": definition.speed_tier,
                "intelligence_tier": definition.intelligence_tier,
            }
        )

    items.sort(
        key=lambda item: (
            MODEL_FUNCTION_IDS.index(str(item["function_id"]))
            if str(item["function_id"]) in MODEL_FUNCTION_IDS
            else len(MODEL_FUNCTION_IDS),
            str(item["title"]).lower(),
        )
    )
    return items


def build_function_model_catalog(
    provider_catalog: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    by_function: dict[str, list[dict[str, Any]]] = {function_id: [] for function_id in MODEL_FUNCTION_IDS}
    for provider_id, payload in provider_catalog.items():
        if not bool(payload.get("show_in_settings", True)):
            continue
        provider_title = str(payload.get("title") or provider_id)
        provider_vendor = str(payload.get("vendor") or provider_title)
        category = str(payload.get("category") or "general")
        command_present = bool(payload.get("command_present", False))
        enabled = bool(payload.get("enabled", False))
        functional_models: list[dict[str, Any]] = []
        for item in payload.get("functional_models") or []:
            if not isinstance(item, dict):
                continue
            functional_model = dict(item)
            if (
                functional_model.get("provider_id")
                and functional_model.get("model_id")
                and functional_model.get("function_id")
            ):
                functional_models.append(functional_model)
        if not functional_models:
            functional_models = resolve_provider_function_model_catalog(
                provider_id,
                available_models=[str(item) for item in payload.get("available_models") or []],
            )
        for model in functional_models:
            function_id = str(model["function_id"])
            by_function.setdefault(function_id, []).append(
                {
                    **model,
                    "provider_title": provider_title,
                    "provider_vendor": provider_vendor,
                    "provider_category": category,
                    "provider_enabled": enabled,
                    "command_present": command_present,
                }
            )
    for function_id in list(by_function):
        by_function[function_id].sort(
            key=lambda item: (str(item["provider_title"]).lower(), str(item["title"]).lower())
        )
    return by_function
