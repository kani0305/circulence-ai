from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.core.security import verify_password, get_password_hash, create_access_token
from app.models.models import User, UserProfile, Department
from app.schemas.schemas import Token, UserLogin, UserCreate, UserOut
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=Token)
def login(login_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email.lower()).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account is disabled")

    access_token = create_access_token(subject=user.id, role=user.role)
    return Token(
        access_token=access_token,
        token_type="bearer",
        role=user.role,
        user_id=user.id,
        full_name=user.full_name,
        email=user.email
    )

@router.post("/register", response_model=UserOut)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user_in.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    dept = None
    if user_in.department_code:
        dept = db.query(Department).filter(Department.code == user_in.department_code.upper()).first()

    new_user = User(
        email=user_in.email.lower(),
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role.lower(),
        is_active=True
    )
    db.add(new_user)
    db.flush()

    # Create associated profile
    profile = UserProfile(
        user_id=new_user.id,
        department_id=dept.id if dept else None,
        roll_number=user_in.roll_number,
        academic_year=user_in.academic_year,
        semester=user_in.semester,
        degree_program=user_in.degree_program or ("B.Tech Computer Science" if user_in.role == "student" else None)
    )
    db.add(profile)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    profile = current_user.profile
    dept_name = profile.department.name if (profile and profile.department) else None
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "profile": {
            "id": profile.id if profile else None,
            "roll_number": profile.roll_number if profile else None,
            "academic_year": profile.academic_year if profile else None,
            "semester": profile.semester if profile else None,
            "section": profile.section if profile else None,
            "degree_program": profile.degree_program if profile else None,
            "nexus_student_id": profile.nexus_student_id if profile else None,
            "nexus_sync_status": profile.nexus_sync_status if profile else "not_synced",
            "department_name": dept_name
        } if profile else None
    }

@router.post("/logout")
def logout():
    return {"message": "Logged out successfully"}
