# codex-skills

> Research preview: this repository is an early public-facing workspace for Reteno agent skills. Expect iteration, experiments, and evolving conventions.

Shared repository for Reteno skills used by Codex agents.

## Purpose

This repo is the source of truth for reusable agent skills, templates, and supporting documentation.

## Structure

- `skills/` - production-ready skills, one skill per directory.
- `AGENTS.md` - repo-specific operating rules for agents working in this project.

## Current Public Candidates

The first skills being prepared here for later public publication are:

- `reteno-email-editor`
- `web-funnel-analyzer`

## Skill Layout

Each skill should live in its own folder and include:

- `SKILL.md` - the skill instructions and workflow.
- `assets/` - optional templates, prompts, examples, or media.
- `scripts/` - optional automation scripts used by the skill.
- `references/` - optional narrow supporting docs.

## Contributing

1. Create `skills/<skill-name>/SKILL.md`.
2. Add only the assets, scripts, and references the skill actually needs.
3. Keep instructions operational and specific to the task the skill solves.

## Status

Initial scaffold created on March 11, 2026.
Research preview positioning and first imported skills added on March 11, 2026.
Repository cleanup completed on March 11, 2026.
