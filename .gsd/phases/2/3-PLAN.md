---
phase: 2
plan: 3
wave: 2
---

# Plan 2.3: Memory Manager (ChromaDB)

## Objective
Implement persistent, semantic long-term memory using ChromaDB while maintaining a low RAM footprint.

## Context
- .gsd/DECISIONS.md
- core/state/models.py

## Tasks

<task type="auto">
  <name>ChromaDB Integration</name>
  <files>core/state/memory.py</files>
  <action>
    - Initialize ChromaDB with disk persistence.
    - Implement the Hybrid Retrieval:
      1. Hard filter by App/Window name.
      2. Semantic search on filtered subset for top 3-5 matches.
    - Implement "Memory Ingestion": Store successful interactions and user-corrected workflows.
  </action>
  <verify>python core/state/memory.py (should store and retrieve a test memory)</verify>
  <done>Memory system provides context-relevant retrieval with minimal RAM usage.</done>
</task>

<task type="auto">
  <name>Short-Term Memory (RAM)</name>
  <files>core/state/short_term.py</files>
  <action>
    - Implement a simple sliding window buffer (list) for the last 10 interactions.
    - This buffer is directly included in the prompt for conversational coherence.
  </action>
  <verify>python -c "from core.state.short_term import buffer; buffer.add('test'); print(buffer.get_all())"</verify>
  <done>Short-term memory maintains immediate history correctly.</done>
</task>

## Success Criteria
- [ ] Long-term memory retrieves relevant past interactions based on app context.
- [ ] RAM usage for memory remains low through disk-based persistence and filtering.
