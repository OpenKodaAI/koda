# Skill Supply-Chain Scanner

The Phase 4 scanner is a static gate for local skill/plugin packages. It does
not import, execute, or evaluate package code.

## Contract

Scanner output uses `skill_scan.v1`:

- `decision`: `allow`, `review_required`, or `deny`
- `severity`: highest finding severity
- `findings`: id, severity, category, message, path, user action
- `permissions_requested`
- `risk_classes`
- `redactions`
- `package_hash`
- `file_hashes`
- `scanner_version`

## Deny Rules

The scanner denies:

- path traversal or symlink escape
- files over the package size budget
- missing handlers for declared tools
- invalid JSON Schema or manifest shape
- secret-looking files or literal credentials
- install scripts or lifecycle hooks
- dangerous imports or calls such as `subprocess`, `eval`, `exec`, and
  `os.system`
- unknown permissions
- `secret_access`, `code_execution`, `destructive_write`, or `unknown` risk
  without an explicit review path
- tool id conflicts with core or already installed package tools

## Review Required

Network writes, private network access, low-confidence metadata, or broad write
permissions return `review_required`. Review does not bypass ExecutionPolicy or
approval. It only allows package install to proceed when local operator policy
accepts the risk.

So does a Python file that uses a way to run code that the verified-bytes
guarantee (see Load-Time Integrity) does not cover, reported as
`python.exec_from_file` with the name it uses (D-311).

A `review_required` package installs only after an operator accepts the review
in the agent's Skills tab, which calls the operator-authenticated control-plane
route `POST /api/control-plane/agents/{agent_id}/skills/packages/install` with
`review_accepted=true`, a non-empty `review_note` and the `package_hash` the
review screen showed next to the scanner version and verdict. The install scans
the package again and refuses it with `skill.review_hash_mismatch` when the
files no longer match that hash. The lock records the review in
`operator_review`: the note, the time, the reviewer, the `package_hash`, the
`scanner_version` and the scan decision. The review does not weaken scanner
findings, ExecutionPolicy, or per-agent skill/package allowlists.

The model cannot accept a review. The `plugin_install` tool takes only `path`,
ignores any review fields in its call, and a `review_required` package fails
with `skill.policy_denied` until an operator approves it (D-031).

Imported or legacy locks with `decision=review_required` but no preserved
`operator_review.accepted` evidence stay `blocked` and cannot become
`recommended`.

## Load-Time Integrity

The package hash covers every file in the package except the bytecode cache
files Python writes into a `__pycache__` directory (`<module>.<cache tag>.pyc`,
optionally with `.opt-N`). Any other file there, a `.py` source or a `.pyc`
with another name included, is hashed like the rest. A lock approved by an
earlier release, whose hash also covered the cache files, still matches while
every file, caches included, is the one that was approved.

Before the runtime loads a package's handler code (at startup, on install, on
`plugin_reload`), it hashes the files on disk again and compares the result
with the approved `package_hash` in the lock. When they differ, the package is
not loaded: its tools stay unregistered, the runtime logs
`skill_package_modified_not_loaded` and emits a `skill_package.modified` audit
event once per changed hash, `plugin_reload` answers that the package changed
after approval, and the registry item's `integrity.status` is `modified`
(otherwise `verified`), which the Skills tab shows on the package's card. An
operator reinstalls and reviews the package to load it again.

The check reads each package file once, and the code that runs is the bytes it
hashed, never a later read of the files, so a file rewritten after the check
does not run (D-292). The handlers compile from those bytes, and from the time
a package registers until it is unregistered or uninstalled, so does every module file
inside its directory, however package code loads it, while the handlers
register or later, at tool-call time: an `import` statement,
`importlib.util.spec_from_file_location` or a `SourceFileLoader` of its own all
end in `SourceFileLoader.get_code`, which for those files reads neither a
`__pycache__` entry (D-273) nor the file on disk. The bytes are looked up by
the path the module is loaded from, under the package directory, not by where
a symlink there points: a file or a directory in the package swapped for a
symlink after the check, to a file outside the package or to another package
file, still runs the bytes hashed at that path. Only when no bytes were hashed
at that path is a module looked up by its real path in the same package too:
a directory symlink inside the package that points inside it (`alias -> real`)
is allowed, the hash covers its files once, at `real/`, and a module or a
declared handler reached through `alias/` runs the bytes hashed at its real
path (D-309); a symlink out of the package is denied at scan. A module file
that was not hashed at its path or at its real path, for example one added
after the check, is refused with an `ImportError`. A compiled module inside a package's directory (a `.pyc` without
its source, an extension module) and a module in an archive there (a `.zip`
that package code puts on `sys.path` or opens with `zipimport`) are refused
too, because Python would read them from disk when they load: package code
loads from its verified `.py` sources only.

### Load routes the verified bytes cover, and the ones left to the scanner

The guarantee holds for code that reaches `SourceFileLoader.get_code` or one of
the refused loaders above (D-311). Covered, for a file inside the package
directory:

- the declared handlers, which the plugin registry compiles from the verified
  bytes itself;
- `import` and `from ... import` statements, `importlib.import_module` and
  `__import__`, through the path finders, including a directory package code
  adds to `sys.path`;
- `importlib.util.spec_from_file_location`, `importlib.machinery.SourceFileLoader`
  used directly, and its `exec_module` and `load_module`;
- `runpy.run_module`, which loads through the same loaders (the scanner still
  flags `runpy`, for `run_path`);
- refused rather than run: a `.pyc` without its source
  (`SourcelessFileLoader`), an extension module (`ExtensionFileLoader`) and a
  module in an archive (`zipimport`).

Every other way to run code compiles or loads what it reads at call time, so it
is left to the scanner, which flags these as `python.exec_from_file` (review
required):

- `runpy` (`run_path` compiles a file it reads itself);
- `compile`, and `exec`, `eval` or `compile` reached through `builtins` (bare
  `exec` and `eval` are denied);
- interpreters, debuggers, profilers and runners that run source text: `code`,
  `codeop`, `bdb`, `pdb`, `profile`, `cProfile`, `trace`, `timeit`, `doctest`;
- code objects or calls made from bytes: `marshal`, `pickle`, `_pickle`,
  `shelve`, `CodeType`;
- the import machinery's own loaders: `importlib.abc`, `importlib._bootstrap`,
  `importlib._bootstrap_external`, `_frozen_importlib`,
  `_frozen_importlib_external`, `_imp`, `SourcelessFileLoader` and
  `ExtensionFileLoader` used directly (a file outside the package loads from
  disk), and any class that defines `get_code`, `exec_module`,
  `create_module`, `load_module` or `source_to_code` (a loader of its own,
  including a `SourceFileLoader` subclass that replaces `get_code`);
- `site` (it runs the `import` lines of `.pth` files);
- native code: `ctypes`, `_ctypes`;
- another interpreter, which imports from disk without the guarantee:
  `multiprocessing`, `ProcessPoolExecutor`, `os.exec*`, `os.spawn*`,
  `os.posix_spawn*`, `os.popen`, `pty.spawn`, `asyncio.create_subprocess_*`
  and the event loop's `subprocess_exec` and `subprocess_shell` (`subprocess`
  and `os.system` are denied).

The scanner matches names as the code writes them, including a literal module
name passed to `importlib.import_module` or `__import__`; a name computed at run
time is not seen. Code loaded from a file outside the package directory, for
example one package code writes and then imports, runs from that file like any
other module outside a package.

A registered package changed on disk keeps running the bytes that were
verified, and is checked again whenever it registers again: `plugin_reload`
reloads a package from its lock, which hashes the files first, and the plugin
registry never reloads a skill package from its files.

Unregistering a skill package (on uninstall, and before it registers again on
install, reinstall, rollback or `plugin_reload`) drops its directory from that
lookup and removes from `sys.modules` every module whose file lies under it,
the modules package code imported under its own names included, so an import
after a reinstall runs the bytes verified for that install rather than a module
object kept from before (D-310).

A rollback restores the previous lock, not the previous files. When the files
on disk no longer hash to that revision's `package_hash`, for example because
the update overwrote the same directory, the rollback is refused with
`skill.package_modified` and the current revision stays installed; reinstall
the wanted version instead (D-037).

## Audit And Observability

Every scan/install/uninstall/rollback emits audit events. Runtime use of
package tools continues through ToolRegistry, ExecutionPolicy, approvals,
RunGraph, and metrics. The frontend renders backend findings and must not
reclassify risk locally.

Package tool execution is gated twice: prompt/native schema exposure requires
`skill_policy.enabled_skill_packages` and `tool_policy.allowed_tool_ids`, and
direct dynamic handler calls are denied by the dispatcher unless the same
runtime policy allows the package and tool.

Recommendation is evidence-backed. A package with no skill eval evidence is
`unreviewed`; failed required evals produce `eval_failed`; only passing required
offline `skill_eval.v1` checks can produce `recommended`.
