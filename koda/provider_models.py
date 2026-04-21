"""Canonical provider model catalogs grouped by product functionality."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
        "claude-opus-4-6": "Claude Opus 4.6",
        "claude-sonnet-4-6": "Claude Sonnet 4.6",
        "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
    },
    "codex": {
        "gpt-5.4": "GPT-5.4",
        "gpt-5.4-mini": "GPT-5.4 Mini",
        "gpt-5.3-codex": "GPT-5.3 Codex",
        "gpt-5.3-codex-spark": "GPT-5.3 Codex Spark",
        "gpt-5.2-codex": "GPT-5.2 Codex",
        "gpt-5.2": "GPT-5.2",
        "gpt-5.1-codex-max": "GPT-5.1 Codex Max",
        "gpt-5.1-codex-mini": "GPT-5.1 Codex Mini",
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
}

# ── Real pricing & metadata for general (dynamic) models ─────────────
# Keyed by (provider_id, model_id). All costs in USD per 1M tokens.
# Sources: platform.claude.com/docs, developers.openai.com/api/docs/pricing,
#          ai.google.dev/gemini-api/docs/pricing  (verified 2026-04)
_GENERAL_MODEL_METADATA: dict[tuple[str, str], dict[str, Any]] = {
    # ── Anthropic ────────────────────────────────────────────────────
    ("claude", "claude-opus-4-6"): {
        "description": "Modelo de raciocinio mais avancado com pensamento estendido.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 25.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
    },
    ("claude", "claude-sonnet-4-6"): {
        "description": "Equilibrio entre velocidade e inteligencia para tarefas complexas.",
        "context_window": 1_000_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
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
    },
    ("claude", "claude-opus-4-1-20250805"): {
        "description": "Claude Opus 4.1 snapshot.",
        "context_window": 200_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 25.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
    },
    ("claude", "claude-sonnet-4-5"): {
        "description": "Claude Sonnet 4.5 com raciocinio forte.",
        "context_window": 200_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("claude", "claude-sonnet-4-20250514"): {
        "description": "Claude Sonnet 4 snapshot.",
        "context_window": 200_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("claude", "claude-3-7-sonnet-latest"): {
        "description": "Claude 3.7 Sonnet com raciocinio estendido.",
        "context_window": 200_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
    },
    ("claude", "claude-3-7-sonnet-20250219"): {
        "description": "Claude 3.7 Sonnet snapshot.",
        "context_window": 200_000,
        "input_cost_per_1m": 3.00,
        "output_cost_per_1m": 15.00,
        "speed_tier": 4,
        "intelligence_tier": 4,
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
    ("codex", "gpt-5.4"): {
        "description": "Modelo de ultima geracao com raciocinio avancado e contexto massivo.",
        "context_window": 1_050_000,
        "input_cost_per_1m": 2.50,
        "output_cost_per_1m": 15.00,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("codex", "gpt-5.4-mini"): {
        "description": "Versao compacta e rapida do GPT-5.4.",
        "context_window": 400_000,
        "input_cost_per_1m": 0.75,
        "output_cost_per_1m": 4.50,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("codex", "gpt-5.4-nano"): {
        "description": "Versao ultrarapida para tarefas simples e alta vazao.",
        "context_window": 400_000,
        "input_cost_per_1m": 0.20,
        "output_cost_per_1m": 1.25,
        "speed_tier": 5,
        "intelligence_tier": 2,
    },
    ("codex", "gpt-5.4-pro"): {
        "description": "Versao premium do GPT-5.4 com raciocinio estendido.",
        "context_window": 1_050_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 30.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
    },
    ("codex", "gpt-5.3-codex"): {
        "description": "Especializado em codigo e raciocinio tecnico.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.75,
        "output_cost_per_1m": 14.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
    },
    ("codex", "gpt-5.3-codex-spark"): {
        "description": "Versao agil do GPT-5.3 Codex para iteracao rapida.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.75,
        "output_cost_per_1m": 14.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
    },
    ("codex", "gpt-5.2-codex"): {
        "description": "Codex para tarefas de engenharia de software.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.75,
        "output_cost_per_1m": 14.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
    },
    ("codex", "gpt-5.2"): {
        "description": "Modelo GPT-5.2 de proposito geral.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.25,
        "output_cost_per_1m": 10.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
    },
    ("codex", "gpt-5.1-codex-max"): {
        "description": "Codex 5.1 Max para projetos complexos e longos.",
        "context_window": 400_000,
        "input_cost_per_1m": 2.50,
        "output_cost_per_1m": 15.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
    },
    ("codex", "gpt-5.1-codex-mini"): {
        "description": "Codex 5.1 Mini para tarefas de codigo rapidas.",
        "context_window": 400_000,
        "input_cost_per_1m": 0.75,
        "output_cost_per_1m": 4.50,
        "speed_tier": 4,
        "intelligence_tier": 3,
    },
    ("codex", "gpt-5"): {
        "description": "Modelo GPT de quinta geracao com capacidades avancadas.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.25,
        "output_cost_per_1m": 10.00,
        "speed_tier": 3,
        "intelligence_tier": 5,
    },
    ("codex", "gpt-5-mini"): {
        "description": "Versao compacta e eficiente do GPT-5.",
        "context_window": 400_000,
        "input_cost_per_1m": 0.25,
        "output_cost_per_1m": 2.00,
        "speed_tier": 5,
        "intelligence_tier": 3,
    },
    ("codex", "gpt-5-nano"): {
        "description": "Modelo ultrarapido para tarefas simples de alta vazao.",
        "context_window": 400_000,
        "input_cost_per_1m": 0.05,
        "output_cost_per_1m": 0.40,
        "speed_tier": 5,
        "intelligence_tier": 2,
    },
    ("codex", "gpt-5-pro"): {
        "description": "GPT-5 Pro com raciocinio estendido e precisao maxima.",
        "context_window": 400_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 30.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
    },
    ("codex", "gpt-5-codex"): {
        "description": "GPT-5 Codex para engenharia de software.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.25,
        "output_cost_per_1m": 10.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
    },
    ("codex", "gpt-5.2-pro"): {
        "description": "GPT-5.2 Pro com raciocinio avancado.",
        "context_window": 400_000,
        "input_cost_per_1m": 5.00,
        "output_cost_per_1m": 30.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
    },
    ("codex", "gpt-5.1"): {
        "description": "Modelo GPT-5.1 de proposito geral.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.25,
        "output_cost_per_1m": 10.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
    },
    ("codex", "gpt-5.1-codex"): {
        "description": "Codex 5.1 para engenharia de software.",
        "context_window": 400_000,
        "input_cost_per_1m": 1.75,
        "output_cost_per_1m": 14.00,
        "speed_tier": 3,
        "intelligence_tier": 4,
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
    },
    ("codex", "o3"): {
        "description": "Modelo de raciocinio avancado da OpenAI.",
        "context_window": 200_000,
        "input_cost_per_1m": 2.00,
        "output_cost_per_1m": 8.00,
        "speed_tier": 2,
        "intelligence_tier": 5,
    },
    ("codex", "o3-mini"): {
        "description": "Versao compacta do o3 com bom custo-beneficio.",
        "context_window": 200_000,
        "input_cost_per_1m": 1.10,
        "output_cost_per_1m": 4.40,
        "speed_tier": 3,
        "intelligence_tier": 4,
    },
    ("codex", "o3-pro"): {
        "description": "o3 Pro com raciocinio profundo e alta fidelidade.",
        "context_window": 200_000,
        "input_cost_per_1m": 20.00,
        "output_cost_per_1m": 80.00,
        "speed_tier": 1,
        "intelligence_tier": 5,
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
}

_STATIC_PROVIDER_MODELS: tuple[ProviderModelDefinition, ...] = (
    ProviderModelDefinition(
        "codex", "gpt-image-1.5", "GPT Image 1.5", "image", "Modelo oficial da OpenAI para imagem."
    ),
    ProviderModelDefinition(
        "codex",
        "sora-2",
        "Sora 2 (visual guiado por imagem)",
        "image",
        "Modelo Sora exposto para fluxos visuais guiados por texto ou imagem de referencia. "
        "A saida oficial do modelo e video.",
        status="preview",
    ),
    ProviderModelDefinition(
        "codex",
        "sora-2-pro",
        "Sora 2 Pro (visual guiado por imagem)",
        "image",
        "Variante premium do Sora para fluxos visuais guiados por imagem. A saida oficial do modelo e video.",
        status="preview",
    ),
    ProviderModelDefinition("codex", "sora-2", "Sora 2", "video", "Modelo de video da OpenAI."),
    ProviderModelDefinition("codex", "sora-2-pro", "Sora 2 Pro", "video", "Versao premium do Sora 2."),
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
        "whispercpp",
        "whisper-cpp-local",
        "Whisper CPP (local)",
        "transcription",
        "Transcricao local gratuita executada pela API do agent com whisper.cpp.",
    ),
    ProviderModelDefinition("sora", "sora-2", "Sora 2", "video", "Geracao de video da OpenAI."),
    ProviderModelDefinition("sora", "sora-2-pro", "Sora 2 Pro", "video", "Versao premium do Sora 2."),
)


def resolve_model_function_catalog() -> list[dict[str, Any]]:
    return [{"id": item.id, "title": item.title, "description": item.description} for item in _MODEL_FUNCTIONS]


def _general_model_title(provider_id: str, model_id: str) -> str:
    lookup = _DYNAMIC_GENERAL_MODEL_LABELS.get(provider_id, {})
    return lookup.get(model_id, model_id)


def resolve_known_general_model_ids(provider_id: str) -> list[str]:
    normalized_provider = provider_id.strip().lower()
    return list(_DYNAMIC_GENERAL_MODEL_LABELS.get(normalized_provider, {}).keys())


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
