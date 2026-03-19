# Playbook — Project Execution Process

## Decision Gate: Should This Project Use the Playbook?

Use this process when **all three** are true:

1. **Multi-file deliverable** — more than 2-3 files being created or modified
2. **Architectural decisions required** — tech stack, data models, API design, or file structure choices
3. **Takes more than one agent session** — can’t be completed in a single relay/prompt

**Skip this process and work directly** when:

- Quick config change, single script, or one-file fix
- The task is well-understood and needs no design phase
- Debugging or troubleshooting (interactive back-and-forth is better)
- Infrastructure/ops work that’s mostly commands, not code architecture

When in doubt: if you can describe the entire task in 3 sentences and there’s only one reasonable way to do it, skip the playbook.

---

## Phase 1: Architecture (Human + AI Advisor)

**Goal:** Lock down every design decision before writing code.

**Outputs:** Completed SPEC.md with:

- [ ] Problem statement — what this solves, who it’s for
- [ ] Tech stack — language, framework, database, deployment target
- [ ] File tree — every file and directory, named and placed
- [ ] Data models — every table/schema/type with fields and relationships
- [ ] API contracts — every endpoint/interface with request/response shapes
- [ ] External dependencies — third-party services, APIs, packages with versions
- [ ] Environment — env vars, secrets, ports, config files
- [ ] Constraints — what the agent can’t do (permissions, network, etc.)

**Rules:**

- No code is written in this phase
- Challenge every assumption (“do we actually need a database here?”)
- Name things now, not later — file names, function names, route paths
- If two approaches are viable, pick one and document why

---

## Phase 2: Task Breakdown (Human + AI Advisor)

**Goal:** Decompose the spec into ordered, independently-executable tasks.

**Outputs:** Completed TASKS.md and individual task files in `tasks/`

**Task sizing rules:**

- Each task should be completable in **one agent session** (10-20 file operations max)
- Each task has a **clear input state** (what exists before) and **output state** (what exists after)
- Tasks are ordered by dependency — no task references code that hasn’t been written yet
- First task is always **scaffold** — create the file structure, install dependencies, write config files, no business logic

**Task writing rules:**

- Copy `tasks/_TEMPLATE.md` for each task
- Include acceptance criteria that can be verified programmatically when possible
- Include the exact files the agent will create or modify
- Reference SPEC.md sections, don’t repeat them (“See SPEC.md Data Models”)

---

## Phase 3: Execute (AI Agent — Claude Code)

**Goal:** Complete one task at a time via relay.

**Relay prompt structure:**

```
Read /path/to/project/AGENT_CONTEXT.md for your constraints.
Read /path/to/project/SPEC.md for the full project spec.
Read /path/to/project/tasks/NNN-task-name.md for your current task.

Execute the task as specified. Follow the spec exactly.

If you encounter a conflict, ambiguity, or something that seems wrong:
1. Document the concern at the top of your output
2. Complete the task as spec’d anyway
3. Do not improvise alternatives unless the spec is impossible to follow

When done, list every file you created or modified.
```

**Execution rules:**

- One task per relay — never batch
- Agent reads context from files, not from the prompt
- Agent commits its own work (commit message: “task NNN: short description”)
- If a task fails or times out, do not re-relay blindly — go to Phase 4 first

---

## Phase 4: Verify (Human + AI Advisor)

**Goal:** Confirm the task was completed correctly before advancing.

### Verification Methods by Task Type

| Task Type | Primary Check | Secondary Check |
|---|---|---|
| **Scaffold / setup** | File tree matches spec | Dependencies install clean |
| **Data models / DB** | Schema matches spec | Migrations run without error |
| **API endpoints** | Routes exist, return expected shapes | curl/httpie smoke test |
| **Business logic** | Tests pass | Manual review of edge cases |
| **Frontend / UI** | Renders without errors | Visual spot-check |
| **Config / infra** | Service starts | Logs show no errors |
| **Integration** | End-to-end flow works | Error paths handled |

### Verification workflow:

1. **Read the agent’s output** — check for flagged concerns at the top
2. **Run the primary check** for the task type
3. **Run the secondary check** if primary passes
4. **Log the result** in `reviews/NNN-task-name.md`
5. **If passed:** Update TASKS.md status, advance to next task
6. **If failed:** Go to Failure Protocol

---

## Failure Protocol

When a task produces incorrect output:

### Severity 1 — Minor issues (naming, formatting, small logic error)

1. Document the issue in `reviews/NNN-task-name.md`
2. Create a fix task (e.g., `tasks/NNN-fix.md`) with the specific correction
3. Relay the fix task — include the error description and expected fix

### Severity 2 — Significant deviation from spec

1. Document what went wrong and why in `reviews/NNN-task-name.md`
2. Check if the spec was ambiguous — if so, fix SPEC.md first
3. Re-relay the original task with additional clarification appended
4. If it fails twice: flag for human intervention (do it manually or redesign the task)

### Severity 3 — Architectural problem surfaces

1. **Stop execution.** Do not relay more tasks.
2. Return to Phase 1 — the spec needs revision
3. Assess impact on completed tasks — may need to re-do earlier work
4. Update SPEC.md, re-generate affected task files, resume from the affected point

### General retry rules:

- **Max 2 retries per task** — after that, human intervenes
- **Never retry without new information** — if the prompt was the same, the result will be the same
- **Append, don’t replace** — add clarification to the task file, don’t rewrite it (preserve history of what was tried)
