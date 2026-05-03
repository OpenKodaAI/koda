"""Curated catalog of embedding models for Koda's memory + knowledge stack.

Operators pick from this list in the system settings UI ("Inteligência e
Memória"). Each entry carries enough metadata for the UI to surface a
trade-off comparison: download size, dimensionality, multilingual coverage,
quality / speed / hardware ratings, and a short description.

**No model is pre-installed.** A fresh Koda install ships with zero
embedding weights on disk — the goal is a lightweight install where the
operator opts into whichever model fits their hardware/quality budget.
Until a model is downloaded, the runtime falls back to a hash-based
bag-of-words vector (see :func:`koda.utils.embeddings.fallback_text_vector`),
which works but degrades retrieval quality. The UI surfaces a strong
warning when memory is enabled but no model is installed.

The runtime resolves the *active* embedding model in this order:

  1. Operator selection persisted in ``cp_global_sections.memory.embedding_model``
     (the UI writes here).
  2. ``MEMORY_EMBEDDING_MODEL`` env var (legacy override).
  3. ``DEFAULT_MODEL_ID`` below — the *recommended* starting point if the
     operator has no other signal. This is a hint, not an auto-install.

Model files live under the standard ``~/.cache/huggingface/hub`` path so
``sentence-transformers``'s loader picks them up without further config.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class EmbeddingModelDefinition:
    """One curated embedding model with the metadata the UI needs."""

    id: str
    """Stable identifier used in URLs and persistence (URL-safe slug)."""

    repo_id: str
    """Hugging Face Hub repo, e.g. ``sentence-transformers/...``."""

    title: str
    """Short display name."""

    description: str
    """One- or two-line description for the model card."""

    size_mb: int
    """Approximate on-disk size after download."""

    dimension: int
    """Output embedding dimensionality."""

    languages: tuple[str, ...]
    """Languages the model is documented to handle well."""

    quality: int
    """Subjective rating 1-5; higher is better on retrieval benchmarks."""

    speed: int
    """Subjective rating 1-5; higher is faster per-query."""

    hardware_hint: str
    """One-line guidance: ``cpu``, ``cpu/mps``, ``mps_recommended``, ``gpu_recommended``."""

    multilingual: bool
    """True if the model handles ≥10 languages well; false for English-only."""

    is_default_install: bool = False
    """Reserved. Currently ``False`` for every catalog entry — Koda no
    longer ships any embedding weights pre-installed. Kept on the dataclass
    to avoid breaking JSON consumers that still read the field."""


# Catalog
#
# The picks below are tuned for Koda's actual workload — multilingual
# (PT-BR + EN heavy), short queries / docs, real-time retrieval. Numbers
# come from the bench in tests/bench/bench_embedding_models.py and the
# published MTEB-multilingual leaderboard. We deliberately avoid >2GB models
# unless they carry a large quality jump, since download time and memory
# pressure on Macs are real costs.

DEFAULT_MODEL_ID = "paraphrase-multilingual-minilm"

_CATALOG: tuple[EmbeddingModelDefinition, ...] = (
    EmbeddingModelDefinition(
        id="paraphrase-multilingual-minilm",
        repo_id="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        title="Paraphrase Multilingual MiniLM",
        description=(
            "Modelo balanceado e leve. Boa escolha como ponto de partida "
            "para memória e cache em PT-BR + EN. nDCG@5 ≈ 0.91 no bench interno."
        ),
        size_mb=470,
        dimension=384,
        languages=("pt", "en", "es", "fr", "de", "it", "ja", "zh"),
        quality=3,
        speed=4,
        hardware_hint="cpu/mps",
        multilingual=True,
    ),
    EmbeddingModelDefinition(
        id="multilingual-e5-small",
        repo_id="intfloat/multilingual-e5-small",
        title="Multilingual E5 Small",
        description=(
            "Pequeno e instruct-tuned. +1.2 pp nDCG@5 vs default em queries "
            "técnicas. Use prefixo 'query: ' / 'passage: ' para melhor qualidade."
        ),
        size_mb=470,
        dimension=384,
        languages=("pt", "en", "es", "fr", "de", "ru", "zh", "ja", "ar"),
        quality=4,
        speed=3,
        hardware_hint="cpu/mps",
        multilingual=True,
    ),
    EmbeddingModelDefinition(
        id="gte-multilingual-base",
        repo_id="Alibaba-NLP/gte-multilingual-base",
        title="GTE Multilingual Base",
        description=(
            "Eficiente, 768 dim, top-tier no MTEB-multilingual (early 2026). "
            "Demanda trust_remote_code=True. Boa escolha para knowledge base grande."
        ),
        size_mb=600,
        dimension=768,
        languages=("pt", "en", "es", "fr", "de", "ru", "zh", "ja", "ar", "ko"),
        quality=4,
        speed=3,
        hardware_hint="cpu/mps",
        multilingual=True,
    ),
    EmbeddingModelDefinition(
        id="bge-m3",
        repo_id="BAAI/bge-m3",
        title="BGE-M3 (multilingual SOTA)",
        description=(
            "1024 dim, multilingual SOTA. Alto custo de download e memória; "
            "vale a pena para knowledge base com >100k documentos. Suporta "
            "dense + sparse + ColBERT (este integration usa só dense)."
        ),
        size_mb=2300,
        dimension=1024,
        languages=("pt", "en", "es", "fr", "de", "ru", "zh", "ja", "ar", "ko", "hi"),
        quality=5,
        speed=2,
        hardware_hint="mps_recommended",
        multilingual=True,
    ),
    EmbeddingModelDefinition(
        id="multilingual-e5-large-instruct",
        repo_id="intfloat/multilingual-e5-large-instruct",
        title="Multilingual E5 Large Instruct",
        description=(
            "Grande, instruct-tuned, líder em benchmarks de retrieval. "
            "Ideal para precisão máxima. Custo: ~2.2 GB e ~50 ms por embed em CPU."
        ),
        size_mb=2200,
        dimension=1024,
        languages=("pt", "en", "es", "fr", "de", "ru", "zh", "ja", "ar"),
        quality=5,
        speed=2,
        hardware_hint="mps_recommended",
        multilingual=True,
    ),
    EmbeddingModelDefinition(
        id="snowflake-arctic-embed-l-v2",
        repo_id="Snowflake/snowflake-arctic-embed-l-v2.0",
        title="Snowflake Arctic Embed L v2",
        description=(
            "Lançado em late 2025, líder em retrieval com bom equilíbrio "
            "tamanho/qualidade. Forte em EN; multilingual razoável."
        ),
        size_mb=1100,
        dimension=1024,
        languages=("en", "pt", "es", "fr", "de"),
        quality=4,
        speed=3,
        hardware_hint="mps_recommended",
        multilingual=True,
    ),
    EmbeddingModelDefinition(
        id="bge-small-en",
        repo_id="BAAI/bge-small-en-v1.5",
        title="BGE Small (English-only)",
        description=(
            "Apenas inglês mas extremamente rápido e leve (~130 MB). "
            "Use só se sua memória/conhecimento for puramente EN."
        ),
        size_mb=130,
        dimension=384,
        languages=("en",),
        quality=3,
        speed=5,
        hardware_hint="cpu",
        multilingual=False,
    ),
)


CATALOG: dict[str, EmbeddingModelDefinition] = {model.id: model for model in _CATALOG}


# Filesystem helpers — answer "is this model already on disk?"


def _hf_cache_dir() -> Path:
    return Path.home() / ".cache" / "huggingface" / "hub"


def _model_cache_dir(repo_id: str) -> Path:
    """Where ``snapshot_download(repo_id)`` writes its blobs."""
    safe = repo_id.replace("/", "--")
    return _hf_cache_dir() / f"models--{safe}"


def model_local_path(model_id: str) -> Path | None:
    definition = CATALOG.get(model_id)
    if definition is None:
        return None
    return _model_cache_dir(definition.repo_id)


def is_model_installed(model_id: str) -> bool:
    """A model is "installed" if its safetensors / pytorch weight is fully on disk.

    We check for at least one weights file inside any snapshot directory and
    no ``.incomplete`` blob remaining — that combination tells us a previous
    download finished cleanly.
    """
    definition = CATALOG.get(model_id)
    if definition is None:
        return False
    base = _model_cache_dir(definition.repo_id)
    snapshots = base / "snapshots"
    if not snapshots.is_dir():
        return False
    blobs = base / "blobs"
    if blobs.is_dir():
        for entry in blobs.iterdir():
            if entry.suffix == ".incomplete":
                return False
    for snapshot in snapshots.iterdir():
        if not snapshot.is_dir():
            continue
        for name in (
            "model.safetensors",
            "pytorch_model.bin",
            "model.onnx",
        ):
            candidate = snapshot / name
            if candidate.exists():
                return True
    return False


def model_disk_bytes(model_id: str) -> int:
    """Bytes currently consumed under the cache for this model (best-effort)."""
    definition = CATALOG.get(model_id)
    if definition is None:
        return 0
    base = _model_cache_dir(definition.repo_id)
    if not base.is_dir():
        return 0
    total = 0
    for path in base.rglob("*"):
        if path.is_file() and not path.is_symlink():
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total


# Public catalog payload — what the API endpoint returns


def model_payload(model_id: str) -> dict[str, Any]:
    """Serialize one catalog entry plus disk status for the UI."""
    definition = CATALOG[model_id]
    payload = asdict(definition)
    payload["installed"] = is_model_installed(model_id)
    payload["disk_bytes"] = model_disk_bytes(model_id)
    return payload


def catalog_payload(active_model_id: str | None = None) -> dict[str, Any]:
    items = [model_payload(model_id) for model_id in CATALOG]
    return {
        "items": items,
        "active": active_model_id or DEFAULT_MODEL_ID,
        "default": DEFAULT_MODEL_ID,
    }


# Deletion — wipe a downloaded model's HF cache directory


def delete_model(model_id: str) -> dict[str, Any]:
    """Remove every file under the cache directory for ``model_id``.

    The whole ``models--<repo>`` tree is dropped (snapshots + blobs + refs)
    so the next ``snapshot_download`` call starts clean. Returns a small
    receipt the API hands back to the UI.
    """
    definition = CATALOG.get(model_id)
    if definition is None:
        raise KeyError(f"unknown embedding model: {model_id}")

    base = _model_cache_dir(definition.repo_id)
    bytes_freed = model_disk_bytes(model_id)
    existed = base.is_dir()
    if existed:
        shutil.rmtree(base, ignore_errors=True)
    return {
        "model_id": definition.id,
        "repo_id": definition.repo_id,
        "removed": existed,
        "bytes_freed": int(bytes_freed),
        "local_path": str(base),
    }
