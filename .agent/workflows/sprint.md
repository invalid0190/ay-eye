---
description: Create and manage a time-boxed sprint for quick focused work
argument-hint: "[new|status|close] [sprint-name]"
---

# /sprint Workflow

<objective>
Manage time-boxed sprints for quick, focused work outside the full milestone/phase cycle.
Sprints are ideal for bug fixes, small features, or exploratory work that doesn't warrant a full planning cycle.
</objective>

<process>

## 1. Parse Arguments

Extract from $ARGUMENTS:
- **Action**: `new` (default), `status`, or `close`
- **Sprint name**: identifier for the sprint

**If no arguments:** Default to `new` and ask for sprint details.

---

## 2a. Action: New Sprint

### Gather Sprint Information

Ask for:
- **Name** â€” Sprint identifier (e.g., "bugfix-auth", "spike-caching")
- **Goal** â€” One sentence describing the sprint goal
- **Duration** â€” Timeframe (e.g., "2 days", "1 week")
- **Scope** â€” Tasks included and explicitly excluded

### Create Sprint File

Create `.gsd/SPRINT.md` using the template from `.gsd/templates/sprint.md`:

```markdown
# Sprint {N} â€” {Sprint Name}

> **Duration**: {start-date} to {end-date}
> **Status**: In Progress

## Goal
{One sentence goal}

## Scope

### Included
- {Task 1}
- {Task 2}

### Explicitly Excluded
- {Out of scope item}

## Tasks

| Task | Assignee | Status | Est. Hours |
|------|----------|--------|------------|
| {Task 1} | Claude | â¬œ Todo | â€” |
| {Task 2} | Claude | â¬œ Todo | â€” |

## Daily Log

### {today's date}
- Sprint created
```

### Update STATE.md

```markdown
## Current Position
- **Sprint**: {name}
- **Status**: Sprint in progress
- **Milestone**: (paused if active)
```

### Commit

```bash
git add .gsd/SPRINT.md .gsd/STATE.md
git commit -m "docs: create sprint {name}"
```

---

## 2b. Action: Status

Read `.gsd/SPRINT.md` and display:

```
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
 GSD â–º SPRINT STATUS
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”

Sprint: {name}
Duration: {start} to {end}
Tasks: {done}/{total} complete

{task table}

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
```

---

## 2c. Action: Close

### Verify Sprint Complete

Check all tasks are done or explicitly deferred.

### Generate Retrospective

Append to `.gsd/SPRINT.md`:

```markdown
## Retrospective ({date})

### What Went Well
- {auto-extract from daily log}

### What Could Improve
- {identify blockers or friction}

### Action Items
- [ ] {carry-forward items}
```

### Archive Sprint

**PowerShell:**
```powershell
New-Item -ItemType Directory -Force ".gsd/sprints"
Move-Item ".gsd/SPRINT.md" ".gsd/sprints/{name}-SPRINT.md"
```

**Bash:**
```bash
mkdir -p .gsd/sprints
mv .gsd/SPRINT.md ".gsd/sprints/{name}-SPRINT.md"
```

### Update STATE.md

Restore previous milestone position or mark as idle.

### Commit

```bash
git add .gsd/sprints/ .gsd/STATE.md
git commit -m "docs: close sprint {name}"
```

### Display Result

```
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
 GSD â–º SPRINT CLOSED âœ“
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”

Sprint: {name}
Tasks completed: {N}/{total}

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

â–¶ NEXT

/resume â€” Return to milestone work
/sprint new â€” Start another sprint

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
```

</process>

<related>
## Related

### Workflows
| Command | Relationship |
|---------|--------------|
| `/plan` | Full planning cycle (use for milestone work) |
| `/execute` | Full execution cycle (use for milestone work) |
| `/pause` | Pause current work for handoff |

### Templates
| Template | Purpose |
|----------|---------|
| `sprint.md` | Sprint document structure |
</related>
