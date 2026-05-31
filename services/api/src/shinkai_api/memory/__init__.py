"""4-layer memory primitives per alignment-v2 §10.

- Working    (within a run)     : recent events, scratch.
- Episodic   (across runs)      : completed-run summaries; recall prior work.
- Semantic   (curated, durable) : validated facts (e.g. "AMD's HBM partner is ...").
- Procedural (curated, durable) : trajectory templates ("for power infra, search Y first").

This module provides the schema + an in-memory store. Persistence integration is
gated on the LLMRouter (#29) being wired so that memory consolidation can rely
on a real critic-style judgment of which working-memory items to elevate.
"""

from shinkai_api.memory.models import (
    EpisodicRecord,
    MemoryEntry,
    MemoryLayer,
    ProceduralRecord,
    SemanticFact,
    WorkingMemoryItem,
)
from shinkai_api.memory.store import InMemoryMemoryStore, default_memory_store

__all__ = [
    "EpisodicRecord",
    "InMemoryMemoryStore",
    "MemoryEntry",
    "MemoryLayer",
    "ProceduralRecord",
    "SemanticFact",
    "WorkingMemoryItem",
    "default_memory_store",
]
