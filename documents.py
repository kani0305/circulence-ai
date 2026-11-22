import os
import shutil
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.models import Document, DocumentVersion, ExtractedPolicy, User, PolicyRule, Deadline
from app.schemas.schemas import DocumentOut, DocumentDetailOut, DocumentVersionOut
from app.api.deps import get_current_user, require_faculty_or_admin
from app.agents.orchestrator import orchestrator
from app.core.config import settings

router = APIRouter(prefix="/documents", tags=["Documents"])

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    manual_version: Optional[str] = Form(None),
    current_user: User = Depends(require_faculty_or_admin),
    db: Session = Depends(get_db)
):
    # Validate file type
    filename = file.filename or "unknown.pdf"
    ext = os.path.splitext(filename)[1].lower().replace(".", "")
    if ext not in ("pdf", "docx", "doc", "txt"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Supported formats are PDF, DOCX, and TXT."
        )

    # Save file to uploads directory
    safe_filename = f"{uuid.uuid4().hex[:10]}_{filename}"
    file_path = os.path.join(settings.UPLOAD_DIRECTORY, safe_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    file_size = os.path.getsize(file_path)

    try:
        # Run Multi-Agent processing lifecycle
        result = orchestrator.process_new_document_lifecycle(
            db=db,
            file_path=file_path,
            original_filename=filename,
            file_type=ext,
            file_size=file_size,
            uploaded_by_user_id=current_user.id,
            manual_version=manual_version
        )
        return {
            "message": "Document successfully ingested and analyzed by CircularIQ AI agents.",
            "data": result
        }
    except Exception as e:
        # Clean up file on processing failure
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@router.get("", response_model=List[DocumentOut])
def list_documents(
    search: Optional[str] = None,
    category: Optional[str] = None,
    department: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Document)

    if isinstance(search, str) and search.strip():
        query = query.filter(
            (Document.title.ilike(f"%{search.strip()}%")) |
            (Document.document_number.ilike(f"%{search.strip()}%"))
        )
    if isinstance(category, str) and category != "All" and category.strip():
        query = query.filter(Document.category == category.strip())
    if isinstance(status, str) and status != "All" and status.strip():
        query = query.filter(Document.status == status.strip())

    docs = query.order_by(Document.updated_at.desc()).all()

    results = []
    for d in docs:
        curr_v = None
        if d.current_version_id:
            curr_v = db.query(DocumentVersion).filter(DocumentVersion.id == d.current_version_id).first()
        elif d.versions:
            curr_v = d.versions[-1]

        results.append(DocumentOut(
            id=d.id,
            document_number=d.document_number,
            title=d.title,
            category=d.category,
            status=d.status,
            department_name=d.department.name if d.department else "Academic Affairs",
            current_version=DocumentVersionOut.from_orm(curr_v) if curr_v else None,
            version_count=len(d.versions),
            created_at=d.created_at,
            updated_at=d.updated_at
        ))
    return results

@router.get("/{document_id}")
def get_document_details(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    versions = db.query(DocumentVersion).filter(DocumentVersion.document_id == document_id).order_by(DocumentVersion.created_at.desc()).all()
    latest_v = versions[0] if versions else None

    latest_policy = None
    rules_out = []
    deadlines_out = []

    if latest_v:
        extracted = db.query(ExtractedPolicy).filter(ExtractedPolicy.document_version_id == latest_v.id).first()
        if extracted:
            latest_policy = extracted.raw_extraction_json

        rules = db.query(PolicyRule).filter(PolicyRule.document_version_id == latest_v.id).all()
        rules_out = [{
            "id": r.id,
            "rule_type": r.rule_type,
            "title": r.title,
            "description": r.description,
            "clause_reference": r.clause_reference,
            "page_number": r.page_number
        } for r in rules]

        deadlines = db.query(Deadline).filter(Deadline.document_version_id == latest_v.id).all()
        deadlines_out = [{
            "id": dl.id,
            "title": dl.title,
            "category": dl.category,
            "deadline_date": dl.deadline_date.isoformat(),
            "is_extended": dl.is_extended,
            "is_cancelled": dl.is_cancelled
        } for dl in deadlines]

    return {
        "document": {
            "id": doc.id,
            "document_number": doc.document_number,
            "title": doc.title,
            "category": doc.category,
            "status": doc.status,
            "department_name": doc.department.name if doc.department else "Academic Affairs",
            "created_at": doc.created_at,
            "updated_at": doc.updated_at
        },
        "versions": [DocumentVersionOut.from_orm(v) for v in versions],
        "latest_extracted_policy": latest_policy,
        "rules": rules_out,
        "deadlines": deadlines_out
    }

@router.get("/{document_id}/preview")
def preview_document(document_id: int, version_id: Optional[int] = None, db: Session = Depends(get_db)):
    if version_id:
        v = db.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
    else:
        v = db.query(DocumentVersion).filter(DocumentVersion.document_id == document_id).order_by(DocumentVersion.created_at.desc()).first()

    if not v or not os.path.exists(v.file_path):
        raise HTTPException(status_code=404, detail="Original document file not found")

    # If PDF, return FileResponse
    if v.file_type.lower() == "pdf":
        return FileResponse(v.file_path, media_type="application/pdf", filename=v.file_name)
    else:
        # For txt/docx or fallback, read text preview
        with open(v.file_path, "rb") as f:
            content = f.read()
        return FileResponse(v.file_path, filename=v.file_name)
