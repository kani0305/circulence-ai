from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.models import (
    Document, DocumentVersion, PolicyChange, 
    PolicyContradiction, ContradictionResolution, User
)
from app.schemas.schemas import (
    VersionComparisonResult, ContradictionOut, ResolveContradictionIn
)
from app.agents.version_agent import version_agent
from app.api.deps import get_current_user, require_admin

router = APIRouter(prefix="/versions", tags=["Version Intelligence"])

@router.get("/{document_id}/compare", response_model=VersionComparisonResult)
def compare_document_versions(
    document_id: int,
    new_version_id: Optional[int] = None,
    old_version_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    if not isinstance(new_version_id, int):
        versions = db.query(DocumentVersion).filter(DocumentVersion.document_id == document_id).order_by(DocumentVersion.created_at.desc()).all()
        if not versions:
            raise HTTPException(status_code=404, detail="No versions found for this document")
        new_version_id = versions[0].id
        if len(versions) > 1 and not isinstance(old_version_id, int):
            old_version_id = versions[1].id

    result = version_agent.compare_versions(
        db=db,
        new_version_id=new_version_id,
        old_version_id=old_version_id if isinstance(old_version_id, int) else None
    )
    return result

@router.get("/changes")
def list_policy_changes(
    document_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(PolicyChange)
    if isinstance(document_id, int):
        query = query.filter(PolicyChange.document_id == document_id)
    changes = query.order_by(PolicyChange.detected_at.desc()).limit(limit).all()

    return [{
        "id": c.id,
        "document_id": c.document_id,
        "old_version_id": c.old_version_id,
        "new_version_id": c.new_version_id,
        "change_type": c.change_type,
        "previous_content": c.previous_content,
        "updated_content": c.updated_content,
        "summary": c.summary,
        "detected_at": c.detected_at.isoformat()
    } for c in changes]

@router.get("/contradictions")
def list_contradictions(
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(PolicyContradiction)
    if isinstance(status, str) and status != "All" and status.strip():
        query = query.filter(PolicyContradiction.status == status.strip())

    contradictions = query.order_by(PolicyContradiction.detected_at.desc()).all()

    results = []
    for c in contradictions:
        v_a = db.query(DocumentVersion).filter(DocumentVersion.id == c.document_version_a_id).first()
        v_b = db.query(DocumentVersion).filter(DocumentVersion.id == c.document_version_b_id).first()

        res_data = None
        if c.resolution:
            res_data = {
                "decision": c.resolution.resolution_decision,
                "notes": c.resolution.administrative_notes,
                "resolved_at": c.resolution.resolved_at.isoformat()
            }

        results.append({
            "id": c.id,
            "document_a_title": v_a.document.title if (v_a and v_a.document) else "Circular A",
            "document_a_version": v_a.version_number if v_a else "v1.0",
            "clause_a": c.clause_a,
            "document_b_title": v_b.document.title if (v_b and v_b.document) else "Circular B",
            "document_b_version": v_b.version_number if v_b else "v2.0",
            "clause_b": c.clause_b,
            "description": c.description,
            "severity": c.severity,
            "status": c.status,
            "detected_at": c.detected_at,
            "resolution": res_data
        })
    return results

@router.post("/contradictions/{contradiction_id}/resolve")
def resolve_contradiction(
    contradiction_id: int,
    data: ResolveContradictionIn,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    contradiction = db.query(PolicyContradiction).filter(PolicyContradiction.id == contradiction_id).first()
    if not contradiction:
        raise HTTPException(status_code=404, detail="Contradiction record not found")

    resolution = ContradictionResolution(
        contradiction_id=contradiction.id,
        resolved_by_user_id=current_user.id,
        resolution_decision=data.resolution_decision,
        administrative_notes=data.administrative_notes
    )
    db.add(resolution)
    contradiction.status = "resolved"
    db.commit()

    return {
        "message": "Contradiction marked as resolved with administrative override.",
        "contradiction_id": contradiction.id,
        "decision": data.resolution_decision
    }
