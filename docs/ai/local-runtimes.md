# Local Apple Silicon / Metal Runtimes

Koda ships first-class support for Metal-accelerated local inference on Apple Silicon Macs through two providers:

- **`llamacpp`** — `llama-server` from llama.cpp, GGUF model format, GBNF grammar for tool-call reliability.
- **`mlx`** — `mlx-openai-server` (Apple's MLX framework), MLX 4-bit/8-bit format, native Metal kernels with unified memory.

Both providers reuse the shared OpenAI-compatible HTTP runner (`koda/services/openai_compatible_runner.py`) via the `auth_mode="local"` path; no new request plumbing was added. They coexist with Ollama — operators who want one-click installation continue to use `ollama`, while operators who want raw control over GGUF/MLX models, sampler params, draft models, or grammar-constrained decoding pick `llamacpp` / `mlx`.

## When to use which

| Situation | Recommended | Why |
|---|---|---|
| Tool-calling reliability matters with a small (≤7B) local model | `llamacpp` with `STRUCTURED_DECODING_ENABLED=true` | GBNF grammar bounds output to syntactically valid `<agent_cmd>` blocks. |
| Single-model throughput on M-series | `mlx` | Native Metal kernels; unified memory removes the PCIe bottleneck. |
| First-time / casual setup | `ollama` | Single binary install, model registry, CLI download. |
| Need GGUF model variant from Hugging Face | `llamacpp` | Largest open ecosystem of pre-quantized models. |
| Vision/multimodal | none yet | Planned; today, route image queries to a cloud vision provider. |

## Setup

### llama.cpp

```bash
brew install llama.cpp
# Pick a GGUF model from huggingface.co/models?library=gguf
llama-server -m ~/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  -ngl 99 --host 127.0.0.1 --port 8080
```

Set in `.env`:

```ini
LLAMACPP_ENABLED=true
LLAMACPP_API_BASE_URL=http://127.0.0.1:8080
LLAMACPP_DEFAULT_MODEL=qwen2.5-7b-instruct-q4_k_m
```

### MLX

```bash
pip install mlx-lm
python -m mlx_lm.server \
  --model mlx-community/Qwen2.5-7B-Instruct-4bit \
  --host 127.0.0.1 --port 8000
```

Set in `.env`:

```ini
MLX_ENABLED=true
MLX_API_BASE_URL=http://127.0.0.1:8000
MLX_DEFAULT_MODEL=mlx-community/Qwen2.5-7B-Instruct-4bit
```

## Auto-activation: what lights up when you enable a local provider

The default value of ``LOCAL_AUTO_OPTIMIZE`` is ``true``. Once you set
``LLAMACPP_ENABLED=true`` (or ``MLX_ENABLED=true``, or ``OLLAMA_ENABLED=true``),
Koda inspects the environment at startup and **turns on the practices that
make sense for that machine**. Concretely:

| Practice | Auto-activates when... |
|---|---|
| GBNF grammar (llamacpp only) | always — bundled with the package |
| Reranker (BGE) | ``sentence-transformers`` is importable |
| FAISS vector cache | ``faiss-cpu`` is importable |
| Cascade routing (threshold 0.4) | a local provider is enabled |
| Auto-spawn supervisor (llamacpp) | ``llama-server`` is on the PATH |
| Auto-spawn supervisor (mlx) | ``mlx_lm.server`` binary or ``mlx_lm`` module is available |

**Explicit env vars always override.** Setting ``RERANK_ENABLED=false``,
``SEMANTIC_CACHE_BACKEND=lexical``, ``LOCAL_PREFER_BELOW_COMPLEXITY=0``, or
``LOCAL_RUNTIME_AUTO_SPAWN=false`` keeps that one feature off regardless of
auto-activation.

To opt out of automatic behavior entirely (every bolt-on off until you
flip it yourself), set ``LOCAL_AUTO_OPTIMIZE=false``.

The single source of truth for this resolution is
[`koda/services/runtime_capabilities.py`](../../koda/services/runtime_capabilities.py).
A snapshot of the resolved state is logged at startup and surfaced via
``runtime_capabilities_snapshot()`` so operators can verify what was
chosen for their environment.

## Optional: auto-spawn supervisor

Set `LOCAL_RUNTIME_AUTO_SPAWN=true` to let Koda spawn and supervise the binaries itself. The supervisor (`koda/services/local_runtime_supervisor.py`) will:

- Spawn `llama-server` or `mlx_lm.server` on the first request.
- Hold a `LOCAL_RUNTIME_HEAVY_SLOTS=1` lock so two ≥30B models can't load simultaneously and OOM unified memory.
- Issue a 1-token warmup call after spawn so the first user-facing turn doesn't pay the model-load latency.
- Tear down spawned processes cleanly via `atexit` and SIGTERM through the process group.

Auto-spawn is opt-in by design — production deployments may run the binaries elsewhere (different host, container) and want Koda to connect rather than manage.

## Quality bolt-ons that pair well

- **Constrained decoding (`STRUCTURED_DECODING_ENABLED=true`)** — only `llamacpp` consumes the bundled GBNF grammar today. MLX server-side support is pending upstream.
- **Reranker (`RERANK_ENABLED=true`)** — `BAAI/bge-reranker-v2-m3` runs on MPS at ~5 ms/query and meaningfully improves memory recall ordering, particularly on multi-hop queries.
- **Semantic cache (`SEMANTIC_CACHE_BACKEND=vector`)** — FAISS-CPU index over cached query embeddings catches paraphrase hits the existing chunked match misses.
- **Cascade routing (`LOCAL_PREFER_BELOW_COMPLEXITY=0.4`)** — trivial Q&A lands locally; complex tasks transparently escalate via the existing fallback chain.

## Apple Silicon detection

`koda/services/apple_silicon.py` exposes a cached profile (`detect_apple_silicon_profile()`) with chip name, unified memory, GPU cores, recommended quantization (`q4_k_m`, `q5_k_m`, or `mlx-4bit`), and a recommended max parameter count. The web control plane uses it to render install hints and capacity guidance in the connection modal.

## Capacity guidance

| Unified memory | Recommended max model | Quantization |
|---|---|---|
| 16 GB | 8B | MLX 4-bit / Q4_K_M |
| 24 GB | 13B | Q4_K_M |
| 36 GB | 30B | Q4_K_M |
| 64 GB | 70B | Q4_K_M |
| ≥96 GB | 70B with headroom | Q5_K_M |

Headroom assumes ~10 GB for KV cache, macOS, and the rest of Koda's process tree. Multi-agent setups should add 1 GB per concurrent agent.

## Files

- `koda/services/llamacpp_runner.py` — provider runner (50 LOC wrapper around the shared OpenAI-compatible runner).
- `koda/services/mlx_runner.py` — same shape for MLX.
- `koda/services/structured_decoding.py` — GBNF/XGrammar helpers for tool-call constraint.
- `koda/services/grammars/agent_cmd.gbnf` — bundled grammar; matches the `<agent_cmd>` regex parsed by `koda/services/tool_dispatcher.py`.
- `koda/services/apple_silicon.py` — chip detection + recommendation table.
- `koda/services/local_runtime_supervisor.py` — opt-in process supervision (auto-spawn + slot lock + warmup).
- `koda/services/local_routing_policy.py` — cascade routing that prefers local for low-complexity queries.
- `koda/services/reranker.py` — `BAAI/bge-reranker-v2-m3` integration for memory recall.
- `koda/services/semantic_cache_index.py` — FAISS upgrade for the existing semantic cache.
