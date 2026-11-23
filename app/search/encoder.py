"""Text-encoder adapter. The only place that knows about the embedding model."""
from collections.abc import Sequence
from typing import Protocol

import numpy as np

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class TextEncoder(Protocol):
    """Turns texts into vectors: shape (len(texts), dimension)."""

    def encode(self, texts: Sequence[str]) -> np.ndarray: ...


class SentenceTransformerEncoder:
    """Adapter over a pretrained Sentence Transformers model (runs on CPU)."""

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        # Imported here so tests and other modules never pay the model cost.
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name, device="cpu")

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self._model.encode(
            list(texts), convert_to_numpy=True, show_progress_bar=False
        )
        return np.asarray(vectors, dtype=np.float32).reshape(len(texts), -1)
