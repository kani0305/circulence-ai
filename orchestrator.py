import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.agents.ingestion_agent import ingestion_agent
from app.agents.policy_agent import policy_agent
from app.agents.version_agent import version_agent
from app.agents.applicability_agent import applicability_agent
from app.agents.deadline_agent import deadline_agent
from app.agents.action_plan_agent import action_plan_agent
from app.models.models import User, Notification, AuditLog

logger = logging.getLogger("circulariq.orchestrator")

class MultiAgentOrchestrator:
    """
    Coordinates the 7 specialized AI agents across the end-to-end document lifecycle:
    Upload -> Ingestion -> Policy Understanding -> Deadline Extraction -> Version Comparison -> Applicability -> Action Plans.
    """

    def process_new_document_lifecycle(
        self,
        db: Session,
        file_path: str,
        original_filename: str,
        file_type: str,
        file_size: int,
        uploaded_by_user_id: Optional[int] = None,
        manual_version: Optional[str] = None
    ) -> Dict[str, Any]:
        logger.info(f"Starting Multi-Agent processing for {original_filename}...")

        # Step 1: Agent 1 (Ingestion)
        ingest_res = ingestion_agent.process_document(
            db=db,
            file_path=file_path,
            original_filename=original_filename,
            file_type=file_type,
            file_size=file_size,
            uploaded_by_user_id=uploaded_by_user_id,
            manual_version=manual_version
        )
        version_id = ingest_res["version_id"]
        doc_id = ingest_res["document_id"]
        pages_raw = ingest_res["pages_raw"]

        # Step 2: Agent 2 (Policy Understanding)
        policy_rec = policy_agent.analyze_document(
            db=db,
            version_id=version_id,
            pages_raw=pages_raw
        )

        # Step 3: Agent 6 (Deadline Extraction & Management)
        deadlines_extracted = deadline_agent.extract_and_sync_deadlines(
            db=db,
            version_id=version_id,
            pages_raw=pages_raw
        )

        # Step 4: Agent 3 (Version Comparison & Contradiction Detection)
        comparison_res = version_agent.compare_versions(
            db=db,
            new_version_id=version_id
        )

        # Step 5: Agent 4 (User Applicability Evaluation)
        users = db.query(User).filter(User.is_active == True).all()
        applicable_count = 0
        for user in users:
            app_res = applicability_agent.evaluate_applicability(
                db=db,
                user_id=user.id,
                version_id=version_id
            )
            if app_res["is_applicable"]:
                applicable_count += 1
                # Step 6: Agent 7 (Update Action Plan for applicable user)
                if user.role == "student":
                    action_plan_agent.generate_plan_for_user(
                        db=db,
                        user_id=user.id,
                        version_id=version_id
                    )

                # Send Notification
                notif_title = f"New Circular: {ingest_res['title']} ({ingest_res['version_number']})"
                if comparison_res.get("changed_deadlines"):
                    notif_title = f"Deadline Update: {ingest_res['title']}"

                notif = Notification(
                    user_id=user.id,
                    title=notif_title,
                    message=f"Circular '{ingest_res['title']}' applies to your profile. {len(deadlines_extracted)} deadlines detected.",
                    notification_type="new_circular" if not comparison_res.get("changed_deadlines") else "deadline_change",
                    related_document_id=doc_id,
                    is_read=False
                )
                db.add(notif)

        # Step 7: Log Audit Trail
        audit = AuditLog(
            user_id=uploaded_by_user_id,
            action="INGEST_AND_ANALYZE_CIRCULAR",
            entity_type="DocumentVersion",
            entity_id=str(version_id),
            details_json={
                "title": ingest_res["title"],
                "version": ingest_res["version_number"],
                "deadlines_count": len(deadlines_extracted),
                "applicable_users": applicable_count,
                "contradictions_found": len(comparison_res.get("contradictions", []))
            }
        )
        db.add(audit)
        db.commit()

        logger.info(f"Multi-Agent pipeline successfully finished for version {version_id}.")

        return {
            "ingestion": ingest_res,
            "policy": {
                "id": policy_rec.id,
                "target_audience": policy_rec.target_audience,
                "rules_count": len(policy_rec.rules)
            },
            "deadlines_count": len(deadlines_extracted),
            "version_comparison": comparison_res,
            "applicable_users_count": applicable_count
        }

orchestrator = MultiAgentOrchestrator()
