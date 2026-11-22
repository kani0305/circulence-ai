import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.models import Deadline, DocumentVersion, Document, User
from app.schemas.schemas import DeadlineOut, DeadlineCreate, DeadlineUpdate
from app.api.deps import get_current_user, require_faculty_or_admin
from app.agents.deadline_agent import deadline_agent

router = APIRouter(prefix="/deadlines", tags=["Deadline Management"])

@router.get("", response_model=List[DeadlineOut])
def list_deadlines(
    category: Optional[str] = None,
    status: Optional[str] = None, # upcoming, overdue, today, all
    db: Session = Depends(get_db)
):
    now = datetime.datetime.utcnow()
    query = db.query(Deadline).filter(Deadline.is_cancelled == False)

    if isinstance(category, str) and category != "All" and category.strip():
        query = query.filter(Deadline.category == category.strip())

    if status == "upcoming":
        query = query.filter(Deadline.deadline_date > now)
    elif status == "overdue":
        query = query.filter(Deadline.deadline_date < now)
    elif status == "today":
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        query = query.filter(Deadline.deadline_date >= start_of_day, Deadline.deadline_date <= end_of_day)

    deadlines = query.order_by(Deadline.deadline_date.asc()).all()

    results = []
    for dl in deadlines:
        v = dl.version
        doc = v.document if v else None
        
        diff = (dl.deadline_date - now).days
        urgency = "upcoming"
        if dl.deadline_date < now:
            urgency = "overdue"
        elif dl.deadline_date.date() == now.date():
            urgency = "today"

        results.append(DeadlineOut(
            id=dl.id,
            title=dl.title,
            description=dl.description,
            category=dl.category,
            deadline_date=dl.deadline_date,
            original_deadline_date=dl.original_deadline_date,
            is_extended=dl.is_extended,
            is_cancelled=dl.is_cancelled,
            is_verified=dl.is_verified,
            document_title=doc.title if doc else "Institutional Notice",
            document_version=v.version_number if v else "v1.0",
            document_id=doc.id if doc else 0,
            days_remaining=diff,
            urgency_status=urgency
        ))
    return results

@router.get("/upcoming", response_model=List[DeadlineOut])
def get_upcoming_deadlines(limit: int = 5, db: Session = Depends(get_db)):
    now = datetime.datetime.utcnow()
    deadlines = db.query(Deadline).filter(
        Deadline.is_cancelled == False,
        Deadline.deadline_date >= now - datetime.timedelta(hours=12)
    ).order_by(Deadline.deadline_date.asc()).limit(limit).all()

    results = []
    for dl in deadlines:
        v = dl.version
        doc = v.document if v else None
        diff = (dl.deadline_date - now).days
        urgency = "today" if dl.deadline_date.date() == now.date() else ("overdue" if dl.deadline_date < now else "upcoming")

        results.append(DeadlineOut(
            id=dl.id,
            title=dl.title,
            description=dl.description,
            category=dl.category,
            deadline_date=dl.deadline_date,
            original_deadline_date=dl.original_deadline_date,
            is_extended=dl.is_extended,
            is_cancelled=dl.is_cancelled,
            is_verified=dl.is_verified,
            document_title=doc.title if doc else "Notice",
            document_version=v.version_number if v else "v1.0",
            document_id=doc.id if doc else 0,
            days_remaining=diff,
            urgency_status=urgency
        ))
    return results

@router.post("", response_model=DeadlineOut)
def create_deadline(
    deadline_in: DeadlineCreate,
    current_user: User = Depends(require_faculty_or_admin),
    db: Session = Depends(get_db)
):
    dl = Deadline(
        document_version_id=deadline_in.document_version_id,
        title=deadline_in.title,
        description=deadline_in.description,
        category=deadline_in.category,
        deadline_date=deadline_in.deadline_date,
        is_verified=deadline_in.is_verified
    )
    db.add(dl)
    db.commit()
    db.refresh(dl)

    v = dl.version
    doc = v.document if v else None
    now = datetime.datetime.utcnow()
    diff = (dl.deadline_date - now).days

    return DeadlineOut(
        id=dl.id,
        title=dl.title,
        description=dl.description,
        category=dl.category,
        deadline_date=dl.deadline_date,
        original_deadline_date=dl.original_deadline_date,
        is_extended=dl.is_extended,
        is_cancelled=dl.is_cancelled,
        is_verified=dl.is_verified,
        document_title=doc.title if doc else "Notice",
        document_version=v.version_number if v else "v1.0",
        document_id=doc.id if doc else 0,
        days_remaining=diff,
        urgency_status="upcoming" if diff >= 0 else "overdue"
    )

@router.put("/{deadline_id}")
def update_deadline(
    deadline_id: int,
    data: DeadlineUpdate,
    current_user: User = Depends(require_faculty_or_admin),
    db: Session = Depends(get_db)
):
    dl = db.query(Deadline).filter(Deadline.id == deadline_id).first()
    if not dl:
        raise HTTPException(status_code=404, detail="Deadline not found")

    if data.deadline_date and data.deadline_date != dl.deadline_date:
        dl.original_deadline_date = dl.deadline_date
        dl.deadline_date = data.deadline_date
        dl.is_extended = True

    if data.title:
        dl.title = data.title
    if data.is_extended is not None:
        dl.is_extended = data.is_extended
    if data.is_cancelled is not None:
        dl.is_cancelled = data.is_cancelled
    if data.is_verified is not None:
        dl.is_verified = data.is_verified

    db.commit()
    return {"message": "Deadline updated successfully", "id": dl.id}

@router.post("/trigger-reminders")
def trigger_reminders(
    current_user: User = Depends(require_faculty_or_admin),
    db: Session = Depends(get_db)
):
    count = deadline_agent.generate_deadline_reminders(db)
    return {"message": f"Processed deadline reminders. {count} new notification(s) dispatched."}
