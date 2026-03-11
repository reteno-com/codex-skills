# codex-skills

Shared repository for Reteno skills used by Codex agents.

## Purpose

This repo is the source of truth for reusable agent skills, templates, and supporting documentation.

## Structure

- `skills/` - production-ready skills, one skill per directory.
- `templates/skill-template/` - starter template for creating a new skill.
- `AGENTS.md` - repo-specific operating rules for agents working in this project.

## Skill Layout

Each skill should live in its own folder and include:

- `SKILL.md` - the skill instructions and workflow.
- `assets/` - optional templates, prompts, examples, or media.
- `scripts/` - optional automation scripts used by the skill.
- `references/` - optional narrow supporting docs.

## Contributing

1. Copy `templates/skill-template/` into `skills/<skill-name>/`.
2. Replace placeholders in `SKILL.md`.
3. Add only the assets and scripts the skill actually needs.
4. Keep instructions operational and specific to the task the skill solves.

## Status

Initial scaffold created on March 11, 2026.
