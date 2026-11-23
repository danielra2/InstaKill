"""Test doubles shared by the search tests (no model download needed)."""
from collections.abc import Sequence

import numpy as np

VOCAB = ["cat", "dog", "pizza", "pasta", "python", "code"]


class KeywordEncoder:
    """Tiny fake encoder: one dimension per vocabulary word (word counts)."""

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        rows = []
        for text in texts:
            words = text.lower().split()
            rows.append([words.count(term) for term in VOCAB])
        return np.asarray(rows, dtype=np.float32).reshape(len(texts), len(VOCAB))
