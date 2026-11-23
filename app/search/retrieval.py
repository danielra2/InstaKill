"""Pure retrieval functions: cosine similarity and deterministic top-k.

No HTTP, no SQLite, no model loading. Input is plain NumPy arrays and
post ids; output is an ordered list of (post_id, score) pairs.
"""
from collections.abc import Sequence

import numpy as np


def cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity between one query vector and every row of `matrix`.

    `query` has shape (d,), `matrix` has shape (n, d). Returns shape (n,).
    A zero-length vector (norm 0) gets similarity 0 instead of NaN.
    """
    query = np.asarray(query, dtype=np.float64)
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.ndim != 2 or query.ndim != 1 or matrix.shape[1] != query.shape[0]:
        raise ValueError(
            f"Shape mismatch: query {query.shape}, matrix {matrix.shape}"
        )
    if matrix.shape[0] == 0:
        return np.zeros(0, dtype=np.float64)

    query_norm = np.linalg.norm(query)
    row_norms = np.linalg.norm(matrix, axis=1)
    denominators = row_norms * query_norm
    dots = matrix @ query

    scores = np.zeros_like(dots)
    nonzero = denominators > 0
    scores[nonzero] = dots[nonzero] / denominators[nonzero]
    return scores


def top_k(
    query: np.ndarray,
    matrix: np.ndarray,
    post_ids: Sequence[int],
    k: int,
) -> list[tuple[int, float]]:
    """Return the `k` most similar posts as (post_id, score) pairs.

    Ordered by descending score; equal scores are ordered by ascending
    post_id, so the result is deterministic.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    ids = np.asarray(post_ids, dtype=np.int64)
    if ids.shape[0] != np.asarray(matrix).shape[0]:
        raise ValueError("post_ids must have one id per matrix row")

    scores = cosine_similarity(query, matrix)
    # np.lexsort sorts by the LAST key first: primary = -score, secondary = id.
    order = np.lexsort((ids, -scores))[:k]
    return [(int(ids[i]), float(scores[i])) for i in order]
