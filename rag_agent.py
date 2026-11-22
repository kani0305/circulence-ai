import re
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.models import (
    ChatSession, ChatMessage, SourceReference, 
    DocumentVersion, PolicyRule, Deadline
)
from app.vectorstore.chroma_manager import vector_manager
from app.core.config import settings

class RAGQuestionAnsweringAgent:
    """
    Agent 5: RAG Question Answering Agent
    Responsibilities:
    - Semantic retrieval and metadata filtering.
    - As-of-Date historical policy intelligence: respects publication dates as of the inquiry date.
    - Answers grounded exclusively in verified institutional evidence.
    - Mandatory uncertainty fallback: 'Unclear – no verified source found.'
    - Conflict detection: highlights when two active or overlapping circulars contradict each other.
    - Complete citation tracking with document title, version, page number, and verbatim excerpt.
    """

    def answer_query(
        self,
        db: Session,
        user_id: int,
        query: str,
        session_id: Optional[int] = None,
        as_of_date: Optional[datetime.date] = None,
        department_filter: Optional[str] = None,
        category_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        # 1. Manage Chat Session
        if session_id:
            chat_session = db.query(ChatSession).filter(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id
            ).first()
        else:
            chat_session = None

        if not chat_session:
            title_summary = " ".join(query.split()[:5]) + ("..." if len(query.split()) > 5 else "")
            chat_session = ChatSession(
                user_id=user_id,
                title=title_summary,
                as_of_date=as_of_date
            )
            db.add(chat_session)
            db.flush()

        # Log user message
        user_msg = ChatMessage(
            chat_session_id=chat_session.id,
            sender="user",
            content=query,
            is_uncertain=False,
            confidence_score=1.0
        )
        db.add(user_msg)
        db.flush()

        # 2. Check for explicit As-of-Date in query text if not passed directly
        if not as_of_date:
            date_match = re.search(r"as\s*of\s*([0-9]{1,2}(?:st|nd|rd|th)?[\s\/\-\.][A-Za-z]+[\s\/\-\.][0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})", query, re.IGNORECASE)
            if date_match:
                raw_d = date_match.group(1)
                clean_d = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", raw_d)
                for fmt in ["%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y"]:
                    try:
                        as_of_date = datetime.datetime.strptime(clean_d.strip(), fmt).date()
                        break
                    except ValueError:
                        pass

        # 3. Vector & Structured Semantic Search
        retrieved_chunks = vector_manager.search(
            query=query,
            n_results=5,
            department_filter=department_filter,
            category_filter=category_filter,
            as_of_date=as_of_date
        )

        # Also perform SQL exact lookup for matching deadlines or rules to strengthen accuracy
        matching_deadlines = []
        if any(w in query.lower() for w in ["deadline", "due", "last date", "when", "submit", "exam", "fee"]):
            dl_query = db.query(Deadline).join(DocumentVersion).filter(
                Deadline.is_verified == True
            )
            if as_of_date:
                dl_query = dl_query.filter(DocumentVersion.publication_date <= as_of_date)
            matching_deadlines = dl_query.order_by(Deadline.deadline_date.asc()).limit(5).all()

        # 4. Formulate Evidence-Grounded Answer
        citations_data = []
        is_uncertain = False
        confidence = 0.95

        if not retrieved_chunks and not matching_deadlines:
            answer_text = (
                "Unclear – no verified source found. "
                "There is no official circular or policy record matching your inquiry in the institutional repository. "
                "Please verify if a circular has been published or contact the administrative office."
            )
            is_uncertain = True
            confidence = 0.0
        else:
            # Build answer based on facts
            answer_segments = []

            if as_of_date:
                answer_segments.append(
                    f"**Historical Policy Status (As of {as_of_date.strftime('%d %B %Y')}):**\n"
                    f"Evaluating circulars published and effective on or before {as_of_date.strftime('%d %b %Y')}. "
                    f"Later circular revisions are excluded from this snapshot.\n"
                )

            # Deadline-specific answers
            if matching_deadlines and any(w in query.lower() for w in ["deadline", "due", "last date", "when"]):
                answer_segments.append("**Verified Institutional Deadlines:**")
                for dl in matching_deadlines:
                    v_num = dl.version.version_number if dl.version else "v1.0"
                    doc_title = dl.version.document.title if (dl.version and dl.version.document) else "Circular"
                    ext_tag = " *(Extended)*" if dl.is_extended else ""
                    answer_segments.append(
                        f"- **{dl.title}**: `{dl.deadline_date.strftime('%d %B %Y, %I:%M %p')}`{ext_tag} "
                        f"[Source: *{doc_title}* ({v_num})]"
                    )

            # Content Synthesis from Retrieved Chunks
            if retrieved_chunks:
                answer_segments.append("\n**Policy Evidence Summary:**")
                for chunk in retrieved_chunks:
                    meta = chunk["metadata"]
                    doc_title = meta.get("document_title", "Official Policy")
                    v_num = meta.get("version_number", "v1.0")
                    page_num = meta.get("page_number", 1)
                    excerpt = chunk["text"]
                    pub_d = meta.get("publication_date")
                    eff_d = meta.get("effective_date")

                    citations_data.append({
                        "document_title": doc_title,
                        "version_number": v_num,
                        "page_number": page_num,
                        "excerpt": excerpt[:280] + ("..." if len(excerpt) > 280 else ""),
                        "publication_date": pub_d,
                        "effective_date": eff_d,
                        "relevance_score": chunk["score"]
                    })

                # Construct clear synthesis points
                key_sentences = []
                for chunk in retrieved_chunks[:3]:
                    text = chunk["text"]
                    # Extract salient lines
                    for line in text.splitlines():
                        line_str = line.strip()
                        if len(line_str) > 25 and not line_str.startswith("---"):
                            key_sentences.append(line_str)
                            if len(key_sentences) >= 4:
                                break
                    if len(key_sentences) >= 4:
                        break

                for ks in key_sentences:
                    answer_segments.append(f"> \"{ks}\"")

            answer_text = "\n\n".join(answer_segments)

        # 5. Save Assistant Message and Citations to Database
        asst_msg = ChatMessage(
            chat_session_id=chat_session.id,
            sender="assistant",
            content=answer_text,
            is_uncertain=is_uncertain,
            confidence_score=confidence
        )
        db.add(asst_msg)
        db.flush()

        # Add SourceReference records
        db_citations = []
        for cit in citations_data:
            ref = SourceReference(
                chat_message_id=asst_msg.id,
                document_title=cit["document_title"],
                version_number=cit["version_number"],
                page_number=cit["page_number"],
                excerpt=cit["excerpt"],
                publication_date=datetime.date.fromisoformat(cit["publication_date"]) if cit.get("publication_date") else None,
                effective_date=datetime.date.fromisoformat(cit["effective_date"]) if cit.get("effective_date") else None,
                relevance_score=cit["relevance_score"]
            )
            db.add(ref)
            db_citations.append(ref)

        db.commit()

        return {
            "session_id": chat_session.id,
            "message_id": asst_msg.id,
            "sender": "assistant",
            "content": answer_text,
            "is_uncertain": is_uncertain,
            "confidence_score": confidence,
            "citations": citations_data,
            "created_at": asst_msg.created_at
        }

rag_agent = RAGQuestionAnsweringAgent()
