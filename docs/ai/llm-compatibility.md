# LLM Compatibility

This repository guidance layer is designed to be readable by Codex, Claude Code, and other modern LLM tooling. The goal is to keep one canonical knowledge layer and expose it through lightweight provider-specific entrypoints only when needed.

## Canonical Provider-Neutral Artifacts

These files are the source of truth for repository understanding:

- [`../../README.md`](../../README.md): high-level repository entrypoint
- [`repo-map.yaml`](repo-map.yaml): deterministic machine-readable index for files, flows, guardrails, and tests
- The rest of [`../ai`](../ai): English reference docs for architecture, runtime flows, configuration, and change recipes
- Repo-local skill instructions in [`skills`](skills), especially each [`SKILL.md`](skills/repo-orientation/SKILL.md)

Any new repository guidance should live here first.

## Provider-Specific Entry Points

These files expose the same guidance to provider-specific tooling:

- [`../../AGENTS.md`](../../AGENTS.md) and matching subtree `AGENTS.md` files: entrypoints for Codex and other `AGENTS.md`-aware tooling
- [`../../CLAUDE.md`](../../CLAUDE.md) and matching subtree `CLAUDE.md` files: entrypoints for Claude Code

Keep both entrypoint families aligned. They should point back to the same provider-neutral docs instead of diverging.

## Skill Compatibility

- Each repo-local [`SKILL.md`](skills/repo-orientation/SKILL.md) is the canonical instruction file for a repository task pattern.
- [`skills/repo-orientation/agents/openai.yaml`](skills/repo-orientation/agents/openai.yaml) and sibling files add optional Codex metadata only.
- Do not put canonical guidance only in provider-specific metadata files.

## Compatibility Rules

- Keep all new repository-guidance documents in English.
- Put semantic structure in provider-neutral artifacts first.
- Keep `AGENTS.md` and `CLAUDE.md` mirrors aligned when local rules change.
- Keep [`repo-map.yaml`](repo-map.yaml) deterministic and provider-neutral.
- Keep control-plane agent documents and runtime `/skill` templates in [`../../koda/skills`](../../koda/skills) separate from repository guidance.

## Recommended Read Order For Any Model

1. Read [`../../README.md`](../../README.md).
2. Read [`repo-map.yaml`](repo-map.yaml).
3. Read the closest provider entrypoint: [`../../AGENTS.md`](../../AGENTS.md) or [`../../CLAUDE.md`](../../CLAUDE.md).
4. Read the relevant reference docs in [`../ai`](../ai).
5. Read the nearest repo-local [`SKILL.md`](skills/repo-orientation/SKILL.md) if the task matches a known workflow.
