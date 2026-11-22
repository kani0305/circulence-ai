from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.models import User, UserProfile, NexusApiSyncLog
from app.schemas.schemas import NexusConnectionStatus
from app.services.nexus_service import nexus_service
from app.api.deps import get_current_user, require_admin

router = APIRouter(prefix="/nexus", tags=["Nexus Integration"])

@router.get("/connection-status", response_model=NexusConnectionStatus)
async def get_nexus_status(db: Session = Depends(get_db)):
    """
    Checks real Nexus API reachability and credentials.
    Adheres strictly to actual configuration. Never invents fake endpoints.
    """
    status_info = await nexus_service.check_connection(db=db)
    return NexusConnectionStatus(**status_info)

@router.post("/sync-profile")
async def sync_student_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile = current_user.profile
    if not profile:
        raise HTTPException(status_code=400, detail="User has no profile record to sync.")

    student_id = profile.nexus_student_id or profile.roll_number
    if not student_id:
        raise HTTPException(
            status_code=400, 
            detail="User does not have an associated Roll Number or Nexus Student ID."
        )

    # Attempt fetch through modular Nexus client
    record = await nexus_service.fetch_student_record(student_id=student_id, db=db)
    if not record:
        profile.nexus_sync_status = "unconfigured_or_unreachable"
        db.commit()
        return {
            "status": "deferred",
            "message": (
                "Nexus live sync deferred: Official Nexus API credentials or endpoints are pending configuration. "
                "Current internal student profile remains active."
            ),
            "profile_synced": False
        }

    # Map actual response fields defensively
    if "department" in record and current_user.profile.department:
        profile.department.name = record["department"]
    if "semester" in record:
        profile.semester = record["semester"]
    if "academic_year" in record:
        profile.academic_year = record["academic_year"]

    profile.nexus_sync_status = "synced"
    db.commit()

    return {
        "status": "success",
        "message": f"Successfully synchronized profile for student {student_id}.",
        "profile_synced": True
    }

@router.get("/logs")
def get_nexus_sync_logs(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    logs = db.query(NexusApiSyncLog).order_by(NexusApiSyncLog.timestamp.desc()).limit(limit).all()
    return [{
        "id": l.id,
        "sync_type": l.sync_type,
        "status": l.status,
        "records_synced": l.records_synced,
        "error_message": l.error_message,
        "request_url": l.request_url,
        "response_status_code": l.response_status_code,
        "timestamp": l.timestamp.isoformat()
    } for l in logs]
