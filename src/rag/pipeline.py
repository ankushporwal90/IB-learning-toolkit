"""Phase 3 Retrieval-Augmented Generation pipeline.

RAG lets the app answer questions from specific filing passages instead of
asking the LLM to rely on one truncated excerpt.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.services.llm_service import LLMService
from src.services.phase1_filing_summary import FilingExtractionResult, clean_text
from src.utils.config import PROJECT_ROOT, get_settings


DEFAULT_CHUNK_SIZE = 1_200
DEFAULT_CHUNK_OVERLAP = 200


@dataclass
class DocumentChunk:
    """A chunk of filing text stored for retrieval."""

    text: str
    document_name: str
    chunk_index: int


@dataclass
class RetrievedChunk:
    """A retrieved filing passage with citation metadata."""

    text: str
    document_name: str
    chunk_index: int
    distance: float | None = None

    @property
    def citation(self) -> str:
        """Human-readable citation label."""

        return f"{self.document_name}, chunk {self.chunk_index}"


class HashEmbeddingFunction:
    """Small deterministic embedding fallback.

    Sentence-transformers is preferred. This fallback avoids hard failure when a
    local model is unavailable, but retrieval quality will be weaker.
    """

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def __call__(self, input: list[str]) -> list[list[float]]:
        """Return normalized hash embeddings for ChromaDB."""

        return [self.embed_text(text) for text in input]

    def embed_text(self, text: str) -> list[float]:
        """Embed text with a lightweight hashing trick."""

        vector = [0.0] * self.dimensions
        for token in clean_text(text).lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class RagPipeline:
    """ChromaDB-backed RAG pipeline for filings."""

    def __init__(self, collection_name: str = "sec_filing_chunks") -> None:
        self.settings = get_settings()
        self.collection_name = collection_name
        self.embedding_function = build_embedding_function()
        self.collection = self._build_collection()

    def ingest_extraction(
        self,
        extraction: FilingExtractionResult,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> int:
        """Split a document into chunks and upsert them into ChromaDB."""

        chunks = chunk_extraction(
            extraction=extraction,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        if not chunks:
            return 0

        self.collection.upsert(
            ids=[build_chunk_id(chunk) for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            metadatas=[
                {
                    "document_name": chunk.document_name,
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in chunks
            ],
        )
        return len(chunks)

    def retrieve(self, question: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Retrieve relevant chunks for a question."""

        if not question.strip():
            return []

        results = self.collection.query(
            query_texts=[question],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        retrieved: list[RetrievedChunk] = []
        for text, metadata, distance in zip(documents, metadatas, distances):
            retrieved.append(
                RetrievedChunk(
                    text=text,
                    document_name=str(metadata.get("document_name", "Unknown document")),
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    distance=float(distance) if distance is not None else None,
                )
            )
        return retrieved

    def indexed_chunk_count(self) -> int:
        """Return number of chunks currently indexed."""

        return int(self.collection.count())

    def _build_collection(self) -> Any:
        """Create or load the Chroma collection."""

        import chromadb

        persist_dir = PROJECT_ROOT / self.settings.chroma_persist_dir
        persist_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(persist_dir))
        return client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
        )


def chunk_extraction(
    extraction: FilingExtractionResult,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """Split extracted document text into overlapping chunks."""

    return [
        DocumentChunk(
            text=text,
            document_name=extraction.document_name,
            chunk_index=index,
        )
        for index, text in enumerate(split_text(extraction.text, chunk_size, chunk_overlap))
    ]


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split text into overlapping character chunks."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap cannot be negative.")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size.")

    cleaned = clean_text(text)
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = start + chunk_size
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start = end - chunk_overlap
    return chunks


def build_chunk_id(chunk: DocumentChunk) -> str:
    """Build a stable Chroma ID for a chunk."""

    digest = hashlib.sha1(chunk.document_name.encode("utf-8")).hexdigest()[:12]
    return f"{digest}_chunk_{chunk.chunk_index}"


def build_rag_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    """Build a citation-aware prompt from retrieved chunks."""

    context_blocks = []
    for index, chunk in enumerate(chunks, start=1):
        context_blocks.append(
            f"[Source {index}] {chunk.citation}\n{chunk.text}"
        )

    return f"""
Answer the user's finance question using only the retrieved filing context.

Question:
{question}

Retrieved context:
{chr(10).join(context_blocks)}

Rules:
- Cite sources inline using [Source 1], [Source 2], etc.
- If the context does not answer the question, say what is missing.
- Do not give buy, sell, or hold recommendations.
- Keep the answer concise and analyst-friendly.
""".strip()


def answer_question_with_rag(
    question: str,
    chunks: list[RetrievedChunk],
    llm_service: LLMService | None = None,
) -> str:
    """Generate a cited answer from retrieved chunks."""

    if not chunks:
        return "No relevant filing chunks were retrieved. Index a document first or ask a different question."

    llm = llm_service or LLMService()
    if not llm.is_configured():
        sources = ", ".join(chunk.citation for chunk in chunks)
        return f"Groq is not configured. Retrieved sources: {sources}"

    system_prompt = (
        "You are a careful finance analyst. Answer only from provided filing excerpts "
        "and cite the retrieved sources."
    )
    return llm.generate(system_prompt=system_prompt, user_prompt=build_rag_prompt(question, chunks))


def build_embedding_function() -> Any:
    """Prefer sentence-transformers embeddings, with hash fallback."""

    settings = get_settings()
    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        return SentenceTransformerEmbeddingFunction(model_name=settings.embedding_model)
    except Exception:
        return HashEmbeddingFunction()
