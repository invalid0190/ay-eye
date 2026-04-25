---
description: The Auditor â€” Validate work against spec with empirical evidence
argument-hint: "<phase-number>"
---

# /verify Workflow

<role>
You are a GSD verifier. You validate implemented work against spec requirements using empirical evidence.

**Core principle:** No "trust me, it works." Every verification produces proof.

**Core responsibilities:**
- Extract testable deliverables from phase
- Walk through each requirement
- Collect empirical evidence (commands, screenshots)
- Create verification report
- Generate fix plans if issues found
</role>

<objective>
Confirm that implemented work meets spec requirements with documented proof.

The verifier checks the CODEBASE, not SUMMARY claims.
</objective>

<context>
**Phase:** $ARGUMENTS (required â€” phase number to verify)

**Required files:**
- `.gsd/SPEC.md` â€” Original requirements
- `.gsd/ROADMAP.md` â€” Phase definition with must-haves
- `.gsd/phases/{phase}/*-SUMMARY.md` â€” What was implemented
</context>

<process>

## 1. Load Verification Context

Read:
- Phase definition from `.gsd/ROADMAP.md`
- Original requirements from `.gsd/SPEC.md`
- All SUMMARY.md files from `.gsd/phases/{phase}/`

---

## 2. Extract Must-Haves

From the phase definition, identify **must-haves** â€” requirements that MUST be true for the phase to be complete.

```markdown
### Must-Haves for Phase {N}
1. {Requirement 1} â€” How to verify
2. {Requirement 2} â€” How to verify
3. {Requirement 3} â€” How to verify
```

---

## 3. Verify Each Must-Have

For each must-have:

### 3a. Determine Verification Method

| Type | Method | Evidence |
|------|--------|----------|
| API/Backend | Run curl or test command | Command output |
| UI | Use browser tool | Screenshot |
| Build | Run build command | Success output |
| Tests | Run test suite | Test results |
| File exists | Check filesystem | File listing |
| Code behavior | Run specific scenario | Output |

### 3b. Execute Verification

Run the verification command/action.

// turbo
```bash
# Example: Run tests
npm test
```

### 3c. Record Evidence

For each must-have, record:
- **Status:** PASS / FAIL
- **Evidence:** Command output, screenshot path, etc.
- **Notes:** Any observations

---

## 4. Create Verification Report

Write `.gsd/phases/{phase}/VERIFICATION.md`:

```markdown
---
phase: {N}
verified_at: {timestamp}
verdict: PASS | FAIL | PARTIAL
---

# Phase {N} Verification Report

## Summary
{X}/{Y} must-haves verified

## Must-Haves

### âœ… {Must-have 1}
**Status:** PASS
**Evidence:** 
```
{command output or description}
```

### âŒ {Must-have 2}
**Status:** FAIL
**Reason:** {why it failed}
**Expected:** {what should happen}
**Actual:** {what happened}

## Verdict
{PASS | FAIL | PARTIAL}

## Gap Closure Required
{If FAIL, list what needs to be fixed}
```

---

## 5. Handle Results

### If PASS (all must-haves verified):

Update `.gsd/STATE.md`:
```markdown
## Current Position
- **Phase**: {N} (verified)
- **Status**: âœ… Complete and verified
```

Output:
```
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
 GSD â–º PHASE {N} VERIFIED âœ“
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”

{X}/{X} must-haves verified

All requirements satisfied.

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

â–¶ Next Up

/execute {N+1} â€” proceed to next phase

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
```

### If FAIL (some must-haves failed):

**Create gap closure plans:**

For each failed must-have, create a fix plan in `.gsd/phases/{phase}/`:

```markdown
---
phase: {N}
plan: fix-{issue}
wave: 1
gap_closure: true
---

# Fix Plan: {Issue Name}

## Problem
{What failed and why}

## Tasks

<task type="auto">
  <name>Fix {issue}</name>
  <files>{files to modify}</files>
  <action>{specific fix instructions}</action>
  <verify>{how to verify the fix}</verify>
  <done>{acceptance criteria}</done>
</task>
```

Output:
```
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
 GSD â–º PHASE {N} GAPS FOUND âš 
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”

{X}/{Y} must-haves verified
{Z} issues require fixes

Gap closure plans created.

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

â–¶ Next Up

/execute {N} --gaps-only â€” run fix plans

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
```

---

## 6. Commit Verification

```bash
git add .gsd/phases/{phase}/VERIFICATION.md
git commit -m "docs(phase-{N}): verification report"
```

</process>

<evidence_requirements>

## Forbidden Phrases

Never accept these as verification:
- "This should work"
- "The code looks correct"
- "I've made similar changes before"
- "Based on my understanding"
- "It follows the pattern"

## Required Evidence

| Claim | Required Proof |
|-------|----------------|
| "Tests pass" | Actual test output |
| "API works" | Curl command + response |
| "UI renders" | Screenshot |
| "Build succeeds" | Build output |
| "File created" | `ls` or `dir` output |

</evidence_requirements>

<related>
## Related

### Workflows
| Command | Relationship |
|---------|--------------|
| `/execute` | Run before /verify to implement work |
| `/execute --gaps-only` | Fix issues found by /verify |
| `/debug` | Diagnose verification failures |

### Skills
| Skill | Purpose |
|-------|---------|
| `verifier` | Detailed verification methodology |
| `empirical-validation` | Evidence requirements |
</related>
