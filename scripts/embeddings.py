# -*- coding: utf-8 -*-
"""
MemoryOS Embedding Layer (L1 Stub)
---------------------------------
Provides cosine similarity and embedding hooks for semantic recall.
Safe for one-way read-only operation.
"""

import math
from typing import List

def get_emb(text: str) -> List[float]:
    """
    Placeholder embedding function.
    In production, replace this with actual model call (e.g. Ollama, OpenAI, or local vector DB).
    Must return a normalized vector.
    """
    # Simple deterministic hash → pseudo vector (for testing)
    import hashlib
    h = hashlib.sha256(text.encode("utf-8")).digest()
    # Repeat the hash to get 64 dimensions
    h_extended = h + h
    return [b / 255.0 for b in h_extended[:64]]

def cosine_sim(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a*b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a*a for a in v1))
    norm2 = math.sqrt(sum(b*b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)
