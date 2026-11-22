import os
import datetime
from sqlalchemy.orm import Session
from app.database.session import Base, engine, SessionLocal
from app.core.security import get_password_hash
from app.models.models import (
    User, UserProfile, Department, Document, DocumentVersion, 
    PolicyRule, Deadline, ExtractedPolicy, ActionPlan, ActionItem, 
    Notification, UserApplicability
)
from app.agents.orchestrator import orchestrator
from app.core.config import settings

def init_database():
    print("Creating all database tables...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 1. Seed Departments
        dept_data = [
            ("CSE", "Computer Science and Engineering", "Department of CSE"),
            ("IT", "Information Technology", "Department of IT"),
            ("ECE", "Electronics and Communication", "Department of ECE"),
            ("MECH", "Mechanical Engineering", "Department of Mechanical"),
            ("ACAD", "Academic Affairs", "Office of Academic Affairs"),
            ("EXAM", "Controller of Examinations", "Examination Directorate"),
            ("TPO", "Training and Placements", "Corporate Relations & Placement Cell"),
            ("FIN", "Finance and Accounts", "Accounts & Tuition Fee Section")
        ]

        departments_map = {}
        for code, name, desc in dept_data:
            dept = db.query(Department).filter(Department.code == code).first()
            if not dept:
                dept = Department(code=code, name=name, description=desc)
                db.add(dept)
                db.flush()
            departments_map[code] = dept

        # 2. Seed Default Accounts
        # Admin
        admin = db.query(User).filter(User.email == "admin@college.edu").first()
        if not admin:
            admin = User(
                email="admin@college.edu",
                hashed_password=get_password_hash("Admin@1234"),
                full_name="Dr. S. Ramanathan (Registrar)",
                role="admin",
                is_active=True
            )
            db.add(admin)
            db.flush()
            admin_profile = UserProfile(
                user_id=admin.id,
                department_id=departments_map["ACAD"].id,
                degree_program="Institutional Administration"
            )
            db.add(admin_profile)

        # Faculty
        faculty = db.query(User).filter(User.email == "faculty@college.edu").first()
        if not faculty:
            faculty = User(
                email="faculty@college.edu",
                hashed_password=get_password_hash("Faculty@1234"),
                full_name="Prof. Anita Sharma (CSE HOD)",
                role="faculty",
                is_active=True
            )
            db.add(faculty)
            db.flush()
            fac_profile = UserProfile(
                user_id=faculty.id,
                department_id=departments_map["CSE"].id,
                degree_program="Faculty Advisor"
            )
            db.add(fac_profile)

        # Student
        student = db.query(User).filter(User.email == "student@college.edu").first()
        if not student:
            student = User(
                email="student@college.edu",
                hashed_password=get_password_hash("Student@1234"),
                full_name="Rohan Verma",
                role="student",
                is_active=True
            )
            db.add(student)
            db.flush()
            stud_profile = UserProfile(
                user_id=student.id,
                department_id=departments_map["CSE"].id,
                roll_number="2024CS101",
                academic_year="3rd Year",
                semester=5,
                section="A",
                degree_program="B.Tech Computer Science",
                nexus_student_id="NEX-2024-8841",
                nexus_sync_status="synced"
            )
            db.add(stud_profile)

        db.commit()

        # 3. Seed Realistic Versioned Policy Circulars
        seed_sample_circulars(db, admin.id)

        print("Database initialized and pre-seeded successfully!")
    finally:
        db.close()

def seed_sample_circulars(db: Session, admin_id: int):
    # Only seed if no documents exist
    if db.query(Document).count() > 0:
        print("Documents already exist. Skipping document seed.")
        return

    sample_dir = os.path.join(settings.UPLOAD_DIRECTORY, "seed_samples")
    os.makedirs(sample_dir, exist_ok=True)

    # Document 1: Examination Registration Circular v1.0
    doc1_v1_text = """OFFICE OF THE CONTROLLER OF EXAMINATIONS
CIRCULAR No: CIR/2026/EXAM-042
Date of Publication: 01 November 2026
Effective Date: 05 November 2026

SUBJECT: END-SEMESTER EXAMINATION REGISTRATION (ODD SEMESTER 2026-2027)

1. Scope and Target Audience:
This notification applies to all 3rd Year and Final Year undergraduate students of Computer Science, Information Technology, and Electronics Engineering.

2. Mandatory Eligibility Criteria:
A minimum of 75% attendance in each registered subject is strictly mandatory to be eligible to sit for the end-semester examinations. Students falling below 75% will be detained.

3. Registration Deadline & Fee Payment:
The examination registration portal will open on 05 November 2026.
The last date for examination registration and payment of exam fee of Rs. 1,200 is 15 November 2026 at 5:00 PM. No late submissions will be entertained under any circumstances.

4. Required Submission Steps:
- Students must log in to the student portal and verify registered elective courses.
- Upload receipt of fee payment.
- Download and obtain signature on the hall ticket verification form from the department advisor before 14 November 2026.
"""
    f1_v1_path = os.path.join(sample_dir, "CIR-2026-EXAM-042_v1.0.txt")
    with open(f1_v1_path, "w", encoding="utf-8") as f:
        f.write(doc1_v1_text)

    orchestrator.process_new_document_lifecycle(
        db=db,
        file_path=f1_v1_path,
        original_filename="CIR-2026-EXAM-042_v1.0.txt",
        file_type="txt",
        file_size=len(doc1_v1_text),
        uploaded_by_user_id=admin_id,
        manual_version="v1.0"
    )

    # Document 2: Examination Registration Circular v2.0 (REVISION & DEADLINE EXTENSION)
    doc1_v2_text = """OFFICE OF THE CONTROLLER OF EXAMINATIONS
CIRCULAR No: CIR/2026/EXAM-042
Date of Publication: 12 November 2026
Effective Date: 12 November 2026

SUBJECT: REVISED END-SEMESTER EXAMINATION REGISTRATION (EXTENSION & ATTENDANCE RELAXATION)

1. Scope and Target Audience:
This revised notification applies to all 3rd Year and Final Year undergraduate students of Computer Science, Information Technology, and Electronics Engineering.

2. Revised Attendance Policy:
Considering recent inter-college technical symposiums, the minimum required attendance is hereby revised to 70% subject to submission of valid official medical certificates or duty leave approvals approved by the Head of Department.

3. Extended Registration Deadline:
In response to student representations and bank server maintenance, the deadline for examination registration is EXTENDED to 20 November 2026 at 11:59 PM.
Registration between 21 November 2026 and 23 November 2026 will incur a late penalty fee of Rs. 500.

4. Action Items:
- Submit elective verification online on or before 20 November 2026.
- Clear outstanding dues with the accounts department before generating hall tickets.
"""
    f1_v2_path = os.path.join(sample_dir, "CIR-2026-EXAM-042_v2.0.txt")
    with open(f1_v2_path, "w", encoding="utf-8") as f:
        f.write(doc1_v2_text)

    orchestrator.process_new_document_lifecycle(
        db=db,
        file_path=f1_v2_path,
        original_filename="CIR-2026-EXAM-042_v2.0.txt",
        file_type="txt",
        file_size=len(doc1_v2_text),
        uploaded_by_user_id=admin_id,
        manual_version="v2.0"
    )

    # Document 3: Campus Placement & Internship Guidelines
    doc2_text = """TRAINING AND PLACEMENT CELL
CIRCULAR No: CIR/2026/TPO-018
Date of Publication: 28 October 2026
Effective Date: 01 November 2026

SUBJECT: CAMPUS RECRUITMENT DRIVE & INTERNSHIP SUBMISSION GUIDELINES

1. Target Audience:
All 3rd Year and Final Year B.Tech Computer Science and Information Technology students.

2. Eligibility Criteria:
Students must possess an aggregate CGPA of 7.0 or above with no active backlogs to register for Tier-1 recruitment drives.

3. Important Deadlines:
- Profile & Resume Submission Deadline: 25 November 2026 at 6:00 PM.
- Technical Pre-Assessment Test: Scheduled for 28 November 2026 at 10:00 AM.
- Mandatory Company Briefing Session: 30 November 2026.

4. Mandatory Guidelines:
- Strict formal dress code is required for all placement interactions.
- Placed students must submit company offer letters to the TPO cell within 3 days of receipt.
"""
    f2_path = os.path.join(sample_dir, "CIR-2026-TPO-018_v1.0.txt")
    with open(f2_path, "w", encoding="utf-8") as f:
        f.write(doc2_text)

    orchestrator.process_new_document_lifecycle(
        db=db,
        file_path=f2_path,
        original_filename="CIR-2026-TPO-018_v1.0.txt",
        file_type="txt",
        file_size=len(doc2_text),
        uploaded_by_user_id=admin_id,
        manual_version="v1.0"
    )

    # Document 4: Tuition Fee Payment
    doc3_text = """FINANCE AND ACCOUNTS SECTION
CIRCULAR No: CIR/2026/FIN-088
Date of Publication: 15 October 2026
Effective Date: 20 October 2026

SUBJECT: ODD SEMESTER TUITION FEE PAYMENT AND SCHOLARSHIP DUES

1. Scope:
Applicable to all enrolled students across all academic branches.

2. Fee Payment Deadline:
The last date for payment of semester tuition fee without late fee is 30 November 2026 at 5:00 PM.
A late fine of Rs. 100 per day will be levied from 01 December 2026 onwards.

3. Instructions:
Payment must be executed exclusively through the ERP banking gateway. Cash payments are not accepted.
"""
    f3_path = os.path.join(sample_dir, "CIR-2026-FIN-088_v1.0.txt")
    with open(f3_path, "w", encoding="utf-8") as f:
        f.write(doc3_text)

    orchestrator.process_new_document_lifecycle(
        db=db,
        file_path=f3_path,
        original_filename="CIR-2026-FIN-088_v1.0.txt",
        file_type="txt",
        file_size=len(doc3_text),
        uploaded_by_user_id=admin_id,
        manual_version="v1.0"
    )

if __name__ == "__main__":
    init_database()
