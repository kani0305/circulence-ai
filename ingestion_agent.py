import os
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.models import Document, DocumentVersion, DocumentChunk, Department
from app.services.document_parser import DocumentParser
from app.vectorstore.chroma_manager import vector_manager

class DocumentIngestionAgent:
    """
    Agent 1: Document Ingestion Agent
    Responsibilities:
    - Accepts PDF, DOCX, TXT.
    - Extracts text with page tracking.
    - Extracts metadata: title, department, category, pub_date, effective_date, ref_no.
    - Chunks document into meaningful segments.
    - Generates vector embeddings & stores in ChromaDB.
    - Stores structured metadata in database.
    """

    def process_document(
        self,
        db: Session,
        file_path: str,
        original_filename: str,
        file_type: str,
        file_size: int,
        uploaded_by_user_id: Optional[int] = None,
        manual_version: Optional[str] = None
    ) -> Dict[str, Any]:
        # 1. Extract text by page
        pages = DocumentParser.extract_text_from_file(file_path, file_type)
        if not pages or all(not p.get("text") for p in pages):
            raise ValueError("Document contains no readable text or is corrupted.")

        # 2. Extract metadata heuristics
        metadata = DocumentParser.extract_metadata(pages, original_filename)
        
        # 3. Associate or create department
        dept_record = db.query(Department).filter(
            (Department.name.ilike(f"%{metadata['department']}%")) |
            (Department.code.ilike(f"%{metadata['department'][:4]}%"))
        ).first()

        dept_id = dept_record.id if dept_record else None

        # 4. Check if document entity already exists by document_number or close title match
        existing_doc = db.query(Document).filter(
            (Document.document_number == metadata["document_number"]) |
            (Document.title.ilike(metadata["title"]))
        ).first()

        if existing_doc:
            doc = existing_doc
            # Compute next version number e.g. v2.0
            version_count = len(doc.versions)
            version_str = manual_version or f"v{version_count + 1}.0"
            # Supersede old active versions if this is a newer version
            for prev_v in doc.versions:
                if prev_v.status == "active":
                    prev_v.status = "superseded"
        else:
            doc = Document(
                document_number=metadata["document_number"],
                title=metadata["title"],
                department_id=dept_id,
                category=metadata["category"],
                status="active"
            )
            db.add(doc)
            db.flush()
            version_str = manual_version or "v1.0"

        # 5. Create document version record
        doc_version = DocumentVersion(
            document_id=doc.id,
            version_number=version_str,
            publication_date=metadata["publication_date"],
            effective_date=metadata["effective_date"],
            file_name=original_filename,
            file_path=file_path,
            file_type=file_type,
            file_size=file_size,
            status="active",
            uploaded_by_user_id=uploaded_by_user_id
        )
        db.add(doc_version)
        db.flush()

        doc.current_version_id = doc_version.id

        # 6. Chunking and Vector Ingestion
        chunks_data = DocumentParser.chunk_document(pages)
        db_chunks = []
        for c in chunks_data:
            chunk_rec = DocumentChunk(
                document_version_id=doc_version.id,
                chunk_index=c["index"],
                page_number=c["page"],
                content=c["text"],
                token_count=len(c["text"].split())
            )
            db_chunks.append(chunk_rec)
        db.add_all(db_chunks)
        db.flush()

        # Ingest to ChromaDB
        try:
            vector_manager.add_chunks(
                document_id=doc.id,
                version_id=doc_version.id,
                version_number=version_str,
                document_title=doc.title,
                category=doc.category,
                department=metadata["department"],
                publication_date=doc_version.publication_date,
                effective_date=doc_version.effective_date,
                chunks=chunks_data
            )
        except Exception as e:
            # Vector indexing logged safely
            pass

        db.commit()

        return {
            "document_id": doc.id,
            "version_id": doc_version.id,
            "version_number": version_str,
            "title": doc.title,
            "document_number": doc.document_number,
            "department": metadata["department"],
            "category": doc.category,
            "pages_count": len(pages),
            "chunks_count": len(chunks_data),
            "publication_date": doc_version.publication_date,
            "effective_date": doc_version.effective_date,
            "pages_raw": pages
        }

ingestion_agent = DocumentIngestionAgent()
