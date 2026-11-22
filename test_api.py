import pytest
import datetime
from app.database.session import SessionLocal
from app.api.auth import login
from app.api.documents import list_documents, get_document_details
from app.api.deadlines import list_deadlines, get_upcoming_deadlines
from app.api.versions import compare_document_versions, list_policy_changes, list_contradictions
from app.api.chat import query_ai_assistant
from app.api.admin import get_dashboard_statistics
from app.schemas.schemas import UserLogin, ChatQueryRequest
from app.models.models import User

@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()

def test_login_endpoint(db):
    res = login(UserLogin(email="student@college.edu", password="Student@1234"), db=db)
    assert res.role == "student"
    assert res.access_token is not None

def test_documents_endpoint(db):
    docs = list_documents(db=db)
    assert len(docs) > 0
    first_doc = docs[0]
    detail = get_document_details(document_id=first_doc.id, db=db)
    assert "document" in detail
    assert "versions" in detail
    assert "rules" in detail

def test_deadlines_endpoint(db):
    dls = list_deadlines(db=db)
    assert len(dls) > 0
    upcoming = get_upcoming_deadlines(limit=3, db=db)
    assert len(upcoming) > 0

def test_version_compare_endpoint(db):
    docs = list_documents(db=db)
    # Find a document with multiple versions
    multi_v_doc = next((d for d in docs if d.version_count > 1), docs[0])
    comp = compare_document_versions(document_id=multi_v_doc.id, db=db)
    assert comp["document_id"] == multi_v_doc.id
    assert "human_readable_report" in comp

def test_policy_changes_endpoint(db):
    changes = list_policy_changes(db=db)
    assert isinstance(changes, list)

def test_contradictions_endpoint(db):
    conts = list_contradictions(db=db)
    assert isinstance(conts, list)

def test_dashboard_stats_endpoint(db):
    admin_user = db.query(User).filter(User.role == "admin").first()
    stats = get_dashboard_statistics(current_user=admin_user, db=db)
    assert stats.total_circulars > 0
    assert stats.upcoming_deadlines_count > 0

def test_chat_rag_endpoint(db):
    student_user = db.query(User).filter(User.role == "student").first()
    req = ChatQueryRequest(query="What is the examination registration deadline?")
    res = query_ai_assistant(request=req, current_user=student_user, db=db)
    assert res["sender"] == "assistant"
    assert len(res["citations"]) > 0
    assert "Verified Institutional Deadlines" in res["content"] or "Policy Evidence" in res["content"]
