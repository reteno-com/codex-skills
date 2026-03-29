# Reteno Agents for Codex

> Outdated repository: use the maintained Reteno AI plugin repository instead: https://github.com/reteno-com/ai-plugin
>
> This repository is no longer the recommended entry point for users.

> Research preview: this repository is an early public-facing workspace for Reteno agent skills. Expect iteration, experiments, and evolving conventions.

Shared repository for Reteno agents and skills used by Codex.

Current version: `0.1.1`

## Purpose

This repo is outdated and retained for historical/reference purposes only.
For current Reteno AI plugin work, use https://github.com/reteno-com/ai-plugin.

## Structure

- `skills/` - production-ready skills, one skill per directory.
- `VERSION` - canonical repository version shared by all in-repo skills.
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

Each in-repo skill must also declare a `version` field in `SKILL.md` frontmatter, and that value must match the root `VERSION` file.

## Contributing

1. Create `skills/<skill-name>/SKILL.md`.
2. Add only the assets, scripts, and references the skill actually needs.
3. Set the skill `version` to match the root `VERSION`.
4. Keep instructions operational and specific to the task the skill solves.

Validate shared versioning with:

```bash
python3 scripts/check_versions.py
```

## Status

Initial scaffold created on March 11, 2026.
Research preview positioning and first imported skills added on March 11, 2026.
Repository cleanup completed on March 11, 2026.
