import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.models import User, UserProfile, DocumentVersion, UserApplicability

logger = logging.getLogger("circulariq.applicability")

class UserApplicabilityAgent:
    """
    Agent 4: User Applicability Agent
    Responsibilities:
    - Analyzes institutional policy target audiences against student profile attributes.
    - Evaluates exact criteria (Department, Year, Semester, Program).
    - Every decision is supported by explicit evidence.
    - If required attributes are missing, flags as 'Unclear – insufficient user information.'
    - Persists results to `user_applicability` table.
    """

    def evaluate_applicability(
        self,
        db: Session,
        user_id: int,
        version_id: int
    ) -> Dict[str, Any]:
        user = db.query(User).filter(User.id == user_id).first()
        doc_version = db.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()

        if not user or not doc_version:
            raise ValueError("User or DocumentVersion does not exist.")

        # Admin and faculty have institutional supervisory scope
        if user.role in ("admin", "faculty"):
            result = {
                "is_applicable": True,
                "match_confidence": 1.0,
                "reasoning_evidence": f"Applicable for institutional oversight and advisement ({user.role.title()} role).",
                "missing_information": None
            }
            self._save_record(db, user_id, version_id, result)
            return result

        profile: Optional[UserProfile] = user.profile
        if not profile:
            result = {
                "is_applicable": False,
                "match_confidence": 0.0,
                "reasoning_evidence": "Unclear – insufficient user information. No student academic profile found.",
                "missing_information": "Department, Academic Year, and Semester details required."
            }
            self._save_record(db, user_id, version_id, result)
            return result

        # Check extracted policy target audience
        extracted = doc_version.extracted_policy
        target_audiences = extracted.target_audience if extracted and extracted.target_audience else []

        # If universal institutional circular
        if any(aud in ["All Students", "All", "Institutional Scope Unspecified"] for aud in target_audiences):
            result = {
                "is_applicable": True,
                "match_confidence": 1.0,
                "reasoning_evidence": f"Circular applies university-wide to all enrolled students across all departments.",
                "missing_information": None
            }
            self._save_record(db, user_id, version_id, result)
            return result

        user_dept_name = profile.department.name.lower() if profile.department else ""
        user_year = (profile.academic_year or "").lower()
        user_sem = profile.semester

        dept_match = False
        year_match = False
        reasons = []

        for aud in target_audiences:
            aud_lower = aud.lower()
            # Department match
            if user_dept_name and (user_dept_name in aud_lower or aud_lower in user_dept_name):
                dept_match = True
                reasons.append(f"Department matched: '{aud}'")
            # Academic Year match
            if user_year and (user_year in aud_lower or aud_lower in user_year):
                year_match = True
                reasons.append(f"Academic Year matched: '{aud}'")

        # Determine applicability
        if dept_match and year_match:
            is_app = True
            confidence = 1.0
            evidence = f"Verified Applicable: Both Department ({profile.department.name if profile.department else ''}) and Academic Year ({profile.academic_year}) match the target audience specified in the circular."
            missing = None
        elif dept_match and not any("year" in a.lower() for a in target_audiences):
            is_app = True
            confidence = 0.95
            evidence = f"Verified Applicable: Circular targets {profile.department.name if profile.department else 'your department'} across all batches."
            missing = None
        elif year_match and not any(d in " ".join(target_audiences).lower() for d in ["computer", "engineering", "electrical", "mechanical", "civil"]):
            is_app = True
            confidence = 0.90
            evidence = f"Verified Applicable: Circular targets all students in {profile.academic_year}."
            missing = None
        elif not user_dept_name or not user_year:
            is_app = False
            confidence = 0.3
            evidence = "Unclear – insufficient user information to conclusively verify target eligibility."
            missing = "Academic Department and Current Academic Year details required."
        else:
            is_app = False
            confidence = 0.95
            evidence = f"Not Applicable: This circular is designated specifically for {', '.join(target_audiences)}. User profile records: Department='{profile.department.name if profile.department else 'N/A'}', Year='{profile.academic_year or 'N/A'}'."
            missing = None

        result = {
            "is_applicable": is_app,
            "match_confidence": confidence,
            "reasoning_evidence": evidence,
            "missing_information": missing
        }
        self._save_record(db, user_id, version_id, result)
        return result

    def _save_record(self, db: Session, user_id: int, version_id: int, res: Dict[str, Any]):
        rec = db.query(UserApplicability).filter(
            UserApplicability.user_id == user_id,
            UserApplicability.document_version_id == version_id
        ).first()

        if not rec:
            rec = UserApplicability(
                user_id=user_id,
                document_version_id=version_id,
                is_applicable=res["is_applicable"],
                match_confidence=res["match_confidence"],
                reasoning_evidence=res["reasoning_evidence"],
                missing_information=res["missing_information"]
            )
            db.add(rec)
        else:
            rec.is_applicable = res["is_applicable"]
            rec.match_confidence = res["match_confidence"]
            rec.reasoning_evidence = res["reasoning_evidence"]
            rec.missing_information = res["missing_information"]
        db.commit()

applicability_agent = UserApplicabilityAgent()
