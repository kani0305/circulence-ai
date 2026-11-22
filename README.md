# CircularIQ
### A Multi-Agent RAG System for Versioned Policy Intelligence and Deadline Management

CircularIQ is an institutional policy intelligence and deadline orchestration platform. It transforms unstructured university circulars, examination notifications, placement guidelines, and administrative orders into a continuously evolving, version-controlled rulebook.

---

## Key Capabilities

- **Multi-Agent AI Pipeline**: Orchestrates 7 specialized agents (Ingestion, Policy Understanding, Version Comparison, Applicability, Grounded RAG, Deadline Management, and Action Plans).
- **Version Intelligence & Differential Analysis**: Automatically compares new document revisions against prior versions, flagging added clauses, modified rules, and extended deadlines (e.g. extension from 15 Nov to 20 Nov).
- **Contradiction Detection & Administrative Governance**: Identifies conflicting requirements across overlapping circulars, marks them as *Needs Review*, and provides an administrative resolution workflow.
- **Personalized Student Applicability**: Integrates student attributes (Department, Academic Year, Semester) to determine whether a policy applies, complete with evidence-based reasoning.
- **As-of-Date Temporal Policy Queries**: Ask natural language questions like *"What was the examination registration deadline as of 10 October 2026?"* and retrieve only the policy snapshot enacted on that date.
- **Strict Citation Grounding**: Answers are synthesized exclusively from verified institutional text, displaying Document Title, Version Number, Page Reference, and verbatim excerpts.
- **Automated Deadline Reminders**: Extracts deadlines across categories (exams, fee payment, registration) with automated 7-day, 3-day, and 1-day notification triggers.
- **Personalized Action Plans**: Automatically creates actionable checklists linked directly to governing clauses with real-time completion tracking.
- **Modular Nexus Gateway**: A secure, isolated integration interface for college Nexus APIs, respecting authentication keys, handling rate limits, and safely handling unconfigured states.

---

## Multi-Agent Architecture

```
                                  [ Uploaded Document (PDF/DOCX/TXT) ]
                                                   │
                                                   ▼
                                       ┌───────────────────────┐
                                       │ 1. Ingestion Agent    │
                                       │    (Parse & Chunk)    │
                                       └───────────┬───────────┘
                                                   │
                          ┌────────────────────────┼────────────────────────┐
                          ▼                        ▼                        ▼
              ┌───────────────────────┐┌───────────────────────┐┌───────────────────────┐
              │ 2. Policy Agent       ││ 6. Deadline Agent     ││ Vector Store (Chroma) │
              │ (Rules & Eligibility) ││ (Extract & Schedule)  ││ (384-dim Embeddings)  │
              └───────────┬───────────┘└───────────┬───────────┘└───────────────────────┘
                          │                        │
                          ▼                        ▼
              ┌───────────────────────┐┌───────────────────────┐
              │ 3. Version Comparison ││ 4. User Applicability │
              │ (Diff & Contradiction)││ (Profile Matching)    │
              └───────────┬───────────┘└───────────┬───────────┘
                          │                        │
                          └───────────┬────────────┘
                                      ▼
                          ┌───────────────────────┐
                          │ 7. Action Plan Agent  │
                          │ (Personalized Tasks)  │
                          └───────────────────────┘
                                      ▲
                                      │
              ┌───────────────────────┴───────────────────────┐
              │ 5. RAG Question Answering Agent               │
              │ (Historical As-of-Date Queries & Citations)   │
              └───────────────────────────────────────────────┘
```

---

## Technology Stack

- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS v4, Lucide React, Recharts, Axios, React Router v7.
- **Backend**: Python 3.10+, FastAPI, Pydantic v2, SQLAlchemy 2.0.
- **Database**: PostgreSQL-compatible schema with automatic SQLite fallback (`circulariq.db`), 21 normalized tables.
- **Vector DB**: ChromaDB with offline-first 384-dimensional dense semantic embeddings.
- **Document Processing**: PyMuPDF (`fitz`), `python-docx`.
- **Scheduler**: APScheduler for automated reminder computation.

---

## Quick Start Guide

### 1. Backend Setup

```bash
# Navigate to project root
cd "circular IQ"

# Install backend dependencies
pip install -r backend/requirements.txt

# Run database setup & sample knowledge ingestion
$env:PYTHONPATH="backend"
python backend/app/database/init_db.py

# Start FastAPI Server (Runs on http://localhost:8000)
uvicorn app.main:app --app-dir backend --reload --port 8000
```

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install frontend dependencies (if not already installed)
npm install

# Start Vite Development Server (Runs on http://localhost:5173)
npm run dev
```

Visit **http://localhost:5173** to launch the CircularIQ application.

---

## Pre-Seeded Demo Accounts

You can log in directly or use the **One-Click Demo Switcher** in the top navigation bar:

| Role | Name | Email | Password | Academic Attributes |
| :--- | :--- | :--- | :--- | :--- |
| **Student** | Rohan Verma | `student@college.edu` | `Student@1234` | 3rd Year, Computer Science, Sem 5, Roll: 2024CS101 |
| **Faculty** | Prof. Anita Sharma | `faculty@college.edu` | `Faculty@1234` | Head of Department, Computer Science |
| **Admin** | Dr. S. Ramanathan | `admin@college.edu` | `Admin@1234` | Registrar & Controller of Examinations |

---

## Running the Automated Test Suite

CircularIQ includes a test suite covering agent logic, embeddings, version differential tracking, RAG citations, and API endpoints:

```bash
$env:PYTHONPATH="backend"
pytest backend/tests -v
```
*(All 13 automated tests pass with 100% success rate)*

---

## Nexus Institutional API Integration

The Nexus API integration is located in `backend/app/services/nexus_service.py` and adheres to your environment variables:

```env
NEXUS_API_BASE_URL=https://api.nexus.college.edu/v1
NEXUS_API_KEY=your_nexus_api_key
NEXUS_API_TOKEN=your_bearer_token
```

When credentials are unset, CircularIQ safely defaults to defensive mock diagnostic mode without failing or fabricating unsupported endpoints. Once your college provides live credentials, simply update `.env` to enable real-time institutional profile sync. See `documentation/NEXUS_INTEGRATION_GUIDE.md` for full specifications.
