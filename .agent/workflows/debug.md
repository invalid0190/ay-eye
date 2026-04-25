---
description: Systematic debugging with persistent state
argument-hint: "[description of issue]"
---

# /debug Workflow

<role>
You are a GSD debugger orchestrator. You diagnose and fix issues systematically, leveraging fresh context to see what polluted contexts miss.
</role>

<objective>
Systematically diagnose an issue using hypothesis-driven debugging, with persistent state to prevent circular attempts.
</objective>

<context>
**Issue:** $ARGUMENTS (description of the problem to debug)

**Skill reference:** `.agents/skills/debugger/SKILL.md`
</context>

<process>

## 1. Initialize Debug Session

Check for existing debug state:
**PowerShell:**
```powershell
Test-Path ".gsd/DEBUG.md"
```

**Bash:**
```bash
test -f ".gsd/DEBUG.md"
```

If exists, load previous attempts. If not, create new session.

Display banner:
```
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
 GSD â–º DEBUG SESSION
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”

Issue: {description}
```

---

## 2. Document Symptom

Create/update `.gsd/DEBUG.md`:

```markdown
# Debug Session: {Issue ID}

## Symptom
{Exact description of the problem}

**When:** {When does it occur?}
**Expected:** {What should happen?}
**Actual:** {What actually happens?}
```

---

## 3. Gather Evidence

Collect data BEFORE forming hypotheses:

**PowerShell:**
```powershell
# Get error details
{relevant commands to capture error info}

# Check logs
Get-Content logs/error.log -Tail 50

# Check environment
{relevant environment checks}
```

**Bash:**
```bash
# Get error details
{relevant commands to capture error info}

# Check logs
tail -50 logs/error.log

# Check environment
{relevant environment checks}
```

Document evidence in DEBUG.md.

---

## 4. Form Hypotheses

Based on evidence, list possible causes:

```markdown
## Hypotheses

| # | Hypothesis | Likelihood | Status |
|---|------------|------------|--------|
| 1 | {cause 1} | 80% | UNTESTED |
| 2 | {cause 2} | 15% | UNTESTED |
| 3 | {cause 3} | 5% | UNTESTED |
```

---

## 5. Test Hypotheses

Test highest likelihood first:

```markdown
## Attempts

### Attempt 1
**Testing:** H1 â€” {hypothesis}
**Action:** {what you did to test}
**Result:** {outcome}
**Conclusion:** {CONFIRMED | ELIMINATED | INCONCLUSIVE}
```

---

## 6. Apply Fix (If Root Cause Found)

When root cause confirmed:

1. Implement fix
2. Run original failing scenario
3. Verify PASSES
4. Check for regressions

Update DEBUG.md:
```markdown
## Resolution

**Root Cause:** {what was actually wrong}
**Fix:** {what was changed}
**Verified:** {how fix was verified}
**Regression Check:** {what else was tested}
```

---

## 7. Handle 3-Strike Rule

If 3 attempts fail on SAME approach:

```
âš ï¸ 3 FAILURES ON SAME APPROACH

Action: STOP and reassess

Options:
1. Try fundamentally DIFFERENT approach
2. /pause for fresh session context
3. Ask user for additional information
```

Update DEBUG.md and recommend next steps.

---

## 8. Commit Resolution

If fixed:
```bash
git add -A
git commit -m "fix: {brief description of fix}"
```

Update STATE.md with resolution.

</process>

<offer_next>

**If Resolved:**
```
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
 GSD â–º BUG FIXED âœ“
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”

Root cause: {what was wrong}
Fix: {what was done}

Committed: {hash}

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
```

**If Stuck After 3 Attempts:**
```
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
 GSD â–º DEBUG PAUSED â¸
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”

3 attempts exhausted on current approach.
State saved to .gsd/DEBUG.md

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

Options:
â€¢ /debug {issue} â€” try different approach
â€¢ /pause â€” save state for fresh session
â€¢ Provide more context about the issue

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
```

</offer_next>

<related>
## Related

### Workflows
| Command | Relationship |
|---------|--------------|
| `/pause` | Use after 3 failed attempts |
| `/resume` | Start fresh with documented state |
| `/verify` | Re-verify after fixing issues |

### Skills
| Skill | Purpose |
|-------|---------|
| `debugger` | Detailed debugging methodology |
| `context-health-monitor` | 3-strike rule |
</related>
