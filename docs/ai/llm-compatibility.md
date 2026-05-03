# LLM Compatibility

This repository guidance layer is designed to be readable by Codex, Claude Code, and other modern LLM tooling. The goal is to keep one canonical knowledge layer and expose it through lightweight provider-specific entrypoints only when needed.

## Canonical Provider-Neutral Artifacts

These files are the source of truth for repository understanding:

- [`../../README.md`](../../README.md): high-level repository entrypoint
- [`repo-map.yaml`](repo-map.yaml): deterministic machine-readable index for files, flows, guardrails, and tests
- The rest of [`../ai`](../ai): English reference docs for architecture, runtime flows, configuration, and change recipes
- Repo-local skill instructions in [`skills`](skills), especially each [`SKILL.md`](skills/repo-orientation/SKILL.md)

Any new repository guidance should live here first.

## Repository Entry Point

- [`../../CLAUDE.md`](../../CLAUDE.md) and matching subtree `CLAUDE.md` files are the canonical entrypoints for any agent working in this repository. Modern coding agents (Claude Code, Codex, Cursor, Copilot, etc.) all read `CLAUDE.md`.

## Skill Compatibility

- Each repo-local [`SKILL.md`](skills/repo-orientation/SKILL.md) is the canonical instruction file for a repository task pattern.
- [`skills/repo-orientation/agents/openai.yaml`](skills/repo-orientation/agents/openai.yaml) and sibling files add optional Codex metadata only.
- Do not put canonical guidance only in provider-specific metadata files.

## Compatibility Rules

- Keep all new repository-guidance documents in English.
- Put semantic structure in provider-neutral artifacts first.
- Keep [`repo-map.yaml`](repo-map.yaml) deterministic and provider-neutral.
- Keep control-plane agent documents and runtime `/skill` templates in [`../../koda/skills`](../../koda/skills) separate from repository guidance.

## Recommended Read Order For Any Model

1. Read [`../../README.md`](../../README.md).
2. Read [`repo-map.yaml`](repo-map.yaml).
3. Read [`../../CLAUDE.md`](../../CLAUDE.md) and the closest subtree `CLAUDE.md`.
4. Read the relevant reference docs in [`../ai`](../ai).
5. Read the nearest repo-local [`SKILL.md`](skills/repo-orientation/SKILL.md) if the task matches a known workflow.
