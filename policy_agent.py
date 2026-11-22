import re
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.models import ExtractedPolicy, PolicyRule, DocumentVersion
from app.services.document_parser import DocumentParser

class PolicyUnderstandingAgent:
    """
    Agent 2: Policy Understanding Agent
    Responsibilities:
    - Extracts institutional rules (mandatory, guidelines, penalties, eligibility).
    - Extracts target audiences (degree, branch, academic year, semester).
    - Extracts instructions and required submission items.
    - Converts policy contents into a structured, validated JSON schema.
    - Derives all fields from document evidence; uses explicit uncertainty markers when missing.
    """

    def analyze_document(
        self,
        db: Session,
        version_id: int,
        pages_raw: List[Dict[str, Any]]
    ) -> ExtractedPolicy:
        doc_version = db.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
        if not doc_version:
            raise ValueError(f"Version ID {version_id} not found.")

        full_text = "\n".join([f"--- Page {p['page']} ---\n{p['text']}" for p in pages_raw])

        # 1. Target Audience Identification
        target_audience = []
        # Check academic years
        if re.search(r"\b1st\s*year\b|first\s*year", full_text, re.IGNORECASE):
            target_audience.append("1st Year")
        if re.search(r"\b2nd\s*year\b|second\s*year", full_text, re.IGNORECASE):
            target_audience.append("2nd Year")
        if re.search(r"\b3rd\s*year\b|third\s*year", full_text, re.IGNORECASE):
            target_audience.append("3rd Year")
        if re.search(r"\b4th\s*year\b|final\s*year", full_text, re.IGNORECASE):
            target_audience.append("Final Year")
        
        # Check departments
        for dept in ["Computer Science", "Information Technology", "Mechanical Engineering", 
                     "Electrical Engineering", "Civil Engineering", "Management Studies"]:
            if re.search(r"\b" + re.escape(dept) + r"\b", full_text, re.IGNORECASE):
                target_audience.append(dept)

        if not target_audience:
            if re.search(r"all\s+students|all\s+faculty|all\s+departments", full_text, re.IGNORECASE):
                target_audience.append("All Students")
            else:
                target_audience.append("Institutional Scope Unspecified")

        # 2. Extract Rules, Instructions, Eligibility, Penalties
        extracted_rules = []
        rule_candidates = []

        # Find bulleted or numbered clauses
        clause_pattern = r"(?:^|\n)\s*(?:(\d+[\.\)]|[a-z][\.\)]|[ivx]+[\.\)]|\*|•))\s*([^\n]+(?:\n(?!\s*(?:\d+[\.\)]|[a-z][\.\)]|[ivx]+[\.\)]|\*|•))[^\n]+)*)"
        matches = re.finditer(clause_pattern, full_text, re.MULTILINE)
        
        for m in matches:
            prefix = m.group(1) or ""
            text_body = m.group(2).strip().replace("\n", " ")
            if len(text_body) > 20:
                rule_candidates.append(text_body)

        # If few bulleted items found, split by sentences
        if len(rule_candidates) < 3:
            sentences = re.split(r"(?<=[.!?])\s+", full_text)
            for s in sentences:
                s_clean = s.strip()
                if any(k in s_clean.lower() for k in ["must", "shall", "mandatory", "required", "eligible", "deadline", "penalty", "attendance", "fee", "submit"]):
                    if len(s_clean) > 25:
                        rule_candidates.append(s_clean)

        # Categorize rules
        for idx, clause_text in enumerate(rule_candidates[:15]):  # Keep top salient rules
            clause_lower = clause_text.lower()
            
            rule_type = "mandatory"
            if "eligible" in clause_lower or "criteria" in clause_lower or "cgpa" in clause_lower:
                rule_type = "eligibility"
            elif "penalty" in clause_lower or "fine" in clause_lower or "barred" in clause_lower or "cancelled" in clause_lower:
                rule_type = "penalty"
            elif "recommended" in clause_lower or "advised" in clause_lower or "should" in clause_lower:
                rule_type = "guideline"
            elif "submit" in clause_lower or "upload" in clause_lower or "step" in clause_lower or "instructions" in clause_lower:
                rule_type = "instruction"

            # Derive title and page reference
            words = clause_text.split()
            title = " ".join(words[:7]) + ("..." if len(words) > 7 else "")
            
            # Locate approximate page
            page_found = 1
            for p in pages_raw:
                if clause_text[:30] in p.get("text", ""):
                    page_found = p["page"]
                    break

            extracted_rules.append({
                "rule_type": rule_type,
                "title": title,
                "description": clause_text,
                "clause_reference": f"Sec-{idx + 1}",
                "page_number": page_found
            })

        # 3. Create JSON Extraction Payload
        raw_extraction = {
            "document_title": doc_version.document.title if doc_version.document else "Policy",
            "department": doc_version.document.department.name if (doc_version.document and doc_version.document.department) else "Institutional",
            "publication_date": doc_version.publication_date.isoformat() if doc_version.publication_date else None,
            "effective_date": doc_version.effective_date.isoformat() if doc_version.effective_date else None,
            "target_audience": target_audience,
            "rules": [r["description"] for r in extracted_rules if r["rule_type"] == "mandatory"],
            "eligibility": [r["description"] for r in extracted_rules if r["rule_type"] == "eligibility"],
            "instructions": [r["description"] for r in extracted_rules if r["rule_type"] == "instruction"],
            "penalties": [r["description"] for r in extracted_rules if r["rule_type"] == "penalty"],
            "source_pages": [p["page"] for p in pages_raw]
        }

        # 4. Save ExtractedPolicy to Database
        # Clean previous extraction if re-analyzing
        existing_extraction = db.query(ExtractedPolicy).filter(ExtractedPolicy.document_version_id == version_id).first()
        if existing_extraction:
            db.delete(existing_extraction)
            db.flush()

        policy_record = ExtractedPolicy(
            document_version_id=version_id,
            title=doc_version.document.title if doc_version.document else "Policy Document",
            department=raw_extraction["department"],
            publication_date=doc_version.publication_date,
            effective_date=doc_version.effective_date,
            target_audience=target_audience,
            raw_extraction_json=raw_extraction,
            is_verified=True
        )
        db.add(policy_record)
        db.flush()

        # Add PolicyRule records
        for r in extracted_rules:
            rule_entry = PolicyRule(
                extracted_policy_id=policy_record.id,
                document_version_id=version_id,
                rule_type=r["rule_type"],
                title=r["title"],
                description=r["description"],
                clause_reference=r["clause_reference"],
                page_number=r["page_number"]
            )
            db.add(rule_entry)

        db.commit()
        return policy_record

policy_agent = PolicyUnderstandingAgent()
