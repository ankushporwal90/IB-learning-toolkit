"""Phase 3 Retrieval-Augmented Generation pipeline.

RAG lets the app answer questions from specific filing passages instead of
asking the LLM to rely on one truncated excerpt.
"""

from __future__ import annotations

from collections import OrderedDict
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
    section: str = "general"


@dataclass
class RetrievedChunk:
    """A retrieved filing passage with citation metadata."""

    text: str
    document_name: str
    chunk_index: int
    section: str = "general"
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
                    "section": chunk.section,
                }
                for chunk in chunks
            ],
        )
        return len(chunks)

    def retrieve(
        self,
        question: str,
        top_k: int = 5,
        document_name: str | None = None,
    ) -> list[RetrievedChunk]:
        """Retrieve relevant chunks for a question."""

        if not question.strip():
            return []

        where = {"document_name": document_name} if document_name else None
        results = self.collection.query(
            query_texts=[question],
            n_results=top_k,
            where=where,
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
                    section=str(metadata.get("section", "general")),
                    distance=float(distance) if distance is not None else None,
                )
            )
        return retrieved

    def retrieve_section_aware(
        self,
        question: str,
        top_k: int = 5,
        document_name: str | None = None,
    ) -> list[RetrievedChunk]:
        """Route a question to likely filing sections and use hybrid retrieval."""

        route = route_finance_question(question)
        chunks = self.retrieve_hybrid(
            question=route.expanded_question,
            top_k=max(top_k * 3, 12),
            document_name=document_name,
        )
        if not route.preferred_sections:
            return chunks[:top_k]

        scored: list[tuple[float, RetrievedChunk]] = []
        keywords = build_keyword_terms(route.expanded_question)
        for chunk in chunks:
            score = keyword_score(chunk.text, keywords)
            if chunk.section in route.preferred_sections:
                score += 8
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored[:top_k]]

    def retrieve_hybrid(
        self,
        question: str,
        top_k: int = 5,
        document_name: str | None = None,
    ) -> list[RetrievedChunk]:
        """Retrieve with semantic search plus keyword scoring for exact finance facts."""

        expanded_question = expand_finance_query(question)
        semantic_chunks = self.retrieve(
            question=expanded_question,
            top_k=max(top_k, 8),
            document_name=document_name,
        )
        keyword_chunks = self.retrieve_by_keywords(
            question=expanded_question,
            top_k=max(top_k, 8),
            document_name=document_name,
        )

        combined: OrderedDict[tuple[str, int], RetrievedChunk] = OrderedDict()
        for chunk in keyword_chunks + semantic_chunks:
            combined[(chunk.document_name, chunk.chunk_index)] = chunk
        return list(combined.values())[:top_k]

    def retrieve_by_keywords(
        self,
        question: str,
        top_k: int = 5,
        document_name: str | None = None,
    ) -> list[RetrievedChunk]:
        """Keyword retrieval for numeric and financial statement questions."""

        chunks = self.get_document_chunks(document_name=document_name)
        keywords = build_keyword_terms(question)
        scored: list[tuple[float, RetrievedChunk]] = []
        for chunk in chunks:
            score = keyword_score(chunk.text, keywords)
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievedChunk(
                    text=chunk.text,
                    document_name=chunk.document_name,
                    chunk_index=chunk.chunk_index,
                    section=chunk.section,
                    distance=1 / (score + 1),
                )
            for score, chunk in scored[:top_k]
        ]

    def get_document_chunks(self, document_name: str | None = None) -> list[RetrievedChunk]:
        """Load indexed chunks, optionally scoped to one document."""

        where = {"document_name": document_name} if document_name else None
        results = self.collection.get(
            where=where,
            include=["documents", "metadatas"],
        )
        documents = results.get("documents", [])
        metadatas = results.get("metadatas", [])
        chunks: list[RetrievedChunk] = []
        for text, metadata in zip(documents, metadatas):
            chunks.append(
                RetrievedChunk(
                    text=text,
                    document_name=str(metadata.get("document_name", "Unknown document")),
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    section=str(metadata.get("section", "general")),
                )
            )
        return sorted(chunks, key=lambda chunk: (chunk.document_name, chunk.chunk_index))

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
            section=infer_section(text),
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


@dataclass
class QueryRoute:
    """Routing hints for section-aware retrieval."""

    intent: str
    preferred_sections: list[str]
    expanded_question: str


def expand_finance_query(question: str) -> str:
    """Add finance synonyms so retrieval catches filing terminology."""

    lowered = question.lower()
    additions: list[str] = []
    if any(term in lowered for term in ["revenue", "sales", "net sales"]):
        additions.extend(
            [
                "revenue",
                "net sales",
                "total net sales",
                "consolidated statements of operations",
                "statement of operations",
                "fiscal year",
            ]
        )
    if any(term in lowered for term in ["profit", "income", "earnings"]):
        additions.extend(["net income", "operating income", "income statement"])
    if any(term in lowered for term in ["cash flow", "cash from operations", "operating cash"]):
        additions.extend(["cash generated by operating activities", "operating cash flow"])
    if "margin" in lowered:
        additions.extend(["gross margin", "operating margin"])
    if any(term in lowered for term in ["risk", "risks"]):
        additions.extend(["risk factors", "uncertainty", "could adversely affect"])
    return " ".join([question, *additions])


def route_finance_question(question: str) -> QueryRoute:
    """Classify a finance question into likely SEC filing sections."""

    lowered = question.lower()
    expanded = expand_finance_query(question)
    if any(term in lowered for term in ["revenue", "sales", "net sales", "margin", "income"]):
        return QueryRoute(
            intent="financial_metric",
            preferred_sections=["financial_statements", "mda", "segments"],
            expanded_question=expanded,
        )
    if any(term in lowered for term in ["risk", "risks", "competition", "cybersecurity"]):
        return QueryRoute(
            intent="risk",
            preferred_sections=["risk_factors"],
            expanded_question=expanded,
        )
    if any(term in lowered for term in ["cash flow", "liquidity", "debt", "capital"]):
        return QueryRoute(
            intent="liquidity",
            preferred_sections=["mda", "financial_statements"],
            expanded_question=expanded,
        )
    if any(term in lowered for term in ["segment", "product", "geography"]):
        return QueryRoute(
            intent="segments",
            preferred_sections=["segments", "mda", "business"],
            expanded_question=expanded,
        )
    return QueryRoute(intent="general", preferred_sections=[], expanded_question=expanded)


def infer_section(text: str) -> str:
    """Infer a rough SEC section label for a chunk."""

    lowered = text.lower()
    if any(term in lowered for term in ["item 1a", "risk factors", "could adversely affect"]):
        return "risk_factors"
    if any(term in lowered for term in ["item 7", "management's discussion", "management discussion"]):
        return "mda"
    if any(
        term in lowered
        for term in [
            "consolidated statements of operations",
            "consolidated balance sheets",
            "consolidated statements of cash flows",
            "net sales",
            "net income",
        ]
    ):
        return "financial_statements"
    if any(term in lowered for term in ["segment", "iphone", "services net sales", "geographic"]):
        return "segments"
    if any(term in lowered for term in ["item 1", "business", "products and services"]):
        return "business"
    return "general"


def build_keyword_terms(question: str) -> list[str]:
    """Build weighted keyword terms for hybrid retrieval."""

    terms = [
        token
        for token in clean_text(question).lower().replace(",", " ").split()
        if len(token) > 2
    ]
    phrase_terms = [
        "net sales",
        "total net sales",
        "revenue",
        "consolidated statements of operations",
        "statement of operations",
        "fiscal year",
        "net income",
        "operating income",
        "gross margin",
        "cash flow",
    ]
    for phrase in phrase_terms:
        if phrase in question.lower():
            terms.append(phrase)
    return list(dict.fromkeys(terms))


def keyword_score(text: str, keywords: list[str]) -> float:
    """Score text for keyword relevance with a small numeric-table boost."""

    lowered = text.lower()
    score = 0.0
    for keyword in keywords:
        score += lowered.count(keyword.lower())
    if any(term in lowered for term in ["net sales", "revenue", "total net sales"]):
        score += 4
    if any(char.isdigit() for char in text):
        score += 2
    if "consolidated statements of operations" in lowered:
        score += 5
    return score


def build_embedding_function() -> Any:
    """Prefer sentence-transformers embeddings, with hash fallback."""

    settings = get_settings()
    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        return SentenceTransformerEmbeddingFunction(model_name=settings.embedding_model)
    except Exception:
        return HashEmbeddingFunction()
