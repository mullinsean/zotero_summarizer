"""
Vector Embedding Model

Provides embedding generation using sentence-transformers for local vector search.
"""

from typing import List, Optional
import struct


class VectorEmbeddingModel:
    """
    Local embedding model using sentence-transformers.

    Default model: all-MiniLM-L6-v2 (384 dimensions)
    - Fast inference
    - Good quality for semantic search
    - No API key required
    """

    # Supported models and their dimensions
    SUPPORTED_MODELS = {
        "all-MiniLM-L6-v2": 384,
        "all-mpnet-base-v2": 768,
        "bge-small-en-v1.5": 384,
        "bge-base-en-v1.5": 768,
    }

    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        verbose: bool = False
    ):
        """
        Initialize the embedding model.

        Args:
            model_name: Name of the sentence-transformers model to use
            verbose: Enable verbose logging
        """
        self.model_name = model_name
        self.verbose = verbose
        self._model = None

        # Validate model name
        if model_name not in self.SUPPORTED_MODELS:
            raise ValueError(
                f"Unsupported model: {model_name}. "
                f"Supported models: {list(self.SUPPORTED_MODELS.keys())}"
            )

    def _log(self, message: str):
        """Log message if verbose mode enabled."""
        if self.verbose:
            print(f"[Embeddings] {message}")

    def _load_model(self):
        """Lazy load the model on first use."""
        if self._model is None:
            self._log(f"Loading embedding model: {self.model_name}")
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                self._log(f"Model loaded successfully (dim={self.dimension})")
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for vector embeddings. "
                    "Install with: uv pip install sentence-transformers"
                )

    @property
    def dimension(self) -> int:
        """Return embedding dimension for this model."""
        return self.SUPPORTED_MODELS[self.model_name]

    def embed_documents(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Embed multiple documents.

        Args:
            texts: List of text strings to embed
            batch_size: Batch size for processing

        Returns:
            List of embedding vectors (each is a list of floats)
        """
        if not texts:
            return []

        self._load_model()
        self._log(f"Embedding {len(texts)} documents...")

        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=self.verbose,
            convert_to_numpy=True
        )

        # Convert numpy arrays to lists
        return [emb.tolist() for emb in embeddings]

    def embed_query(self, query: str) -> List[float]:
        """
        Embed a single query.

        Args:
            query: Query text to embed

        Returns:
            Embedding vector as list of floats
        """
        self._load_model()
        self._log(f"Embedding query: {query[:50]}...")

        embedding = self._model.encode(query, convert_to_numpy=True)
        return embedding.tolist()

    @staticmethod
    def serialize_embedding(embedding: List[float]) -> bytes:
        """
        Serialize embedding to bytes for SQLite storage.

        Args:
            embedding: List of floats

        Returns:
            Bytes representation for BLOB storage
        """
        return struct.pack(f'{len(embedding)}f', *embedding)

    @staticmethod
    def deserialize_embedding(data: bytes, dimension: int) -> List[float]:
        """
        Deserialize embedding from bytes.

        Args:
            data: Bytes from SQLite BLOB
            dimension: Expected dimension of embedding

        Returns:
            List of floats
        """
        return list(struct.unpack(f'{dimension}f', data))


def get_embedding_model(
    model_name: str = VectorEmbeddingModel.DEFAULT_MODEL,
    verbose: bool = False
) -> VectorEmbeddingModel:
    """
    Factory function to get embedding model instance.

    Args:
        model_name: Name of the model to use
        verbose: Enable verbose logging

    Returns:
        VectorEmbeddingModel instance
    """
    return VectorEmbeddingModel(model_name=model_name, verbose=verbose)
