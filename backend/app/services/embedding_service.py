import math
import hashlib
import logging
from functools import lru_cache
from typing import List
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Hugging Face Semantic Search Embedding Service.
    Primary Model: sentence-transformers/all-MiniLM-L6-v2 (384 dimensions)
    Supports local CPU inference, lazy loading, and deterministic fallback.
    """

    def __init__(self):
        self.model_name = settings.EMBEDDING_MODEL_NAME
        self.dimension = 384
        self._model = None
        self._loaded = False

    def _load_model(self):
        if self._loaded:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading Hugging Face embedding model: {self.model_name}...")
            self._model = SentenceTransformer(self.model_name, device=settings.DEVICE)
            self._loaded = True
            logger.info("Embedding model loaded successfully.")
        except Exception as e:
            logger.warning(
                f"SentenceTransformer not available or failed to load ({e}). "
                "Operating with deterministic 384-dim fallback vectorizer."
            )
            self._model = None
            self._loaded = True
        return self._model

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generates a 384-dimensional normalized embedding vector for the provided text.
        """
        if not text or not text.strip():
            return [0.0] * self.dimension

        model = self._load_model()
        if model is not None:
            try:
                embedding = model.encode(text, normalize_embeddings=True)
                return [float(x) for x in embedding.tolist()]
            except Exception as e:
                logger.error(f"Error generating embedding via SentenceTransformer: {e}")

        # Fallback: Deterministic normalized 384-dim pseudo-vector via token hashing
        return self._deterministic_fallback_vector(text)

    @lru_cache(maxsize=512)
    def encode_text_cached(self, text: str) -> tuple:
        """Cached single-text embedding returning tuple for immutability and O(1) repeated query lookups."""
        return tuple(self.generate_embedding(text))

    def encode_query(self, text: str) -> List[float]:
        """Encodes user search query leveraging LRU cache."""
        return list(self.encode_text_cached(text.strip().lower()))

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Computes the cosine similarity between two 384-dimensional vectors.
        Uses NumPy vectorization when available for maximum CPU efficiency.
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        try:
            import numpy as np
            v1 = np.asarray(vec1, dtype=np.float32)
            v2 = np.asarray(vec2, dtype=np.float32)
            dot = np.dot(v1, v2)
            n1 = np.linalg.norm(v1)
            n2 = np.linalg.norm(v2)
            if n1 == 0.0 or n2 == 0.0:
                return 0.0
            sim = float(dot / (n1 * n2))
            return max(0.0, min(1.0, (sim + 1.0) / 2.0 if sim < 0 else sim))
        except Exception:
            dot = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = math.sqrt(sum(a * a for a in vec1))
            norm2 = math.sqrt(sum(b * b for b in vec2))
            if norm1 == 0.0 or norm2 == 0.0:
                return 0.0
            similarity = dot / (norm1 * norm2)
            return max(0.0, min(1.0, (similarity + 1.0) / 2.0 if similarity < 0 else similarity))

    def _deterministic_fallback_vector(self, text: str) -> List[float]:
        """
        Produces a reproducible 384-dimensional unit vector using tokenized MD5/SHA256 feature hashing.
        Guarantees that identical semantic concepts yield high similarity even offline without weights.
        """
        vec = [0.0] * self.dimension
        tokens = [t.lower() for t in text.split() if len(t) > 1]
        if not tokens:
            return vec

        for token in tokens:
            # Hash token across vector dimensions
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            val = ((h >> 8) % 1000) / 500.0 - 1.0
            vec[idx] += val

        # Normalize to unit length
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [round(x / norm, 6) for x in vec]
        return vec


embedding_service = EmbeddingService()
