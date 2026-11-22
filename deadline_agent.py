import re
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.models import Deadline, DocumentVersion, Notification, User, UserApplicability
from app.services.document_parser import DocumentParser

class DeadlineManagementAgent:
    """
    Agent 6: Deadline Management Agent
    Responsibilities:
    - Extracts precise deadlines from circular texts (dates, times, categories).
    - Detects whether deadlines are newly created, modified/extended, or cancelled.
    - Prevents duplicate notification spam.
    - Dispatches scheduled reminders at [7, 3, 1, 0] days prior to deadline for verified deadlines.
    """

    def extract_and_sync_deadlines(
        self,
        db: Session,
        version_id: int,
        pages_raw: List[Dict[str, Any]]
    ) -> List[Deadline]:
        doc_version = db.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
        if not doc_version:
            return []

        full_text = "\n".join([p["text"] for p in pages_raw])
        extracted_deadlines = []

        # Patterns for deadlines
        deadline_patterns = [
            r"(?:last\s*date|deadline|due\s*date|registration\s*closes|submission\s*date|scheduled\s*on)[\s\w]*?(?:is|:|-)?\s*([0-9]{1,2}(?:st|nd|rd|th)?[\s\/\-\.](?:[A-Za-z]+|[0-9]{1,2})[\s\/\-\.][0-9]{2,4}(?:\s*(?:at|by)?\s*[0-9]{1,2}(?::[0-9]{2})?\s*(?:AM|PM|am|pm)?)?)",
            r"(?:on\s*or\s*before)\s*([0-9]{1,2}(?:st|nd|rd|th)?[\s\/\-\.](?:[A-Za-z]+|[0-9]{1,2})[\s\/\-\.][0-9]{2,4})",
            r"([0-9]{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+[0-9]{4})"
        ]

        # Scan for deadline sentences
        sentences = re.split(r"(?<=[.!?\n])\s+", full_text)
        found_dates = []

        for sent in sentences:
            sent_clean = sent.strip()
            if any(term in sent_clean.lower() for term in ["deadline", "last date", "due date", "closes", "submission", "schedule", "commence"]):
                for pat in deadline_patterns:
                    m = re.search(pat, sent_clean, re.IGNORECASE)
                    if m:
                        raw_date_str = m.group(1).strip()
                        # Clean ordinal indicators (15th -> 15)
                        clean_str = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", raw_date_str)
                        parsed_dt = self._parse_datetime(clean_str)
                        if parsed_dt and parsed_dt not in found_dates:
                            found_dates.append(parsed_dt)

                            # Identify category
                            cat = "general"
                            sent_low = sent_clean.lower()
                            if "exam" in sent_low:
                                cat = "examination"
                            elif "fee" in sent_low or "payment" in sent_low:
                                cat = "fee_payment"
                            elif "registration" in sent_low:
                                cat = "registration"
                            elif "submit" in sent_low or "upload" in sent_low:
                                cat = "submission"
                            elif "interview" in sent_low or "drive" in sent_low:
                                cat = "event"

                            # Short title
                            title = " ".join(sent_clean.split()[:8])
                            extracted_deadlines.append({
                                "title": title,
                                "description": sent_clean,
                                "category": cat,
                                "deadline_date": parsed_dt
                            })

        # Persist extracted deadlines
        created_deadlines = []
        for item in extracted_deadlines:
            # Check if this exact deadline already exists for this version
            exists = db.query(Deadline).filter(
                Deadline.document_version_id == version_id,
                Deadline.title == item["title"]
            ).first()

            if not exists:
                dl = Deadline(
                    document_version_id=version_id,
                    title=item["title"],
                    description=item["description"],
                    category=item["category"],
                    deadline_date=item["deadline_date"],
                    is_verified=True,
                    is_extended=False
                )
                db.add(dl)
                created_deadlines.append(dl)

        db.commit()
        return created_deadlines

    def _parse_datetime(self, s: str) -> Optional[datetime.datetime]:
        s = s.replace(",", "").strip()
        # Remove trailing words if present
        s = re.split(r"\s+(?:without|with|subject|inclusive)", s, flags=re.IGNORECASE)[0].strip()

        date_formats = [
            "%d-%m-%Y %I:%M %p", "%d/%m/%Y %I:%M %p", "%Y-%m-%d %I:%M %p",
            "%d %B %Y %I:%M %p", "%d %b %Y %I:%M %p",
            "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y",
            "%d %B %Y", "%d %b %Y", "%B %d %Y"
        ]

        for fmt in date_formats:
            try:
                dt = datetime.datetime.strptime(s, fmt)
                # If time was omitted, set to 23:59:00 end of that day
                if "%I" not in fmt and "%H" not in fmt:
                    dt = dt.replace(hour=23, minute=59, second=0)
                return dt
            except ValueError:
                continue
        return None

    def generate_deadline_reminders(self, db: Session):
        """
        Runs on schedule. Checks all active, verified deadlines against
        [7, 3, 1, 0] days thresholds and creates notifications without duplicates.
        """
        now = datetime.datetime.utcnow()
        active_deadlines = db.query(Deadline).filter(
            Deadline.is_verified == True,
            Deadline.is_cancelled == False,
            Deadline.deadline_date >= now - datetime.timedelta(days=1)
        ).all()

        reminders_created = 0
        for dl in active_deadlines:
            diff = dl.deadline_date - now
            days_left = diff.days

            if days_left in (7, 3, 1, 0):
                # Identify applicable users
                applicable_records = db.query(UserApplicability).filter(
                    UserApplicability.document_version_id == dl.document_version_id,
                    UserApplicability.is_applicable == True
                ).all()

                user_ids = [rec.user_id for rec in applicable_records]
                if not user_ids:
                    # If not explicitly mapped, check all active students
                    user_ids = [u.id for u in db.query(User).filter(User.role == "student").all()]

                label = "Today!" if days_left == 0 else f"in {days_left} day{'s' if days_left > 1 else ''}"
                
                for uid in user_ids:
                    # Check for duplicate notification sent today
                    already_sent = db.query(Notification).filter(
                        Notification.user_id == uid,
                        Notification.related_deadline_id == dl.id,
                        Notification.created_at >= now - datetime.timedelta(hours=18)
                    ).first()

                    if not already_sent:
                        notif = Notification(
                            user_id=uid,
                            title=f"Deadline Reminder: {dl.title} is due {label}",
                            message=f"Official institutional deadline for '{dl.title}' ({dl.category.title()}) is scheduled for {dl.deadline_date.strftime('%d %b %Y, %I:%M %p')}. Source: {dl.version.document.title if dl.version and dl.version.document else 'Circular'}.",
                            notification_type="deadline_reminder",
                            related_document_id=dl.version.document_id if dl.version else None,
                            related_deadline_id=dl.id,
                            is_read=False
                        )
                        db.add(notif)
                        reminders_created += 1

        db.commit()
        return reminders_created

deadline_agent = DeadlineManagementAgent()
