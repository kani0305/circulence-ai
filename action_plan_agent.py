import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.models import (
    User, DocumentVersion, PolicyRule, Deadline, 
    ActionPlan, ActionItem, UserApplicability
)

class ActionPlanAgent:
    """
    Agent 7: Action Plan Agent
    Responsibilities:
    - Synthesizes personalized, prioritized step-by-step action plans for users.
    - Connects each action directly to verified circular rules and deadline dates.
    - Orders steps by urgency (critical/high/medium) and due dates.
    - Tracks completion status with timestamps.
    """

    def generate_plan_for_user(
        self,
        db: Session,
        user_id: int,
        version_id: Optional[int] = None
    ) -> ActionPlan:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found.")

        # Determine target versions: either specific version or all applicable active versions
        if version_id:
            target_versions = [db.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()]
        else:
            applicable_recs = db.query(UserApplicability).filter(
                UserApplicability.user_id == user_id,
                UserApplicability.is_applicable == True
            ).all()
            version_ids = [rec.document_version_id for rec in applicable_recs]
            if not version_ids:
                # Fallback to current active versions
                target_versions = db.query(DocumentVersion).filter(DocumentVersion.status == "active").all()
            else:
                target_versions = db.query(DocumentVersion).filter(DocumentVersion.id.in_(version_ids)).all()

        target_versions = [v for v in target_versions if v is not None]

        # Create or update ActionPlan header
        plan_title = "Academic & Institutional Compliance Action Plan"
        if version_id and target_versions:
            plan_title = f"Action Plan: {target_versions[0].document.title if target_versions[0].document else 'Circular'}"

        existing_plan = db.query(ActionPlan).filter(
            ActionPlan.user_id == user_id,
            ActionPlan.status == "active"
        ).first()

        if not existing_plan:
            plan = ActionPlan(
                user_id=user_id,
                document_version_id=version_id,
                title=plan_title,
                description="Consolidated step-by-step tasks synthesized from verified institutional circulars.",
                status="active"
            )
            db.add(plan)
            db.flush()
        else:
            plan = existing_plan

        now = datetime.datetime.utcnow()
        new_items_count = 0

        for ver in target_versions:
            # 1. Generate items from Deadlines
            deadlines = db.query(Deadline).filter(
                Deadline.document_version_id == ver.id,
                Deadline.is_cancelled == False
            ).all()

            for dl in deadlines:
                # Check if item already exists
                item_title = f"Complete: {dl.title}"
                already_exists = db.query(ActionItem).filter(
                    ActionItem.action_plan_id == plan.id,
                    ActionItem.title == item_title
                ).first()

                if not already_exists:
                    # Urgency priority
                    days_diff = (dl.deadline_date - now).days
                    if days_diff < 0:
                        priority = "critical" # Overdue
                    elif days_diff <= 3:
                        priority = "critical"
                    elif days_diff <= 7:
                        priority = "high"
                    else:
                        priority = "medium"

                    item = ActionItem(
                        action_plan_id=plan.id,
                        user_id=user_id,
                        title=item_title,
                        description=f"{dl.description or dl.title}. Ensure submission prior to {dl.deadline_date.strftime('%d %b %Y, %I:%M %p')}.",
                        priority=priority,
                        due_date=dl.deadline_date,
                        is_completed=False,
                        supporting_evidence=f"Extracted from {ver.document.title if ver.document else 'Circular'} ({ver.version_number}), Category: {dl.category.title()}.",
                        page_number=1
                    )
                    db.add(item)
                    new_items_count += 1

            # 2. Generate items from Mandatory & Instruction Rules
            rules = db.query(PolicyRule).filter(
                PolicyRule.document_version_id == ver.id,
                PolicyRule.rule_type.in_(["mandatory", "instruction"])
            ).limit(4).all()

            for r in rules:
                rule_task_title = f"Action: {r.title}"
                already_exists = db.query(ActionItem).filter(
                    ActionItem.action_plan_id == plan.id,
                    ActionItem.title == rule_task_title
                ).first()

                if not already_exists:
                    item = ActionItem(
                        action_plan_id=plan.id,
                        user_id=user_id,
                        title=rule_task_title,
                        description=r.description,
                        priority="high" if r.rule_type == "mandatory" else "medium",
                        due_date=ver.effective_date or (now + datetime.timedelta(days=14)),
                        is_completed=False,
                        supporting_evidence=f"Institutional Rule '{r.clause_reference}' from {ver.document.title if ver.document else 'Policy'} ({ver.version_number}).",
                        page_number=r.page_number
                    )
                    db.add(item)
                    new_items_count += 1

        db.commit()
        db.refresh(plan)
        return plan

    def mark_item_completed(self, db: Session, item_id: int, user_id: int) -> ActionItem:
        item = db.query(ActionItem).filter(
            ActionItem.id == item_id,
            ActionItem.user_id == user_id
        ).first()

        if not item:
            raise ValueError("Action item not found.")

        item.is_completed = not item.is_completed
        item.completed_at = datetime.datetime.utcnow() if item.is_completed else None
        db.commit()
        db.refresh(item)
        return item

action_plan_agent = ActionPlanAgent()
