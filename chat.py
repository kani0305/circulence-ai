from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.models import ChatSession, ChatMessage, User
from app.schemas.schemas import ChatQueryRequest, ChatMessageOut, ChatSessionOut
from app.agents.rag_agent import rag_agent
from app.api.deps import get_current_user

router = APIRouter(prefix="/chat", tags=["AI Policy Assistant"])

@router.post("", response_model=ChatMessageOut)
def query_ai_assistant(
    request: ChatQueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    result = rag_agent.answer_query(
        db=db,
        user_id=current_user.id,
        query=request.query,
        session_id=request.session_id,
        as_of_date=request.as_of_date,
        department_filter=request.department_filter,
        category_filter=request.category_filter
    )
    return result

@router.post("/as-of-date", response_model=ChatMessageOut)
def query_as_of_date(
    request: ChatQueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not request.as_of_date:
        raise HTTPException(status_code=400, detail="as_of_date must be provided for historical queries")
    
    result = rag_agent.answer_query(
        db=db,
        user_id=current_user.id,
        query=request.query,
        session_id=request.session_id,
        as_of_date=request.as_of_date,
        department_filter=request.department_filter,
        category_filter=request.category_filter
    )
    return result

@router.get("/sessions")
def list_chat_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    sessions = db.query(ChatSession).filter(
        ChatSession.user_id == current_user.id
    ).order_by(ChatSession.updated_at.desc()).all()

    return [{
        "id": s.id,
        "title": s.title,
        "as_of_date": s.as_of_date.isoformat() if s.as_of_date else None,
        "created_at": s.created_at.isoformat(),
        "messages_count": len(s.messages)
    } for s in sessions]

@router.get("/sessions/{session_id}")
def get_session_history(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    messages = []
    for m in session.messages:
        citations = [{
            "document_title": c.document_title,
            "version_number": c.version_number,
            "page_number": c.page_number,
            "excerpt": c.excerpt,
            "publication_date": c.publication_date.isoformat() if c.publication_date else None,
            "effective_date": c.effective_date.isoformat() if c.effective_date else None,
            "relevance_score": c.relevance_score
        } for c in m.citations]

        messages.append({
            "id": m.id,
            "sender": m.sender,
            "content": m.content,
            "is_uncertain": m.is_uncertain,
            "confidence_score": m.confidence_score,
            "created_at": m.created_at,
            "citations": citations
        })

    return {
        "id": session.id,
        "title": session.title,
        "as_of_date": session.as_of_date.isoformat() if session.as_of_date else None,
        "messages": messages
    }
