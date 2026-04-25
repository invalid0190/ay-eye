# Model Selection Playbook

> Guidance for choosing models by phase and task type.
> 
> **No model is required.** These are recommendations, not requirements.

---

## Selection by Phase

### Planning & Architecture

**Recommended capabilities:**
- Extended reasoning / thinking mode
- Large context window (analyze multiple files)
- Strong at structured output (specs, plans)

**Why:** Planning requires understanding full system context and making architectural decisions.

**Examples:** Models with "thinking" or "reasoning" modes, larger context variants.

---

### Code Implementation

**Recommended capabilities:**
- Fast iteration speed
- Good at code completion
- Tool/function calling (for verification commands)

**Why:** Implementation involves many small changes with frequent verification cycles.

**Examples:** Speed-tier models, code-specialized variants.

---

### Refactoring

**Recommended capabilities:**
- Large context window (see before/after)
- Pattern recognition
- Consistent style application

**Why:** Refactoring requires maintaining consistency across large code changes.

**Examples:** Standard or long-context variants.

---

### Debugging

**Recommended capabilities:**
- Extended reasoning (hypothesis generation)
- Good at reading stack traces
- Context for error patterns

**Why:** Debugging requires hypothesis testing and pattern matching.

**Examples:** Reasoning-focused models.

---

### Code Review

**Recommended capabilities:**
- Large context (review full PR diff)
- Security pattern knowledge
- Style consistency checking

**Why:** Review requires seeing both code and context together.

**Examples:** Long-context variants.

---

## Capability Tiers

| Tier | Characteristics | Best For |
|------|-----------------|----------|
| **Fast** | Quick responses, lower cost | Implementation, iteration |
| **Standard** | Balanced speed/quality | Most tasks |
| **Reasoning** | Extended thinking, slower | Planning, debugging, architecture |
| **Long-context** | >100k tokens | Review, refactoring |

---

## Anti-Patterns

âŒ **Using reasoning models for simple edits** â€” Overkill, slow, expensive

âŒ **Using fast models for architecture** â€” Insufficient depth for complex decisions

âŒ **Ignoring context limits** â€” Leads to quality degradation

âŒ **Forcing a specific model** â€” Breaks model-agnosticism

---

## Model Switching Mid-Session

**When to switch:**
- Context is getting polluted (approaching 50%)
- Task type changes significantly (planning â†’ implementation)
- Current model struggling with task type

**How to switch:**
1. Create state snapshot
2. Update STATE.md with current position
3. Start fresh session with appropriate model
4. Load STATE.md to resume

---

## GSD Model-Agnostic Principle

GSD works with any capable LLM. The methodology compensates for model differences through:

1. **Structured plans** â€” Reduce ambiguity
2. **Explicit verification** â€” Catch errors regardless of model
3. **State persistence** â€” Enable model switching
4. **Fresh context** â€” Prevent accumulation issues

Choose models based on task needs, not methodology requirements.

---

*See PROJECT_RULES.md for canonical rules.*
*See docs/runbook.md for operational procedures.*
