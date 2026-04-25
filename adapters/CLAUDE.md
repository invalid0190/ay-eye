# Claude Adapter

> **Everything in this file is optional.**
> For canonical rules, see [PROJECT_RULES.md](../PROJECT_RULES.md).

This adapter provides optional enhancements for Claude models in Antigravity.

---

## Extended Thinking Mode

When available, activate extended thinking for:

| Task Type | Recommended |
|-----------|-------------|
| Architecture planning | âœ… High effort |
| Complex debugging | âœ… High effort |
| Security analysis | âœ… High effort |
| Simple edits | âŒ Not needed |
| Quick iterations | âŒ Overhead too high |

### Effort Levels

If the model supports effort/budget levels:

| Level | Use Case |
|-------|----------|
| `low` | Simple edits, formatting, comments |
| `medium` | Standard implementation (default) |
| `high` | Complex logic, refactoring, debugging |
| `max` | Architecture, security, critical decisions |

**Default:** `medium` if not specified.

---

## Artifacts Mode

When artifacts are supported:

- Use for code generation that needs preview
- Use for documentation with formatting
- Avoid for small inline edits

---

## Context Optimization

Claude-specific context tips:

1. **System prompt loading**: Core rules in system prompt, task details in user message
2. **XML structure**: Claude parses XML well â€” use task XML format from GSD-STYLE.md
3. **Conversation history**: Minimal history preferred; use STATE.md for continuity

---

## File Conventions

Not required, but if organizing Claude-specific files:

```
.claude/
â”œâ”€â”€ CLAUDE.md      # This adapter (if using)
â””â”€â”€ settings.json  # IDE-specific settings
```

---

## Anti-Patterns

âŒ **Using max effort for everything** â€” Slow and expensive
âŒ **Skipping verification** â€” Thinking mode doesn't guarantee correctness
âŒ **Depending on artifacts** â€” Not all Claude interfaces support them

---

*See PROJECT_RULES.md for canonical requirements.*
