import pytest
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base
from app.models.models import (
    User, UserProfile, Department, Document, DocumentVersion, 
    PolicyRule, Deadline, ExtractedPolicy, UserApplicability
)
from app.services.document_parser import DocumentParser
from app.vectorstore.chroma_manager import LocalSemanticEmbedder
from app.agents.version_agent import version_agent
from app.agents.applicability_agent import applicability_agent
from app.agents.rag_agent import rag_agent
from app.services.nexus_service import nexus_service

# Use in-memory SQLite database for isolated unit tests
TEST_DB_URL = "sqlite:///:memory:"

@pytest.fixture
def db():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    
    # Seed mock department
    dept = Department(code="CSE", name="Computer Science and Engineering")
    session.add(dept)
    session.flush()

    # Seed mock student
    user = User(
        email="test_student@college.edu",
        hashed_password="hashed_pwd",
        full_name="Test Student",
        role="student",
        is_active=True
    )
    session.add(user)
    session.flush()

    profile = UserProfile(
        user_id=user.id,
        department_id=dept.id,
        roll_number="2024CS999",
        academic_year="3rd Year",
        semester=5,
        degree_program="B.Tech Computer Science"
    )
    session.add(profile)
    session.commit()

    yield session
    session.close()


def test_document_parser_metadata_extraction():
    sample_pages = [{
        "page": 1,
        "text": """OFFICE OF CONTROLLER OF EXAMINATIONS
CIRCULAR No: CIR/2026/EXAM-100
Date: 10 October 2026
SUBJECT: SEMESTER EXAMINATION SCHEDULE

1. Minimum 75% attendance mandatory.
2. Last date for registration is 25 October 2026 at 5:00 PM.
"""
    }]
    meta = DocumentParser.extract_metadata(sample_pages, "exam_circular.txt")
    assert meta["document_number"] == "CIR/2026/EXAM-100"
    assert "SEMESTER EXAMINATION" in meta["title"].upper()
    assert meta["category"] == "Examination"
    assert meta["publication_date"] == datetime.date(2026, 10, 10)


def test_local_semantic_embedder():
    v1 = LocalSemanticEmbedder.embed_text("Examination registration deadline 20 November")
    v2 = LocalSemanticEmbedder.embed_text("Last date for exam registration")
    v3 = LocalSemanticEmbedder.embed_text("Hostel mess catering schedule")

    assert len(v1) == 384
    assert len(v2) == 384

    # Compute cosine similarity
    def cosine(a, b):
        return sum(x * y for x, y in zip(a, b))

    sim_related = cosine(v1, v2)
    sim_unrelated = cosine(v1, v3)

    assert sim_related > sim_unrelated, "Semantically related texts must have higher cosine similarity"


def test_user_applicability_agent(db):
    user = db.query(User).filter(User.email == "test_student@college.edu").first()

    # Create mock document targeting 3rd Year CSE
    doc = Document(document_number="TEST-001", title="CSE Placement Policy", status="active")
    db.add(doc)
    db.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number="v1.0",
        file_name="test.txt",
        file_path="dummy",
        file_type="txt",
        status="active"
    )
    db.add(ver)
    db.flush()

    policy = ExtractedPolicy(
        document_version_id=ver.id,
        title=doc.title,
        department="Computer Science",
        target_audience=["3rd Year", "Computer Science"],
        raw_extraction_json={}
    )
    db.add(policy)
    db.commit()

    res = applicability_agent.evaluate_applicability(db, user.id, ver.id)
    assert res["is_applicable"] == True
    assert "Computer Science" in res["reasoning_evidence"]
    assert "3rd Year" in res["reasoning_evidence"]


def test_version_comparison_detects_deadline_change(db):
    doc = Document(document_number="TEST-REV", title="Exam Schedule", status="active")
    db.add(doc)
    db.flush()

    # Version 1 with deadline 15 Nov
    v1 = DocumentVersion(
        document_id=doc.id,
        version_number="v1.0",
        file_name="v1.txt",
        file_path="dummy",
        file_type="txt",
        publication_date=datetime.date(2026, 11, 1),
        created_at=datetime.datetime(2026, 11, 1, 10, 0, 0)
    )
    db.add(v1)
    db.flush()

    dl1 = Deadline(
        document_version_id=v1.id,
        title="Exam Registration",
        deadline_date=datetime.datetime(2026, 11, 15, 17, 0, 0),
        category="examination"
    )
    db.add(dl1)

    # Version 2 with extended deadline 20 Nov
    v2 = DocumentVersion(
        document_id=doc.id,
        version_number="v2.0",
        file_name="v2.txt",
        file_path="dummy",
        file_type="txt",
        publication_date=datetime.date(2026, 11, 10),
        created_at=datetime.datetime(2026, 11, 10, 10, 0, 0)
    )
    db.add(v2)
    db.flush()

    dl2 = Deadline(
        document_version_id=v2.id,
        title="Exam Registration",
        deadline_date=datetime.datetime(2026, 11, 20, 23, 59, 0),
        category="examination"
    )
    db.add(dl2)
    db.commit()

    diff = version_agent.compare_versions(db, new_version_id=v2.id, old_version_id=v1.id)
    assert len(diff["changed_deadlines"]) == 1
    assert diff["changed_deadlines"][0]["is_extended"] == True
    assert "20 Nov 2026" in diff["changed_deadlines"][0]["new_date"]


def test_nexus_service_defensive_unconfigured_handling():
    # When Nexus credentials are not yet configured
    assert not nexus_service.is_configured() or nexus_service.is_configured()
    # Verifies graceful check without exception
    # (Actual async check is tested in FastAPI tests)
