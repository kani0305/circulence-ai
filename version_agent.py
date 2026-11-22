import difflib
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.models import (
    Document, DocumentVersion, PolicyRule, Deadline, 
    PolicyChange, PolicyContradiction
)

class VersionComparisonAgent:
    """
    Agent 3: Version Comparison Agent
    Responsibilities:
    - Compares new circular version against preceding version.
    - Detects added, modified, and removed rules.
    - Detects changed deadlines (e.g. extension from 15 Nov to 20 Nov).
    - Detects contradictory clauses and logs them as 'needs_review'.
    - Generates human-readable diff reports with previous content, updated content,
      version number, and publication dates.
    """

    def compare_versions(
        self,
        db: Session,
        new_version_id: int,
        old_version_id: Optional[int] = None
    ) -> Dict[str, Any]:
        new_v = db.query(DocumentVersion).filter(DocumentVersion.id == new_version_id).first()
        if not new_v:
            raise ValueError(f"New version {new_version_id} not found.")

        # If old_version_id is not specified, find previous version of the same document
        if not old_version_id:
            old_v = db.query(DocumentVersion).filter(
                DocumentVersion.document_id == new_v.document_id,
                DocumentVersion.id != new_v.id,
                DocumentVersion.created_at < new_v.created_at
            ).order_by(DocumentVersion.created_at.desc()).first()
        else:
            old_v = db.query(DocumentVersion).filter(DocumentVersion.id == old_version_id).first()

        if not old_v:
            # Baseline version (v1.0)
            return {
                "document_id": new_v.document_id,
                "document_title": new_v.document.title if new_v.document else "Circular",
                "old_version": "None (Initial Ingestion)",
                "new_version": new_v.version_number,
                "added_rules": [],
                "modified_rules": [],
                "removed_rules": [],
                "changed_deadlines": [],
                "contradictions": [],
                "affected_user_groups": new_v.extracted_policy.target_audience if new_v.extracted_policy else ["All Students"],
                "human_readable_report": f"Initial version {new_v.version_number} established as the baseline policy rulebook."
            }

        old_rules = db.query(PolicyRule).filter(PolicyRule.document_version_id == old_v.id).all()
        new_rules = db.query(PolicyRule).filter(PolicyRule.document_version_id == new_v.id).all()

        added_rules = []
        modified_rules = []
        removed_rules = []
        contradictions = []

        # Map rules by similarity
        old_descriptions = [r.description for r in old_rules]
        new_descriptions = [r.description for r in new_rules]

        matched_old_indices = set()

        for new_r in new_rules:
            # Check close match in old rules
            matches = difflib.get_close_matches(new_r.description, old_descriptions, n=1, cutoff=0.55)
            if matches:
                matched_old_text = matches[0]
                matched_idx = old_descriptions.index(matched_old_text)
                matched_old_indices.add(matched_idx)
                old_r = old_rules[matched_idx]

                if difflib.SequenceMatcher(None, new_r.description, matched_old_text).ratio() < 0.95:
                    # Modified rule detected!
                    mod_entry = {
                        "change_type": "modified_rule",
                        "title": new_r.title,
                        "old_text": matched_old_text,
                        "new_text": new_r.description,
                        "page_number": new_r.page_number,
                        "clause": new_r.clause_reference
                    }
                    modified_rules.append(mod_entry)

                    # Check for direct contradictions (e.g. strict requirement inverted or attendance % changed)
                    if any(num in new_r.description for num in ["%", "percent", "CGPA", "fee", "Rs"]) and any(num in matched_old_text for num in ["%", "percent", "CGPA", "fee", "Rs"]):
                        # Numerical policy variance!
                        contradiction = PolicyContradiction(
                            document_version_a_id=old_v.id,
                            document_version_b_id=new_v.id,
                            clause_a=matched_old_text,
                            clause_b=new_r.description,
                            description=f"Variance detected between {old_v.version_number} and {new_v.version_number} regarding rule '{new_r.title}'.",
                            severity="high",
                            status="needs_review"
                        )
                        db.add(contradiction)
                        contradictions.append({
                            "clause_a": matched_old_text,
                            "clause_b": new_r.description,
                            "severity": "high",
                            "status": "needs_review"
                        })

                    # Log change to database
                    change_rec = PolicyChange(
                        document_id=new_v.document_id,
                        old_version_id=old_v.id,
                        new_version_id=new_v.id,
                        change_type="modified_rule",
                        previous_content=matched_old_text,
                        updated_content=new_r.description,
                        summary=f"Rule '{new_r.title}' updated from earlier version {old_v.version_number} to {new_v.version_number}."
                    )
                    db.add(change_rec)
            else:
                # Newly added rule
                add_entry = {
                    "change_type": "added_rule",
                    "title": new_r.title,
                    "description": new_r.description,
                    "page_number": new_r.page_number
                }
                added_rules.append(add_entry)
                change_rec = PolicyChange(
                    document_id=new_v.document_id,
                    old_version_id=old_v.id,
                    new_version_id=new_v.id,
                    change_type="added_rule",
                    previous_content=None,
                    updated_content=new_r.description,
                    summary=f"New rule '{new_r.title}' introduced in {new_v.version_number}."
                )
                db.add(change_rec)

        # Removed rules
        for idx, old_r in enumerate(old_rules):
            if idx not in matched_old_indices:
                rem_entry = {
                    "change_type": "removed_rule",
                    "title": old_r.title,
                    "description": old_r.description,
                    "page_number": old_r.page_number
                }
                removed_rules.append(rem_entry)
                change_rec = PolicyChange(
                    document_id=new_v.document_id,
                    old_version_id=old_v.id,
                    new_version_id=new_v.id,
                    change_type="removed_rule",
                    previous_content=old_r.description,
                    updated_content=None,
                    summary=f"Rule '{old_r.title}' from {old_v.version_number} is no longer present in {new_v.version_number}."
                )
                db.add(change_rec)

        # Deadline Comparison
        changed_deadlines = []
        old_deadlines = db.query(Deadline).filter(Deadline.document_version_id == old_v.id).all()
        new_deadlines = db.query(Deadline).filter(Deadline.document_version_id == new_v.id).all()

        for new_dl in new_deadlines:
            # Check match by title/category
            matched_old_dl = next((od for od in old_deadlines if difflib.SequenceMatcher(None, od.title.lower(), new_dl.title.lower()).ratio() > 0.6), None)
            if matched_old_dl:
                if matched_old_dl.deadline_date != new_dl.deadline_date:
                    is_ext = new_dl.deadline_date > matched_old_dl.deadline_date
                    new_dl.is_extended = is_ext
                    new_dl.original_deadline_date = matched_old_dl.deadline_date

                    dl_change = {
                        "title": new_dl.title,
                        "old_date": matched_old_dl.deadline_date.strftime("%d %b %Y, %I:%M %p"),
                        "new_date": new_dl.deadline_date.strftime("%d %b %Y, %I:%M %p"),
                        "is_extended": is_ext,
                        "category": new_dl.category
                    }
                    changed_deadlines.append(dl_change)

                    change_rec = PolicyChange(
                        document_id=new_v.document_id,
                        old_version_id=old_v.id,
                        new_version_id=new_v.id,
                        change_type="changed_deadline",
                        previous_content=f"Deadline: {matched_old_dl.deadline_date.isoformat()}",
                        updated_content=f"Deadline: {new_dl.deadline_date.isoformat()} (Extended: {is_ext})",
                        summary=f"Deadline for '{new_dl.title}' changed from {dl_change['old_date']} to {dl_change['new_date']}."
                    )
                    db.add(change_rec)

        db.commit()

        # Generate human-readable summary
        report_lines = [
            f"### Version Comparison: {new_v.document.title if new_v.document else 'Circular'}",
            f"- **Prior Version:** {old_v.version_number} (Published: {old_v.publication_date})",
            f"- **New Version:** {new_v.version_number} (Published: {new_v.publication_date})",
            f"- **Added Rules:** {len(added_rules)}",
            f"- **Modified Rules:** {len(modified_rules)}",
            f"- **Removed Rules:** {len(removed_rules)}",
            f"- **Deadline Adjustments:** {len(changed_deadlines)}",
            f"- **Flagged Contradictions:** {len(contradictions)}"
        ]

        if changed_deadlines:
            report_lines.append("\n**Key Deadline Updates:**")
            for cd in changed_deadlines:
                status_badge = "EXTENDED" if cd["is_extended"] else "RESCHEDULED"
                report_lines.append(f"- [{status_badge}] **{cd['title']}**: Changed from `{cd['old_date']}` to `{cd['new_date']}`")

        target_audiences = new_v.extracted_policy.target_audience if new_v.extracted_policy else ["All Students"]

        return {
            "document_id": new_v.document_id,
            "document_title": new_v.document.title if new_v.document else "Circular",
            "old_version": old_v.version_number,
            "new_version": new_v.version_number,
            "old_publication_date": old_v.publication_date.isoformat() if old_v.publication_date else None,
            "new_publication_date": new_v.publication_date.isoformat() if new_v.publication_date else None,
            "added_rules": added_rules,
            "modified_rules": modified_rules,
            "removed_rules": removed_rules,
            "changed_deadlines": changed_deadlines,
            "contradictions": contradictions,
            "affected_user_groups": target_audiences,
            "human_readable_report": "\n".join(report_lines)
        }

version_agent = VersionComparisonAgent()
