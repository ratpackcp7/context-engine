# Project Playbook

A template repository for planning, specifying, and executing software projects using a human-architect + AI-agent workflow.

## How to Use

1. **Create a new repo from this template** on GitHub (Use as template) or clone and reinitialize
2. **Fill out SPEC.md** — architecture, data models, API contracts, file tree
3. **Break work into tasks** — create numbered task files in `tasks/`
4. **Execute** — relay tasks to Claude Code one at a time
5. **Review** — verify output, log in `reviews/`, advance to next task

## Repo Structure

```
├── PLAYBOOK.md            # The process — phases, decision gates, workflows
├── SPEC.md                # Project-specific architecture & design
├── TASKS.md               # Ordered task queue with status
├── AGENT_CONTEXT.md       # Agent constraints, conventions, permissions
├── tasks/
│   ├── _TEMPLATE.md       # Copy this for each new task
│   └── 001-example.md     # Individual task specs
└── reviews/
    └── 001-example.md     # Post-task review notes
```

## Key Principles

- **Planning is the product.** The spec is written before any code. The agent executes, it doesn’t design.
- **Strict spec, flagged concerns.** The agent follows the spec exactly but reports conflicts or ambiguities.
- **Verify before advancing.** Every task goes through a review gate before the next one starts.
- **Context lives in files.** The agent reads the spec from disk — no token-heavy prompt stuffing.

## Requirements

- Claude Code installed on the execution host
- GitHub CLI (`gh`) authenticated
- SSH/tmux access or relay script for agent dispatch
