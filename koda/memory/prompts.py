"""Prompt templates for memory extraction and recall."""

from __future__ import annotations

import json
import os

_DEFAULT_EXTRACTION_PROMPT = """\
Extract important information from this conversation for future recall.

<conversation>
<user_query>{query}</user_query>
<assistant_response>{response}</assistant_response>
</conversation>

<memory_types>
fact | event | preference | decision | problem | commit | relationship | task | procedure
</memory_types>

<importance>
0.9-1.0: Architectural decisions, breaking changes, critical configs
0.7-0.8: Resolved bugs with solutions, explicit preferences, project patterns
0.5-0.6: Technical facts, task context, reference info
0.3-0.4: Minor contextual observations
</importance>

<rules>
- Extract only what would clearly help in a future conversation.
  Prefer fewer, high-quality memories over many weak ones.
- Include technical details: file paths, commands, error messages, versions.
- Each content field must be self-contained.
- Skip greetings, generic questions, source code dumps.
- Prefer memories that would change future behavior for this agent.
- Provide a structured record for each memory:
  - `type`: one of the allowed memory types
  - `content`: concise self-contained summary
  - `importance`: 0.0-1.0
  - `confidence`: 0.0-1.0
  - `claim_kind`: short label like fact, decision, preference, failure, procedure
  - `subject`: the main entity/topic this memory is about
  - `decision_source`: where this came from, such as user_statement, assistant_validation, runtime_observation
  - `evidence_refs`: optional short list of file paths, commands, issue ids, URLs, or errors that support this memory
  - `retention_reason`: why remembering this matters later
  - `conflict_key`: optional stable key when this could supersede an older memory about the same subject
  - `valid_until`: optional ISO date/datetime if the memory clearly expires
- If nothing is important, return [].
- Maximum {max_items} items.
</rules>

Return ONLY a JSON array:
[
  {{
    "type": "<type>",
    "content": "<concise summary>",
    "importance": <0.0-1.0>,
    "confidence": <0.0-1.0>,
    "claim_kind": "<kind>",
    "subject": "<subject>",
    "decision_source": "<source>",
    "evidence_refs": ["<evidence>"],
    "retention_reason": "<why this matters>",
    "conflict_key": "<optional conflict key>",
    "valid_until": "<optional ISO date>"
  }}
]"""


def _schema_extraction_prompt_from_agent_spec() -> str:
    raw_spec = os.environ.get("AGENT_SPEC_JSON", "").strip()
    if not raw_spec:
        return ""
    try:
        payload = json.loads(raw_spec)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""

    memory_schema = payload.get("memory_extraction_schema")
    if isinstance(memory_schema, dict):
        inline_prompt = str(memory_schema.get("template") or memory_schema.get("content_md") or "").strip()
        if inline_prompt:
            return inline_prompt

    documents = payload.get("documents")
    if isinstance(documents, dict):
        inline_prompt = str(documents.get("memory_extraction_prompt_md") or "").strip()
        if inline_prompt:
            return inline_prompt

    return ""


def get_extraction_prompt() -> str:
    """Return the active memory extraction prompt, preferring runtime agent config."""
    inline_prompt = os.environ.get("MEMORY_EXTRACTION_PROMPT_TEXT", "").strip()
    if inline_prompt:
        return inline_prompt
    schema_prompt = _schema_extraction_prompt_from_agent_spec()
    if schema_prompt:
        return schema_prompt
    return _DEFAULT_EXTRACTION_PROMPT


EXTRACTION_PROMPT = get_extraction_prompt()

RECALL_HEADER = "## Memória de Longo Prazo\nInformações relevantes de conversas anteriores:\n"

RECALL_TYPE_HEADERS: dict[str, str] = {
    "event": "### Eventos Recentes",
    "fact": "### Fatos Relevantes",
    "task": "### Tarefas Ativas",
    "decision": "### Decisões",
    "procedure": "### Procedimentos Reutilizáveis",
    "preference": "### Preferências",
    "problem": "### Problemas Conhecidos",
    "commit": "### Commits Recentes",
    "relationship": "### Relações",
}

PROACTIVE_HEADER = "## Lembretes Proativos\nInformações recentes que podem ser relevantes agora:\n"
