"""Real-data measurement of how GBNF reduces tool-call parse failures.

Runs N prompts asking Qwen2.5-1.5B-Instruct (Q4_K_M, Metal) to emit an
``<agent_cmd>`` tool call. Each prompt is sent twice — once without
``grammar`` in the chat-completions payload, once with the bundled
``agent_cmd.gbnf``. We then run each response through the production
``tool_dispatcher.parse_agent_commands`` and count how many produced at
least one valid tool call.

Output: real success-rate numbers, not estimates. Run with:

    LLAMA_PORT=8089 python tests/bench/bench_gbnf_effectiveness.py

Requires a running ``llama-server`` on the given port serving any chat
model with the OpenAI-compatible API. Designed for ad-hoc validation; not
part of the regular pytest suite.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from koda.services.tool_dispatcher import parse_agent_commands  # noqa: E402

# Prompts mix simple/clear, ambiguous, and tricky variants so the small
# model has chances to break formatting in different ways. Each prompt
# implicitly demands an ``<agent_cmd>`` block as the response.
PROMPTS: list[tuple[str, dict[str, object]]] = [
    ("Read the file foo.py.", {"tool": "file_read", "path": "foo.py"}),
    ("Show me what's in src/index.ts.", {"tool": "file_read", "path": "src/index.ts"}),
    ("Run 'ls -la' on the project root.", {"tool": "shell_run", "command": "ls -la"}),
    ("Execute: git status", {"tool": "shell_run", "command": "git status"}),
    ("Query: SELECT name FROM users LIMIT 5", {"tool": "db_query", "query": "SELECT name FROM users LIMIT 5"}),
    ("List the files in the current directory.", {"tool": "shell_run", "command": "ls"}),
    ("Open the README.md and tell me the title.", {"tool": "file_read", "path": "README.md"}),
    ("Grep for 'TODO' in the codebase.", {"tool": "shell_run", "command": "grep -r TODO ."}),
    ("Find all Python files modified today.", {"tool": "shell_run", "command": "find . -name '*.py' -mtime -1"}),
    ("Click the submit button on the page.", {"tool": "browser_click", "selector": "#submit"}),
    ("Send a message to user buddy: hello.", {"tool": "agent_send", "to": "buddy", "message": "hello"}),
    (
        "Create a job named nightly that runs at 2am.",
        {"tool": "job_create", "name": "nightly", "schedule": "0 2 * * *"},
    ),
    ("Get the git log for the last 5 commits.", {"tool": "shell_run", "command": "git log -n 5"}),
    ("Read the file at /etc/hosts.", {"tool": "file_read", "path": "/etc/hosts"}),
    ("Check disk usage.", {"tool": "shell_run", "command": "df -h"}),
    ("Type 'hello' into the search input.", {"tool": "browser_type", "selector": "input[name=q]", "text": "hello"}),
    ("List MCP tools from the stripe server.", {"tool": "mcp_list_tools", "server": "stripe"}),
    ("Run a search for 'koda' in this repo.", {"tool": "shell_run", "command": "grep -r koda ."}),
    ("Show the contents of pyproject.toml.", {"tool": "file_read", "path": "pyproject.toml"}),
    ("Find Python files modified yesterday.", {"tool": "shell_run", "command": "find . -name '*.py' -mtime 1"}),
]


SYSTEM_PROMPT = (
    "You are a tool-using assistant. When the user asks for an action, respond "
    'with EXACTLY ONE <agent_cmd tool="<name>">{json}</agent_cmd> block and nothing else. '
    "Use lowercase tool names. The body must be a single-line JSON object. "
    "Do NOT wrap the block in markdown code fences."
)


def call(*, port: int, prompt: str, grammar: str | None) -> str:
    payload: dict[str, object] = {
        "model": "qwen",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 200,
        "stream": False,
        "temperature": 0.7,  # Some randomness so repeats can fail differently
    }
    if grammar is not None:
        payload["grammar"] = grammar
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return f"<HTTP_ERROR {exc.code} {exc.read().decode()[:200]}>"
    return body["choices"][0]["message"]["content"]


def evaluate(response: str) -> bool:
    """A response 'parses successfully' iff parse_agent_commands extracts >=1 valid call."""
    calls, _ = parse_agent_commands(response)
    return len(calls) >= 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=int(__import__("os").environ.get("LLAMA_PORT", 8089)))
    p.add_argument("--repeats", type=int, default=5, help="Repeats per prompt to absorb noise")
    p.add_argument("--grammar-path", default=str(ROOT / "koda" / "services" / "grammars" / "agent_cmd.gbnf"))
    args = p.parse_args()

    grammar_text = Path(args.grammar_path).read_text(encoding="utf-8")

    n_per_arm = len(PROMPTS) * args.repeats
    print(f"Running {n_per_arm} calls per arm (no grammar / with grammar)...")
    print(f"Model: whatever llama-server on :{args.port} is serving")
    print(f"Repeats per prompt: {args.repeats}")
    print()

    no_grammar_results: list[tuple[str, str, bool]] = []
    with_grammar_results: list[tuple[str, str, bool]] = []

    started = time.time()
    for arm_label, grammar in (("no_grammar", None), ("with_grammar", grammar_text)):
        for _trial in range(args.repeats):
            for prompt, _expected in PROMPTS:
                response = call(port=args.port, prompt=prompt, grammar=grammar)
                ok = evaluate(response)
                row = (prompt, response, ok)
                if arm_label == "no_grammar":
                    no_grammar_results.append(row)
                else:
                    with_grammar_results.append(row)
                # Live progress dot
                sys.stdout.write("." if ok else "x")
                sys.stdout.flush()
        sys.stdout.write(f"  [{arm_label}]\n")

    elapsed = time.time() - started

    no_ok = sum(1 for _, _, ok in no_grammar_results if ok)
    no_total = len(no_grammar_results)
    with_ok = sum(1 for _, _, ok in with_grammar_results if ok)
    with_total = len(with_grammar_results)

    no_rate = no_ok / no_total if no_total else 0.0
    with_rate = with_ok / with_total if with_total else 0.0
    failure_drop = (1 - no_rate) - (1 - with_rate)
    relative_improvement = ((with_rate - no_rate) / max(0.001, 1 - no_rate)) * 100 if no_rate < 1.0 else 0.0

    print()
    print(f"=== GBNF effectiveness on {no_total + with_total} total calls in {elapsed:.0f}s ===")
    print(
        f"No grammar:   {no_ok:>3d}/{no_total} parsed = {no_rate * 100:5.1f}% success "
        f"({(1 - no_rate) * 100:.1f}% failure)"
    )
    print(
        f"With grammar: {with_ok:>3d}/{with_total} parsed = {with_rate * 100:5.1f}% success "
        f"({(1 - with_rate) * 100:.1f}% failure)"
    )
    print(f"Absolute failure-rate drop: {failure_drop * 100:+.1f} percentage points")
    print(f"Relative improvement on failures: {relative_improvement:+.1f}%")

    # Show a few sample failure responses from each arm so the operator can
    # see what kind of mistake the small model makes.
    no_fails = [(p, r) for p, r, ok in no_grammar_results if not ok][:3]
    with_fails = [(p, r) for p, r, ok in with_grammar_results if not ok][:3]
    print()
    print("Sample no-grammar failures:")
    for p, r in no_fails:
        print(f"  PROMPT: {p}")
        print(f"  RESPONSE: {r[:300]!r}")
        print()
    print("Sample with-grammar failures:")
    for p, r in with_fails:
        print(f"  PROMPT: {p}")
        print(f"  RESPONSE: {r[:300]!r}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
