# Nexus Institutional API Integration Guide

CircularIQ connects to your institution's Nexus API to synchronize student profiles, academic departments, and enrollment status.

---

## 1. Principles of Integration

As instructed, CircularIQ treats the Nexus API with strict architectural care:
1. **Never Assume or Fabricate Endpoints**: CircularIQ does not invent fake endpoints or fabricate sample responses.
2. **Modular Service Interface**: `backend/app/services/nexus_service.py` defines `NexusApiClientInterface`, decoupling backend business logic from specific API payloads.
3. **Environment-Driven Security**: All API keys and tokens are stored in `.env` and never exposed to client-side code.
4. **Defensive Error Handling**: Network timeouts (8s), HTTP error codes, rate limits, and missing fields are caught gracefully and logged into `nexus_api_sync_logs`.

---

## 2. Configuration Parameters

In `.env`:

```env
# Nexus Base URL (e.g., provided by college IT administration)
NEXUS_API_BASE_URL=https://api.nexus.college.edu/v1

# Authentication: provide either API Key or Bearer Token as required
NEXUS_API_KEY=your_college_nexus_api_key
NEXUS_API_TOKEN=your_oauth_or_jwt_bearer_token
```

---

## 3. Supported Architecture & Adapters

```
[ Frontend: React UI ] 
        │
        ▼ (JWT authenticated)
[ Backend: FastAPI Router /api/nexus ]
        │
        ▼
[ NexusApiService (app/services/nexus_service.py) ]
        │
        ├── If Configured ───► HTTP GET {BASE_URL}/students/{id} ──► College Gateway
        │
        └── If Unconfigured ─► Returns Diagnostic Status ──► Defers gracefully
```

### Methods Provided by `nexus_service`:

- `check_connection(db)`: Tests reachability against `{NEXUS_API_BASE_URL}/health`. Logs result to `nexus_api_sync_logs`.
- `fetch_student_record(student_id, db)`: Retrieves live academic data (Department, Semester, Year) and maps fields into `UserProfile`.

---

## 4. How to Update for Custom College Specifications

When official Nexus documentation is provided by your college:
1. Open `backend/app/services/nexus_service.py`.
2. Update the URL path in `fetch_student_record()` (e.g. if the college endpoint is `/api/v2/student-directory/{id}` instead of `/students/{id}`).
3. Adjust the response field mapping in `sync_student_profile()` in `backend/app/api/nexus.py`.
4. Trigger a live sync from the **Nexus Integration Hub** page in the frontend.
