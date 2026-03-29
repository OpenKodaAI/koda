"""Prompt templates for memory extraction and recall."""

from __future__ import annotations

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


def _load_extraction_prompt() -> str:
    inline_prompt = os.environ.get("MEMORY_EXTRACTION_PROMPT_TEXT", "").strip()
    return inline_prompt or _DEFAULT_EXTRACTION_PROMPT


EXTRACTION_PROMPT = _load_extraction_prompt()

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
