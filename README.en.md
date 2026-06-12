# code-change-check

[简体中文](README.md)

`code-change-check` is a Skill for reviewing AI-generated code changes. It combines iteration scope, requirements, business contracts, Java semantic evidence, call graphs, and baseline/target differences into a traceable report.

The current version provides deep semantic analysis for **Java** only.

## Capabilities

- Git, SVN, directory snapshots, and current working trees.
- Interactive commit/revision selection with arrow keys, space, and Enter.
- OpenSpec, spec-kit, superpowers, and ordinary Markdown requirements or task lists.
- Contracts from explicit files, baseline code, both, or none.
- Spoon `NOCLASSPATH` analysis for field mappings, call arguments, configuration sources, HTTP addresses, database writes, guards, and state conditions.
- CodeGraph analysis for callers, callees, impact scope, and affected tests.
- Automatic baseline/target semantic comparison.
- Explicit `success`, `partial`, and `blocked` audit coverage states.

## Requirements

- Python 3.10+.
- Java 17+. System Java is preferred; a pinned Windows runtime is downloaded and cached when Java is missing.
- Users do not need Maven, Gradle, Node.js, npm, or a global CodeGraph installation.

## Usage

```bash
run-code-change-check.cmd --project . --output code-change-check-output
run-code-change-check.cmd --project . --base-ref main --target-ref HEAD --no-interactive
run-code-change-check.cmd --project . --svn-revision 100:120 --no-interactive
run-code-change-check.cmd --project . --scan-all --java-analysis required --no-interactive
run-code-change-check.cmd --project . --scan-all --offline --no-interactive
```

Java analysis options:

- `--java-analysis auto|required|off`
- `--tool-cache <path>`
- `--offline`

Open a fresh Claude Code or Codex conversation before each review. An independent context reduces self-review bias and keeps the development conversation focused.

The report contains Java parsing coverage, semantic differences, call graph impact, affected tests, business contract results, and explicit evidence limitations.
