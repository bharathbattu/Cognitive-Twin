from hashlib import sha256

import numpy as np

from app.core.config import get_settings


class EmbeddingManager:
    """Provides deterministic local embeddings for the initial scaffold."""

    def __init__(self) -> None:
        self.dimension = get_settings().embedding_dimension

    def embed(self, text: str) -> np.ndarray:
        digest = sha256(text.encode("utf-8")).digest()
        values = np.frombuffer(digest, dtype=np.uint8).astype(np.float32)
        vector = np.resize(values, self.dimension)
        norm = np.linalg.norm(vector)
        return vector if norm == 0 else vector / norm
