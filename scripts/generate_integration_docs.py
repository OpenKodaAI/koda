#!/usr/bin/env python3
"""Generate per-integration markdown documentation.

For each integration in CORE_INTEGRATION_CATALOG and MCP_CATALOG, emits a
`.md` file under `docs/ai/integrations/{core|mcp}/`. Manual sections between
`<!-- MANUAL:BEGIN:<slug> -->` and `<!-- MANUAL:END:<slug> -->` markers are
preserved across regenerations.

Usage:
    python3 scripts/generate_integration_docs.py            # write files
    python3 scripts/generate_integration_docs.py --check    # exit 1 on drift
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT))

from koda.agent_contract import (  # noqa: E402
    CORE_INTEGRATION_CATALOG,
    ConnectionField,
    ConnectionProfile,
    CoreIntegrationDefinition,
)
from koda.integrations.mcp_catalog import MCP_CATALOG, McpServerSpec  # noqa: E402

DOCS_ROOT = REPO_ROOT / "docs" / "ai" / "integrations"

MANUAL_RE = re.compile(
    r"<!-- MANUAL:BEGIN:(?P<slug>[\w-]+) -->\n(?P<body>.*?)<!-- MANUAL:END:(?P=slug) -->",
    re.DOTALL,
)


def _manual_block(slug: str, default: str) -> str:
    body = default.rstrip() + "\n"
    return f"<!-- MANUAL:BEGIN:{slug} -->\n{body}<!-- MANUAL:END:{slug} -->"


def _preserve_manual(new_body: str, previous: str | None) -> str:
    if not previous:
        return new_body
    prev_blocks = {m.group("slug"): m.group("body") for m in MANUAL_RE.finditer(previous)}

    def repl(match: re.Match[str]) -> str:
        slug = match.group("slug")
        body = prev_blocks.get(slug, match.group("body"))
        return f"<!-- MANUAL:BEGIN:{slug} -->\n{body}<!-- MANUAL:END:{slug} -->"

    return MANUAL_RE.sub(repl, new_body)


def _render_fields(fields: tuple[ConnectionField, ...], title: str) -> str:
    if not fields:
        return ""
    rows = [f"### {title}", "", "| Campo | Obrigatório | Tipo | Descrição |", "|---|---|---|---|"]
    for f in fields:
        required = "sim" if f.required else "não"
        rows.append(f"| `{f.key}` | {required} | {f.input_type} | {f.label}{' — ' + f.help if f.help else ''} |")
    rows.append("")
    return "\n".join(rows)


def _render_profile(profile: ConnectionProfile | None) -> str:
    if profile is None:
        return "Esta integração não expõe modal de conexão (sempre ativa para o agente quando habilitada)."
    lines = [f"**Strategy**: `{profile.strategy}`"]
    if profile.oauth_provider:
        scopes = " ".join(profile.oauth_scopes) or "(sem scopes padrão)"
        lines.append(f"- OAuth provider: `{profile.oauth_provider}` · scopes: `{scopes}`")
    if profile.local_app_name:
        lines.append(f"- App local: **{profile.local_app_name}**")
        if profile.local_app_detection_hint:
            lines.append(f"  - {profile.local_app_detection_hint}")
    if profile.path_argument:
        pf = profile.path_argument
        lines.append(f"- Argumento de caminho: `{pf.key}` — {pf.label}")
    sections = [
        "\n".join(lines),
        _render_fields(profile.fields, "Campos principais"),
        _render_fields(profile.scope_fields, "Campos de escopo (opcionais)"),
    ]
    if profile.read_only_toggle:
        sections.append(
            "\n".join(
                [
                    "### Toggle de read-only",
                    "",
                    f"`{profile.read_only_toggle.key}` — {profile.read_only_toggle.label}",
                    "",
                ]
            )
        )
    return "\n\n".join(s for s in sections if s)


def _render_constraints(constraints: tuple[str, ...]) -> str:
    if not constraints:
        return "Nenhuma restrição de runtime aplicável a esta integração."
    return "\n".join(f"- `{c}`" for c in constraints)


def _render_core(spec: CoreIntegrationDefinition) -> str:
    body = f"""# {spec.title}

- **Integration key**: `{spec.id}`
- **Kind**: core
- **Transport**: {spec.transport}
- **Risk class**: {spec.risk_class}
- **Auth modes**: {", ".join(f"`{m}`" for m in spec.auth_modes)}
- **Required env**: {", ".join(f"`{e}`" for e in spec.required_env) or "—"}
- **Required secrets**: {", ".join(f"`{s}`" for s in spec.required_secrets) or "—"}

## Descrição

{spec.description}

## Connection profile

{_render_profile(spec.connection_profile)}

## Runtime constraints

{_render_constraints(spec.runtime_constraints)}

## Como o agente usa bem

{_manual_block(f"core-{spec.id}-patterns", "- (preencher com padrões recomendados)")}

## Gotchas

{_manual_block(f"core-{spec.id}-gotchas", "- (preencher com cuidados específicos)")}
"""
    return body.strip() + "\n"


def _render_mcp(spec: McpServerSpec) -> str:
    tools_rows = [
        "| Tool | Classificação | Descrição |",
        "|---|---|---|",
    ]
    for t in spec.tools:
        tools_rows.append(f"| `{t.name}` | {t.classification} | {t.description} |")
    tools_md = "\n".join(tools_rows) if spec.tools else "_Nenhuma tool catalogada._"

    command_rendered = " ".join(spec.command_template)
    remote = f"\n- **Remote URL**: {spec.remote_url}" if spec.remote_url else ""

    body = f"""# {spec.display_name}

- **Integration key**: `{spec.server_key}`
- **Kind**: mcp
- **Tier**: {spec.tier}
- **Category**: {spec.category}
- **Canonical source**: {spec.documentation_url}
- **Transport**: {spec.transport_type}
- **Install command**: `{command_rendered}`{remote}

## Descrição

{spec.description}

## Connection profile

{_render_profile(spec.connection_profile)}

## Runtime constraints

{_render_constraints(spec.runtime_constraints)}

## Tools expostas

{tools_md}

## Como o agente usa bem

{_manual_block(f"mcp-{spec.server_key}-patterns", "- (preencher com padrões recomendados)")}

## Gotchas

{_manual_block(f"mcp-{spec.server_key}-gotchas", "- (preencher com cuidados específicos)")}
"""
    return body.strip() + "\n"


def _write_doc(path: Path, content: str, check_only: bool, drift: list[Path]) -> None:
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    final = _preserve_manual(content, previous)
    if previous == final:
        return
    if check_only:
        drift.append(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(final, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit 1 if docs are stale")
    args = parser.parse_args()

    drift: list[Path] = []

    for integration_id, core_spec in sorted(CORE_INTEGRATION_CATALOG.items()):
        path = DOCS_ROOT / "core" / f"{integration_id}.md"
        _write_doc(path, _render_core(core_spec), args.check, drift)

    for mcp_spec in MCP_CATALOG:
        path = DOCS_ROOT / "mcp" / f"{mcp_spec.server_key}.md"
        _write_doc(path, _render_mcp(mcp_spec), args.check, drift)

    if args.check and drift:
        print("Stale integration docs (re-run scripts/generate_integration_docs.py):", file=sys.stderr)
        for p in drift:
            print(f"  - {p.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 1
    if not args.check:
        total = len(CORE_INTEGRATION_CATALOG) + len(MCP_CATALOG)
        print(
            f"Generated docs for {total} integrations ({len(CORE_INTEGRATION_CATALOG)} core + {len(MCP_CATALOG)} mcp)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
