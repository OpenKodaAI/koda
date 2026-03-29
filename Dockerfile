# Multi-stage build: Python + Node (for Claude CLI)
FROM node:22-slim AS node-base

# Install Claude CLI globally
RUN npm install -g @anthropic-ai/claude-code

FROM python:3.12-slim

ENV HEALTHCHECK_URL=http://127.0.0.1:8090/health
ENV DEBIAN_FRONTEND=noninteractive

# Copy Node.js and Claude CLI from node stage
COPY --from=node-base /usr/local/bin/node /usr/local/bin/node
COPY --from=node-base /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=node-base /usr/local/bin/claude /usr/local/bin/claude
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm

# Install Google Workspace CLI
RUN npm install -g @googleworkspace/cli

# Install system dependencies and CLI tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    unzip \
    ffmpeg \
    espeak-ng \
    xvfb \
    openbox \
    x11vnc \
    websockify \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Install GitLab CLI when a matching Debian package exists for the target architecture.
RUN arch="$(dpkg --print-architecture)" \
    && glab_url="https://gitlab.com/gitlab-org/cli/-/releases/permalink/latest/downloads/glab_${arch}.deb" \
    && if curl -fsSL "${glab_url}" -o /tmp/glab.deb; then \
        dpkg -i /tmp/glab.deb; \
        rm /tmp/glab.deb; \
    else \
        echo "Skipping GitLab CLI install for unsupported architecture: ${arch}"; \
    fi

# Install AWS CLI v2
RUN arch="$(dpkg --print-architecture)" \
    && case "${arch}" in \
        amd64) aws_arch="x86_64" ;; \
        arm64) aws_arch="aarch64" ;; \
        *) echo "Unsupported architecture for AWS CLI: ${arch}" >&2; exit 1 ;; \
    esac \
    && curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${aws_arch}.zip" -o /tmp/awscliv2.zip \
    && unzip -q /tmp/awscliv2.zip -d /tmp/aws \
    && /tmp/aws/aws/install && rm -rf /tmp/awscliv2.zip /tmp/aws

# Create non-root user
RUN useradd -m -s /bin/bash botuser

WORKDIR /app

# Install Python dependencies first (cache layer)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY pyproject.toml ./
COPY koda/ koda/
COPY docs/openapi/ docs/openapi/
COPY agent.py ./
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
RUN mkdir -p tmp_images data /var/lib/koda/state /var/lib/koda/runtime /var/lib/koda/artifacts \
    && chown -R botuser:botuser /app /var/lib/koda

USER botuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(os.environ.get('HEALTHCHECK_URL', 'http://127.0.0.1:8090/health'))" || exit 1

EXPOSE 8090

CMD ["python", "-m", "koda.control_plane"]
