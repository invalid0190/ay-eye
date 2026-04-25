---
description: Discuss a phase before planning (clarify scope and approach)
argument-hint: "<phase-number>"
---

# /discuss-phase Workflow

<objective>
Interactive discussion about a phase to clarify scope, approach, and concerns before creating plans.
</objective>

<context>
Run BEFORE `/plan` when:
- Phase scope is unclear
- Multiple implementation approaches exist
- Trade-offs need user input
- Dependencies are complex
</context>

<process>

## 1. Load Phase Context

Read from ROADMAP.md:
- Phase objective
- Dependencies
- Current status

---

## 2. Analyze Requirements

From phase objective, extract:
- What needs to be built
- What constraints exist
- What decisions need to be made

---

## 3. Present Discussion Points

```
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
 GSD â–º DISCUSS PHASE {N}
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”

Phase: {name}
Objective: {objective}

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

TOPICS TO DISCUSS

1. SCOPE CLARIFICATION
   - {question about scope}
   - {question about boundaries}

2. IMPLEMENTATION APPROACH
   Option A: {approach}
   Option B: {approach}
   Which do you prefer and why?

3. DEPENDENCIES
   - Requires: {what from previous phases}
   - Missing: {any gaps in earlier work}

4. CONCERNS
   - {potential issue}
   - {risk to flag}

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
```

---

## 4. Gather User Input

Listen for:
- Scope decisions
- Approach preferences
- Constraints not in spec
- Priority clarifications

---

## 5. Document Decisions

Update `.gsd/DECISIONS.md`:

```markdown
## Phase {N} Decisions

**Date:** {date}

### Scope
- {decision about scope}

### Approach
- Chose: {approach}
- Reason: {rationale}

### Constraints
- {constraint identified}
```

---

## 6. Offer Next Steps

```
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

âœ“ Discussion documented in DECISIONS.md

â–¶ NEXT

/plan {N} â€” Create execution plans with this context
/research-phase {N} â€” Deep dive on technical options

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
```

</process>
