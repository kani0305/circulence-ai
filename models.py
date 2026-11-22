import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date, 
    ForeignKey, Float, JSON
)
from sqlalchemy.orm import relationship
from app.database.session import Base

def utcnow():
    return datetime.datetime.utcnow()

# 1. users
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), default="student", nullable=False)  # student, faculty, admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    profile = relationship("UserProfile", back_populates="user", uselist=False)
    notifications = relationship("Notification", back_populates="user")
    action_plans = relationship("ActionPlan", back_populates="user")
    action_items = relationship("ActionItem", back_populates="user")
    applicabilities = relationship("UserApplicability", back_populates="user")
    chat_sessions = relationship("ChatSession", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")

# 2. departments
class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    documents = relationship("Document", back_populates="department")
    user_profiles = relationship("UserProfile", back_populates="department")

# 3. user_profiles
class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    roll_number = Column(String(100), unique=True, index=True, nullable=True)
    academic_year = Column(String(50), nullable=True)  # e.g., "3rd Year", "Final Year"
    semester = Column(Integer, nullable=True)          # e.g., 5, 6
    section = Column(String(10), nullable=True)        # e.g., "A", "B"
    degree_program = Column(String(100), nullable=True) # e.g., "B.Tech Computer Science"
    nexus_student_id = Column(String(100), nullable=True, index=True)
    nexus_sync_status = Column(String(50), default="not_synced")  # synced, pending, error
    extra_attributes = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="profile")
    department = relationship("Department", back_populates="user_profiles")

# 4. documents
class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    document_number = Column(String(100), unique=True, index=True, nullable=False)
    title = Column(String(500), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    category = Column(String(100), default="General", index=True) # Academic, Examination, Placement, Fee, Hostel
    status = Column(String(50), default="active", index=True)      # active, superseded, withdrawn, draft, under_review
    current_version_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    department = relationship("Department", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document", foreign_keys="DocumentVersion.document_id")

# 5. document_versions
class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    version_number = Column(String(20), nullable=False)  # "v1.0", "v2.0"
    publication_date = Column(Date, nullable=True, index=True)
    effective_date = Column(Date, nullable=True, index=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(20), nullable=False)  # pdf, docx, txt
    file_size = Column(Integer, default=0)
    summary = Column(Text, nullable=True)
    status = Column(String(50), default="active")  # active, superseded, withdrawn
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    document = relationship("Document", back_populates="versions", foreign_keys=[document_id])
    chunks = relationship("DocumentChunk", back_populates="version", cascade="all, delete-orphan")
    extracted_policy = relationship("ExtractedPolicy", back_populates="version", uselist=False, cascade="all, delete-orphan")
    deadlines = relationship("Deadline", back_populates="version", cascade="all, delete-orphan")
    applicabilities = relationship("UserApplicability", back_populates="version", cascade="all, delete-orphan")
    policy_rules = relationship("PolicyRule", back_populates="version", cascade="all, delete-orphan")

# 6. document_chunks
class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_version_id = Column(Integer, ForeignKey("document_versions.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, default=1)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    embedding_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    version = relationship("DocumentVersion", back_populates="chunks")

# 7. extracted_policies
class ExtractedPolicy(Base):
    __tablename__ = "extracted_policies"

    id = Column(Integer, primary_key=True, index=True)
    document_version_id = Column(Integer, ForeignKey("document_versions.id"), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    department = Column(String(255), nullable=True)
    publication_date = Column(Date, nullable=True)
    effective_date = Column(Date, nullable=True)
    target_audience = Column(JSON, default=list) # e.g. ["3rd Year", "Computer Science", "All Students"]
    raw_extraction_json = Column(JSON, default=dict)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    version = relationship("DocumentVersion", back_populates="extracted_policy")
    rules = relationship("PolicyRule", back_populates="extracted_policy", cascade="all, delete-orphan")

# 8. policy_rules
class PolicyRule(Base):
    __tablename__ = "policy_rules"

    id = Column(Integer, primary_key=True, index=True)
    extracted_policy_id = Column(Integer, ForeignKey("extracted_policies.id"), nullable=True)
    document_version_id = Column(Integer, ForeignKey("document_versions.id"), nullable=False, index=True)
    rule_type = Column(String(50), default="mandatory")  # mandatory, guideline, eligibility, instruction, penalty
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    clause_reference = Column(String(100), nullable=True)
    page_number = Column(Integer, default=1)
    created_at = Column(DateTime, default=utcnow)

    extracted_policy = relationship("ExtractedPolicy", back_populates="rules")
    version = relationship("DocumentVersion", back_populates="policy_rules")

# 9. policy_changes
class PolicyChange(Base):
    __tablename__ = "policy_changes"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    old_version_id = Column(Integer, ForeignKey("document_versions.id"), nullable=False)
    new_version_id = Column(Integer, ForeignKey("document_versions.id"), nullable=False)
    change_type = Column(String(100), nullable=False)  # added_rule, modified_rule, removed_rule, changed_deadline, eligibility_change
    previous_content = Column(Text, nullable=True)
    updated_content = Column(Text, nullable=True)
    summary = Column(Text, nullable=False)
    human_readable_diff = Column(Text, nullable=True)
    detected_at = Column(DateTime, default=utcnow)

# 10. policy_contradictions
class PolicyContradiction(Base):
    __tablename__ = "policy_contradictions"

    id = Column(Integer, primary_key=True, index=True)
    document_version_a_id = Column(Integer, ForeignKey("document_versions.id"), nullable=False)
    document_version_b_id = Column(Integer, ForeignKey("document_versions.id"), nullable=False)
    clause_a = Column(Text, nullable=False)
    clause_b = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(50), default="medium")  # low, medium, high, critical
    status = Column(String(50), default="needs_review")  # needs_review, resolved, dismissed
    detected_at = Column(DateTime, default=utcnow)

    resolution = relationship("ContradictionResolution", back_populates="contradiction", uselist=False)

# 11. contradiction_resolutions
class ContradictionResolution(Base):
    __tablename__ = "contradiction_resolutions"

    id = Column(Integer, primary_key=True, index=True)
    contradiction_id = Column(Integer, ForeignKey("policy_contradictions.id"), unique=True, nullable=False)
    resolved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    resolution_decision = Column(String(100), nullable=False)  # supersede_b, supersede_a, custom_guidance
    administrative_notes = Column(Text, nullable=False)
    resolved_at = Column(DateTime, default=utcnow)

    contradiction = relationship("PolicyContradiction", back_populates="resolution")

# 12. user_applicability
class UserApplicability(Base):
    __tablename__ = "user_applicability"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_version_id = Column(Integer, ForeignKey("document_versions.id"), nullable=False, index=True)
    is_applicable = Column(Boolean, default=False)
    match_confidence = Column(Float, default=1.0)
    reasoning_evidence = Column(Text, nullable=False)
    missing_information = Column(Text, nullable=True)
    evaluated_at = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="applicabilities")
    version = relationship("DocumentVersion", back_populates="applicabilities")

# 13. deadlines
class Deadline(Base):
    __tablename__ = "deadlines"

    id = Column(Integer, primary_key=True, index=True)
    document_version_id = Column(Integer, ForeignKey("document_versions.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), default="general") # examination, registration, fee_payment, submission, event
    deadline_date = Column(DateTime, nullable=False, index=True)
    original_deadline_date = Column(DateTime, nullable=True)
    is_extended = Column(Boolean, default=False)
    is_cancelled = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    version = relationship("DocumentVersion", back_populates="deadlines")

# 14. action_plans
class ActionPlan(Base):
    __tablename__ = "action_plans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_version_id = Column(Integer, ForeignKey("document_versions.id"), nullable=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="active") # active, completed, archived
    generated_at = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="action_plans")
    items = relationship("ActionItem", back_populates="action_plan", cascade="all, delete-orphan")

# 15. action_items
class ActionItem(Base):
    __tablename__ = "action_items"

    id = Column(Integer, primary_key=True, index=True)
    action_plan_id = Column(Integer, ForeignKey("action_plans.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(20), default="medium") # critical, high, medium, low
    due_date = Column(DateTime, nullable=True)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    supporting_evidence = Column(Text, nullable=True)
    page_number = Column(Integer, default=1)
    created_at = Column(DateTime, default=utcnow)

    action_plan = relationship("ActionPlan", back_populates="items")
    user = relationship("User", back_populates="action_items")

# 16. notifications
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(String(50), default="system") # new_circular, policy_update, deadline_reminder, deadline_change, contradiction_alert
    related_document_id = Column(Integer, nullable=True)
    related_deadline_id = Column(Integer, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="notifications")

# 17. chat_sessions
class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), default="Policy Inquiry")
    as_of_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

# 18. chat_messages
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    sender = Column(String(20), nullable=False) # user, assistant
    content = Column(Text, nullable=False)
    is_uncertain = Column(Boolean, default=False)
    confidence_score = Column(Float, default=1.0)
    created_at = Column(DateTime, default=utcnow)

    session = relationship("ChatSession", back_populates="messages")
    citations = relationship("SourceReference", back_populates="message", cascade="all, delete-orphan")

# 19. source_references
class SourceReference(Base):
    __tablename__ = "source_references"

    id = Column(Integer, primary_key=True, index=True)
    chat_message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=False, index=True)
    document_version_id = Column(Integer, ForeignKey("document_versions.id"), nullable=True)
    document_title = Column(String(500), nullable=False)
    version_number = Column(String(20), nullable=False)
    page_number = Column(Integer, default=1)
    excerpt = Column(Text, nullable=False)
    publication_date = Column(Date, nullable=True)
    effective_date = Column(Date, nullable=True)
    relevance_score = Column(Float, default=1.0)

    message = relationship("ChatMessage", back_populates="citations")

# 20. audit_logs
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False) # UPLOAD_CIRCULAR, RESOLVE_CONTRADICTION, MODIFY_DEADLINE, etc.
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(String(100), nullable=True)
    details_json = Column(JSON, default=dict)
    ip_address = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="audit_logs")

# 21. nexus_api_sync_logs
class NexusApiSyncLog(Base):
    __tablename__ = "nexus_api_sync_logs"

    id = Column(Integer, primary_key=True, index=True)
    sync_type = Column(String(100), nullable=False) # student_profile, department_catalog, attendance
    status = Column(String(50), nullable=False)     # success, failed, timeout, skipped
    records_synced = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    request_url = Column(String(500), nullable=True)
    response_status_code = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=utcnow)
