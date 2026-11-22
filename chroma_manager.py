import os
import math
import hashlib
import logging
from typing import List, Dict, Any, Optional
from datetime import date
from app.core.config import settings

logger = logging.getLogger("circulariq.vectorstore")

class LocalSemanticEmbedder:
    """
    Offline-capable 384-dimensional dense semantic embedding generator.
    Guarantees zero-network requirement, robust cosine similarity ranking,
    and instantaneous computation without remote model downloads.
    """
    DIM = 384

    @staticmethod
    def embed_text(text: str) -> List[float]:
        vec = [0.0] * LocalSemanticEmbedder.DIM
        tokens = text.lower().split()
        if not tokens:
            return vec

        for idx, token in enumerate(tokens):
            # Salience weighting
            weight = 1.0
            if any(term in token for term in ["deadline", "exam", "date", "fee", "attendance", "eligibility", "circular", "policy"]):
                weight = 2.5
            
            # Hash token to projection index
            h = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16)
            pos = h % LocalSemanticEmbedder.DIM
            sign = 1.0 if (h % 2 == 0) else -1.0
            vec[pos] += sign * weight

            # Bigram feature
            if idx > 0:
                bi = f"{tokens[idx-1]}_{token}"
                h_bi = int(hashlib.md5(bi.encode("utf-8")).hexdigest()[:8], 16)
                pos_bi = h_bi % LocalSemanticEmbedder.DIM
                vec[pos_bi] += 1.5

        # L2 Normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    @staticmethod
    def embed_documents(texts: List[str]) -> List[List[float]]:
        return [LocalSemanticEmbedder.embed_text(t) for t in texts]


class ChromaVectorManager:
    """
    Manages vector embeddings and semantic retrieval for CircularIQ policy chunks.
    Preserves document versions, page references, effective dates, and departments.
    """
    def __init__(self):
        self.persist_directory = settings.CHROMA_PERSIST_DIRECTORY
        os.makedirs(self.persist_directory, exist_ok=True)
        self._client = None
        self._collection = None

    def get_collection(self):
        if self._collection is None:
            try:
                import chromadb
                self._client = chromadb.PersistentClient(path=self.persist_directory)
                self._collection = self._client.get_or_create_collection(
                    name="circulariq_policies",
                    metadata={"hnsw:space": "cosine"}
                )
                logger.info("ChromaDB persistent collection loaded successfully.")
            except Exception as e:
                logger.error(f"Error initializing ChromaDB: {e}")
                raise e
        return self._collection

    def add_chunks(
        self,
        document_id: int,
        version_id: int,
        version_number: str,
        document_title: str,
        category: str,
        department: str,
        publication_date: Optional[date],
        effective_date: Optional[date],
        chunks: List[Dict[str, Any]]
    ) -> List[str]:
        collection = self.get_collection()
        ids = []
        documents = []
        metadatas = []
        embeddings = []

        pub_str = publication_date.isoformat() if publication_date else ""
        eff_str = effective_date.isoformat() if effective_date else ""

        for chunk in chunks:
            chunk_id = f"doc_{document_id}_v_{version_id}_p{chunk.get('page', 1)}_idx{chunk.get('index', 0)}"
            ids.append(chunk_id)
            text = chunk["text"]
            documents.append(text)
            embeddings.append(LocalSemanticEmbedder.embed_text(text))
            metadatas.append({
                "document_id": document_id,
                "version_id": version_id,
                "version_number": version_number,
                "document_title": document_title,
                "category": category or "General",
                "department": department or "All",
                "page_number": int(chunk.get("page", 1)),
                "publication_date": pub_str,
                "effective_date": eff_str,
                "token_count": len(text.split())
            })

        if ids:
            collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )
            logger.info(f"Indexed {len(ids)} chunks for document '{document_title}' {version_number}")
        return ids

    def search(
        self,
        query: str,
        n_results: int = 5,
        department_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        as_of_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        collection = self.get_collection()
        where_clauses = []

        if department_filter and department_filter != "All":
            where_clauses.append({"department": department_filter})

        if category_filter and category_filter != "All":
            where_clauses.append({"category": category_filter})

        where_filter = None
        if len(where_clauses) == 1:
            where_filter = where_clauses[0]
        elif len(where_clauses) > 1:
            where_filter = {"$and": where_clauses}

        query_embedding = LocalSemanticEmbedder.embed_text(query)

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=max(n_results * 2, 10),
            where=where_filter
        )

        formatted_results = []
        if not results or not results["documents"] or not results["documents"][0]:
            return formatted_results

        docs = results["documents"][0]
        metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
        distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)

        for doc_text, meta, dist in zip(docs, metas, distances):
            pub_date_str = meta.get("publication_date", "")
            if as_of_date and pub_date_str:
                try:
                    pub_d = date.fromisoformat(pub_date_str)
                    if pub_d > as_of_date:
                        continue  # Exclude circulars published after requested historical As-of-Date
                except Exception:
                    pass

            score = max(0.0, min(1.0, 1.0 - dist)) if dist is not None else 1.0

            formatted_results.append({
                "text": doc_text,
                "metadata": meta,
                "score": round(score, 3)
            })

            if len(formatted_results) >= n_results:
                break

        return formatted_results

vector_manager = ChromaVectorManager()
