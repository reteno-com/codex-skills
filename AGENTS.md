# AGENTS.md

## Repo Purpose

This repository hosts Reteno-specific Codex skills for internal agent use.
Treat the repository as a research preview unless a task explicitly says a skill is production-ready.

## Working Rules

- Keep the repository lightweight and text-first.
- Each skill must live under `skills/<skill-name>/`.
- Every skill directory must include a `SKILL.md`.
- Add `assets/`, `scripts/`, and `references/` only when they provide real value.
- Prefer updating shared templates before duplicating patterns across skills.
- Document execution prerequisites in the skill itself.
- Avoid storing secrets, generated binaries, or large exports in git.

## Authoring Standard

- Write skill instructions as concrete steps an agent can execute.
- Reference local files with repo-relative paths.
- Keep examples minimal and directly relevant.
- If a skill depends on external tools or APIs, list setup requirements near the top.

## Review Standard

- Confirm the skill can be followed without hidden context.
- Check that referenced files exist.
- Remove dead links, stale examples, and unused assets.
