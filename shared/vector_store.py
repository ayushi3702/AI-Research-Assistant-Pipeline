"""
Vector store module for RAG (Retrieval-Augmented Generation).
Uses ChromaDB with sentence-transformers embeddings to store and retrieve
document chunks across research jobs.
"""
from __future__ import annotations
import os
import logging
from typing import Optional

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
COLLECTION_NAME = "research_chunks"

# Singleton instances
_client: Optional[chromadb.ClientAPI] = None
_embedding_model: Optional[SentenceTransformer] = None


def _get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embedding_model


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _client


def get_collection() -> chromadb.Collection:
    """Get or create the research chunks collection."""
    client = _get_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts."""
    model = _get_embedding_model()
    embeddings = model.encode(texts, show_progress_bar=False)
    return embeddings.tolist()


def store_chunks(
    chunks: list[dict],
    job_id: str,
) -> int:
    """
    Store extracted chunks in the vector store.

    Args:
        chunks: List of dicts with keys: content, url, source_type, relevance_score
        job_id: The research job ID for metadata filtering

    Returns:
        Number of chunks stored
    """
    if not chunks:
        return 0

    collection = get_collection()
    texts = [c["content"] for c in chunks]
    embeddings = embed_texts(texts)

    ids = [f"{job_id}_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "job_id": job_id,
            "url": c.get("url", ""),
            "source_type": c.get("source_type", "web"),
            "relevance_score": c.get("relevance_score", 0.0),
        }
        for c in chunks
    ]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    logger.info(f"[vector_store] Stored {len(chunks)} chunks for job {job_id}")
    return len(chunks)


def retrieve_relevant_chunks(
    query: str,
    n_results: int = 10,
    exclude_job_id: Optional[str] = None,
) -> list[dict]:
    """
    Retrieve the most relevant chunks from the vector store for a given query.

    Args:
        query: The search/research query
        n_results: Maximum number of results to return
        exclude_job_id: Optionally exclude chunks from a specific job
                        (to avoid retrieving the current job's own chunks)

    Returns:
        List of dicts with keys: content, url, source_type, relevance_score, distance
    """
    collection = get_collection()

    if collection.count() == 0:
        return []

    query_embedding = embed_texts([query])[0]

    where_filter = None
    if exclude_job_id:
        where_filter = {"job_id": {"$ne": exclude_job_id}}

    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, collection.count()),
            where=where_filter,
        )
    except Exception as e:
        logger.warning(f"[vector_store] Query failed: {e}")
        return []

    retrieved = []
    if results and results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 1.0
            retrieved.append({
                "content": doc,
                "url": metadata.get("url", ""),
                "source_type": metadata.get("source_type", ""),
                "relevance_score": metadata.get("relevance_score", 0.0),
                "distance": distance,
                "job_id": metadata.get("job_id", ""),
            })

    logger.info(f"[vector_store] Retrieved {len(retrieved)} chunks for query: {query[:50]}...")
    return retrieved


# ── Document-specific operations ──────────────────────────────────────────────

DOCUMENTS_COLLECTION = "uploaded_documents"


def get_documents_collection() -> chromadb.Collection:
    """Get or create the uploaded documents collection."""
    client = _get_client()
    return client.get_or_create_collection(
        name=DOCUMENTS_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def store_document_chunks(
    chunks: list[str],
    doc_id: str,
    filename: str,
) -> int:
    """
    Store document chunks in the vector store.

    Args:
        chunks: List of text chunks from the document
        doc_id: Unique document identifier
        filename: Original filename

    Returns:
        Number of chunks stored
    """
    if not chunks:
        return 0

    collection = get_documents_collection()
    embeddings = embed_texts(chunks)

    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "doc_id": doc_id,
            "filename": filename,
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadatas,
    )

    logger.info(f"[vector_store] Stored {len(chunks)} document chunks for {filename}")
    return len(chunks)


def query_document(
    query: str,
    doc_id: str,
    n_results: int = 6,
) -> list[dict]:
    """
    Retrieve relevant chunks from a specific uploaded document.

    Args:
        query: The user's question
        doc_id: The document to search within
        n_results: Max results to return

    Returns:
        List of dicts with keys: content, chunk_index, distance
    """
    collection = get_documents_collection()

    if collection.count() == 0:
        return []

    query_embedding = embed_texts([query])[0]

    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, collection.count()),
            where={"doc_id": doc_id},
        )
    except Exception as e:
        logger.warning(f"[vector_store] Document query failed: {e}")
        return []

    retrieved = []
    if results and results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 1.0
            retrieved.append({
                "content": doc,
                "chunk_index": metadata.get("chunk_index", 0),
                "distance": distance,
            })

    return retrieved
