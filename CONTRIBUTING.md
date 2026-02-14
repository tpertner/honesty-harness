# Contributing

Thanks for your interest in contributing to **Honesty Harness**!

This repo is intentionally lightweight and practical: small test cases, clear scoring, and reproducible runs.

## How to contribute

### 1) Add a new test case

Add a new YAML or prompt pair under the appropriate folder (for example, `testsuites/` or `examples/`), and include:

- **What it tests** (1 sentence)
- **Expected behavior** (PASS/FAIL criteria)
- **Why it matters** (what failure mode it catches)

### 2) Improve docs

If something is confusing or missing, open a PR with doc edits. Clarity is a contribution.

### 3) Report a bug

Open an issue with:

- steps to reproduce
- expected vs actual behavior
- any relevant logs (please redact secrets)

## Development quickstart

1) Fork the repo and clone your fork.  
2) Create a branch:

- `git checkout -b feat/<short-name>`

3) Install dependencies:

- `python -m pip install -r requirements.txt`

4) Run the suite:

- `python -m evals.runner`

## Style guidelines

- Keep changes small and focused.
- Prefer explicit, readable names over clever ones.
- Add or update docs when behavior changes.
- If you add logic, add a minimal test case or example.

## Commit message style

Use a simple convention:

- `docs: ...`
- `fix: ...`
- `feat: ...`
- `chore: ...`
