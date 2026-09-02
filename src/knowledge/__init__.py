"""Campaign-scoped knowledge retrieval."""

from .base import (
    EmbeddingProvider,
    KnowledgeBaseStore,
    SparseLexicalEmbeddingProvider,
    get_knowledge_base_store,
)

__all__ = [
    "EmbeddingProvider",
    "KnowledgeBaseStore",
    "SparseLexicalEmbeddingProvider",
    "get_knowledge_base_store",
]
