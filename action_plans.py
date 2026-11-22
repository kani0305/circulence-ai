from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.models import ActionPlan, ActionItem, User
from app.schemas.schemas import ActionPlanOut, ActionItemOut
from app.agents.action_plan_agent import action_plan_agent
from app.api.deps import get_current_user

router = APIRouter(prefix="/action-plans", tags=["Personalized Action Plans"])

@router.get("", response_model=Optional[ActionPlanOut])
def get_user_action_plan(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    plan = db.query(ActionPlan).filter(
        ActionPlan.user_id == current_user.id,
        ActionPlan.status == "active"
    ).first()

    if not plan:
        # Generate on first visit
        plan = action_plan_agent.generate_plan_for_user(db, current_user.id)

    # Sort items: incomplete first, then by priority
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_items = sorted(
        plan.items,
        key=lambda x: (x.is_completed, priority_order.get(x.priority, 2))
    )

    return ActionPlanOut(
        id=plan.id,
        title=plan.title,
        description=plan.description,
        status=plan.status,
        generated_at=plan.generated_at,
        items=[ActionItemOut.from_orm(it) for it in sorted_items]
    )

@router.post("/generate", response_model=ActionPlanOut)
def regenerate_action_plan(
    version_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    plan = action_plan_agent.generate_plan_for_user(
        db=db,
        user_id=current_user.id,
        version_id=version_id
    )
    return ActionPlanOut(
        id=plan.id,
        title=plan.title,
        description=plan.description,
        status=plan.status,
        generated_at=plan.generated_at,
        items=[ActionItemOut.from_orm(it) for it in plan.items]
    )

@router.put("/items/{item_id}/toggle")
def toggle_action_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    item = action_plan_agent.mark_item_completed(db, item_id, current_user.id)
    return {
        "id": item.id,
        "is_completed": item.is_completed,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None
    }
