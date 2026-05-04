# Multi-stage build: Python + Node (for provider CLIs)
FROM node:22-slim AS node-base

# Install provider CLIs globally
RUN npm install -g \
    @anthropic-ai/claude-code \
    @openai/codex \
    @google/gemini-cli

FROM python:3.12-slim

ENV HEALTHCHECK_URL=http://127.0.0.1:8090/health
ENV DEBIAN_FRONTEND=noninteractive
ENV RUNNING_IN_DOCKER=true
ENV UV_VERSION=0.10.7

RUN python -m pip install --no-cache-dir --upgrade pip==26.0 uv==${UV_VERSION}

# Copy Node.js, npm helpers, and provider CLIs from node stage
COPY --from=node-base /usr/local/bin/node /usr/local/bin/node
COPY --from=node-base /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=node-base /usr/local/bin/claude /usr/local/bin/claude
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
    && ln -sf /usr/local/lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex \
    && ln -sf /usr/local/lib/node_modules/@google/gemini-cli/dist/index.js /usr/local/bin/gemini

# Install system dependencies and local runtime tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    unzip \
    ffmpeg \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

# X11/browser display packages — opt out with --build-arg INSTALL_BROWSER_DEPS=false
ARG INSTALL_BROWSER_DEPS=true
RUN if [ "$INSTALL_BROWSER_DEPS" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends \
        xvfb openbox x11vnc websockify && \
      rm -rf /var/lib/apt/lists/*; \
    fi

# Create non-root user
RUN useradd -m -s /bin/bash botuser

WORKDIR /app

# Install locked Python dependencies first (cache layer)
COPY pyproject.toml uv.lock ./
RUN uv export \
        --format requirements.txt \
        --locked \
        --no-editable \
        --no-emit-project \
        --no-emit-workspace \
        --no-header \
        --no-annotate \
        --output-file /tmp/runtime-requirements.txt \
    && pip install --no-cache-dir -r /tmp/runtime-requirements.txt \
    && rm -f /tmp/runtime-requirements.txt

# Copy application code
COPY koda/ koda/
COPY docs/openapi/ docs/openapi/
RUN pip install --no-cache-dir --no-deps .

# Pre-download optional embedding assets only when the dependency is present in the image.
RUN python - <<'PY'
import importlib.util

if importlib.util.find_spec("sentence_transformers") is None:
    print("Skipping sentence_transformers preload; dependency not installed in this image.")
else:
    from sentence_transformers import SentenceTransformer

    SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
PY

# Install Playwright browsers (before switching to non-root user)
RUN pip install --no-cache-dir playwright && playwright install --with-deps chromium

# Create required directories
RUN mkdir -p tmp_images data /var/lib/koda/state /var/lib/koda/runtime /var/lib/koda/runtime/home /var/lib/koda/artifacts \
    && chown -R botuser:botuser /app /var/lib/koda

USER botuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(os.environ.get('HEALTHCHECK_URL', 'http://127.0.0.1:8090/health'))" || exit 1

EXPOSE 8090

CMD ["python", "-m", "koda.control_plane"]
