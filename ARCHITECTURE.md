# CircularIQ Architecture & Database Specification

CircularIQ treats institutional notices, circulars, and announcements as a structured, versioned, continuously verified rulebook.

---

## 1. Multi-Agent System Roles & Workflows

### Agent 1: Document Ingestion Agent (`app/agents/ingestion_agent.py`)
- Accepts PDF, DOCX, and TXT files.
- Extracts page-level text, titles, departments, reference numbers, and effective dates.
- Generates 384-dimensional dense semantic embeddings and stores chunks in ChromaDB.
- Persists document and version metadata in relational storage.

### Agent 2: Policy Understanding Agent (`app/agents/policy_agent.py`)
- Extracts discrete clauses, classifying them into `mandatory`, `guideline`, `eligibility`, `instruction`, or `penalty`.
- Identifies intended target audiences (e.g. `3rd Year`, `Computer Science`, `All Students`).
- Produces normalized JSON policy extractions.

### Agent 3: Version Comparison Agent (`app/agents/version_agent.py`)
- Performs structural and semantic diffs between a newly uploaded document and its predecessor.
- Categorizes changes into `added_rule`, `modified_rule`, `removed_rule`, and `changed_deadline`.
- Identifies quantitative and normative conflicts, flagging them into `policy_contradictions` with severity levels.

### Agent 4: User Applicability Agent (`app/agents/applicability_agent.py`)
- Compares student attributes (Department, Academic Year, Semester, Degree) against policy target audiences.
- Outputs boolean applicability with evidence strings (e.g., *"Verified Applicable: Department (Computer Science) and Year (3rd Year) match audience clause"*).
- When profile attributes are insufficient, returns `"Unclear – insufficient user information"`.

### Agent 5: RAG Question Answering Agent (`app/agents/rag_agent.py`)
- Performs hybrid semantic search and structured SQL lookup.
- Implements **As-of-Date temporal filtering**: excludes circulars published or enacted after the query date.
- Grounds answers exclusively in retrieved evidence; if insufficient evidence exists, returns *"Unclear – no verified source found"*.
- Returns verbatim citations with document titles, versions, page numbers, and similarity scores.

### Agent 6: Deadline Management Agent (`app/agents/deadline_agent.py`)
- Extracts dates, categories (examination, fee payment, registration, submission), and times.
- Detects extensions and cancellations.
- Background scheduler triggers reminders at **7 days, 3 days, 1 day, and 0 days** prior to verified deadlines.

### Agent 7: Action Plan Agent (`app/agents/action_plan_agent.py`)
- Synthesizes an individualized, prioritized compliance checklist for each student.
- Ranks tasks by urgency (`critical`, `high`, `medium`, `low`) linked to source clauses.
- Tracks user completion state and timestamps.

---

## 2. Relational Database Schema (21 Tables)

1. `users`: Authentication records, roles (`student`, `faculty`, `admin`).
2. `departments`: Institutional departments (`CSE`, `IT`, `ECE`, `MECH`, `ACAD`, etc.).
3. `user_profiles`: Academic metadata (roll number, year, semester, section, degree).
4. `documents`: Master circular entity with document reference number and category.
5. `document_versions`: Individual versions (`v1.0`, `v2.0`) with publication & effective dates.
6. `document_chunks`: Text chunks with page number tracking.
7. `extracted_policies`: Structured JSON extraction and target audience arrays.
8. `policy_rules`: Extracted clauses with rule types and page numbers.
9. `policy_changes`: Change logs (added, modified, removed rules, changed deadlines).
10. `policy_contradictions`: Conflicting clauses between two circular versions.
11. `contradiction_resolutions`: Registrar/Admin override decisions and notes.
12. `user_applicability`: User-to-circular applicability mapping with evidence reasoning.
13. `deadlines`: Extracted deadline milestones with category and verification status.
14. `action_plans`: User action plan containers.
15. `action_items`: Actionable tasks with priority and completion status.
16. `notifications`: Alert notifications (deadline reminders, new circulars, policy changes).
17. `chat_sessions`: Chat session threads with As-of-Date parameters.
18. `chat_messages`: Natural language chat history.
19. `source_references`: Verbatim document citations supporting AI responses.
20. `audit_logs`: Operational audit trail for administrative tracking.
21. `nexus_api_sync_logs`: External Nexus API synchronization logs.
