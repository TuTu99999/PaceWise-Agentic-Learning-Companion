"""
Workflow Q&A: Hỏi đáp kiến thức học tập dựa trên tài liệu học liệu và liêm chính học thuật.
Agent phụ trách: Study Support Agent.
Tích hợp:
- Truy xuất RAG từ Qdrant Vector Store (Task 2.1, 2.2).
- Trích dẫn học liệu chính xác [Tên tài liệu, Trang X, Đoạn Y].
- Phân định 3 chế độ: grounded_answer, guided_help, insufficient_sources.
- Xử lý khiếu nại trích dẫn và cờ disputed_evidence (Task 2.3).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.grounded_answer import (
    citation_check,
    expand_source_markers,
    extractive_fallback,
    grounded_prompt,
    message_delta_text,
    message_text,
    retrieval_query,
)
from src.agents.guardrails import evaluate_guardrails, normalize_text
from src.agents.llm import get_agent_llm
from src.agents.prompts.study_support import GROUNDED_QA_SYSTEM_PROMPT
from src.agents.safety import evaluate_input_policy
from src.agents.state import LearningGraphState
from src.agents.tools.qdrant_retriever import (
    record_disputed_evidence,
    search_course_materials,
)
from src.config import get_settings

logger = logging.getLogger("pacewise.agents.qa")
_stream_sink: ContextVar[Callable[[str], None] | None] = ContextVar("qa_stream_sink", default=None)


@contextmanager
def stream_qa_tokens(sink: Callable[[str], None]) -> Iterator[None]:
    """Attach a request-local token sink without placing callbacks in graph state."""
    token = _stream_sink.set(sink)
    try:
        yield
    finally:
        _stream_sink.reset(token)


_SOCIAL_PATTERN = re.compile(
    r"\b(xin chao|chao|hello|hi|hey|alo|cam on|thanks?|thank you|tam biet|bye|"
    r"ban on khong|on chu|khoe khong|ok|okay)\b"
)
_ACADEMIC_CUE_PATTERN = re.compile(
    r"\b(giai thich|khai niem|tai sao|so sanh|cong thuc|bai tap|chuong|slide|"
    r"tai lieu|mon hoc|vi du|chung minh|phan tich|thuat toan|code|quiz|deadline|"
    r"csdl|database|sql|lap trinh|du lieu|he dieu hanh|mang may tinh|"
    r"explain|define|compare|formula|chapter|lecture|assignment|proof)\b"
)
_OBVIOUS_OFF_TOPIC_PATTERN = re.compile(
    r"\b(qua tao|trai cay|an trai|mon an|nau an|thoi tiet|du bao thoi tiet|"
    r"bong da|ty so|phim anh|nguoi yeu|hen ho|tu vi|xem boi)\b"
)
_SCOPE_STOP_WORDS = {
    "a", "an", "and", "ban", "cai", "can", "cho", "co", "cua", "duoc", "gi", "hay",
    "ho", "hoi", "la", "m", "minh", "mot", "nao", "nay", "nhe", "nhung", "noi", "tai",
    "tao", "qua", "the", "thi", "trai", "trong", "ve", "vay", "voi", "what", "why", "please",
}
_SCOPE_STOP_WORDS_UNICODE = _SCOPE_STOP_WORDS | {
    "ăn", "bạn", "cái", "cần", "có", "của", "được", "gì", "hỏi", "là", "mình", "một",
    "nào", "này", "nhé", "những", "nói", "tại", "thế", "thì", "trái", "trong", "về", "vậy", "với",
}


def _is_social_message(query: str) -> bool:
    """Recognize short social turns without stealing mixed academic questions."""
    normalized = normalize_text(query)
    if not normalized or len(normalized) > 160:
        return False
    if _ACADEMIC_CUE_PATTERN.search(normalized):
        return False
    return bool(_SOCIAL_PATTERN.search(normalized)) and len(normalized.split()) <= 16


def _is_obviously_out_of_scope(query: str) -> bool:
    normalized = normalize_text(query)
    return bool(_OBVIOUS_OFF_TOPIC_PATTERN.search(normalized)) and not bool(
        _ACADEMIC_CUE_PATTERN.search(normalized)
    )


def _meaningful_terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[^\W_]+", str(text or "").casefold(), flags=re.UNICODE)
        if len(token) > 1 and not token.isdigit() and token not in _SCOPE_STOP_WORDS_UNICODE
    }


def _normalized_meaningful_terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", normalize_text(text))
        if len(token) > 1 and not token.isdigit() and token not in _SCOPE_STOP_WORDS
    }


def _retrieval_scope_overlap(query: str, passages: list[dict[str, Any]]) -> float:
    """Check that a short query has explicit support in retrieved course text.

    Vector similarity alone can assign a confident score to unrelated short text.
    This second gate fails closed for those turns. Follow-up context is already
    included in ``query`` by ``retrieval_query``.
    """
    query_term_sets = (_meaningful_terms(query), _normalized_meaningful_terms(query))
    if not any(query_term_sets):
        return 0.0
    best = 0.0
    for passage in passages:
        searchable = " ".join(
            str(passage.get(field) or "")
            for field in ("document_title", "section_title", "content")
        )
        passage_term_sets = (_meaningful_terms(searchable), _normalized_meaningful_terms(searchable))
        for query_terms, passage_terms in zip(query_term_sets, passage_term_sets, strict=True):
            if query_terms:
                best = max(best, len(query_terms & passage_terms) / len(query_terms))
    return best


def _authorized_course_passages(
    state: LearningGraphState,
    passages: list[dict[str, Any]],
    course_code: str,
) -> list[dict[str, Any]]:
    """Fail closed if a retriever ever returns another course or resource."""
    allowed = state.get("allowed_resource_ids")
    allowed_ids = {str(value) for value in allowed} if allowed is not None else None
    authorized_versions = state.get("authorized_file_versions")
    authorized_ids = {str(value) for value in authorized_versions} if isinstance(authorized_versions, dict) else None
    scoped = []
    for passage in passages:
        if str(passage.get("course_code") or "") != course_code:
            continue
        resource_id = str(passage.get("resource_id") or passage.get("material_id") or "")
        if allowed_ids is not None and resource_id not in allowed_ids:
            continue
        if authorized_ids is not None and resource_id.startswith("file:") and resource_id not in authorized_ids:
            continue
        scoped.append(passage)
    return scoped


def _state_resource_passages(
    state: LearningGraphState,
    query: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Search LMS-scoped content already authorized and loaded by the backend."""
    stop_words = {"giải", "thích", "là", "gì", "của", "về", "bài", "môn", "học", "các", "cho", "mình", "với", "the", "a", "is", "explain", "what"}
    query_terms = Counter(word for word in re.findall(r"\w+", query.casefold()) if word not in stop_words)
    if not query_terms:
        return []
    ranked: list[tuple[int, dict[str, Any]]] = []
    course_code = str(state.get("course_code") or state.get("course_id") or "")
    for index, item in enumerate(state.get("learning_resources") or []):
        if state.get("allowed_resource_ids") is not None and str(item.get("resource_id") or item.get("id")) not in state["allowed_resource_ids"]:
            continue
        if str(item.get("course_code") or "") != course_code:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if evaluate_input_policy(content, semantic_mode="signals").get("action") == "block":
            continue
        content_terms = Counter(re.findall(r"\w+", content.casefold()))
        overlap = sum((query_terms & content_terms).values())
        if overlap / sum(query_terms.values()) < 0.35:
            continue
        ranked.append(
            (
                overlap,
                {
                    **item,
                    "citation": item["citation"],
                    "content": content,
                    "document_title": item["document_title"],
                    "course_code": course_code,
                    "page": int(item.get("page", 1)),
                    "paragraph": int(item.get("paragraph", index + 1)),
                    "score": round(min(0.95, 0.72 + overlap * 0.03), 4),
                },
            )
        )
    return [
        item
        for overlap, item in sorted(ranked, key=lambda row: row[0], reverse=True)[:top_k]
        if overlap
    ]

ACADEMIC_CHEATING_KEYWORDS = [
    "giải hộ",
    "giải giúp mình bài này",
    "làm hộ",
    "làm bài tập hộ",
    "cho mình đáp án",
    "cho em đáp án",
    "viết code hoàn chỉnh để nộp",
    "làm bài thi",
    "nộp lấy điểm",
    "giải bài tập để nộp",
    "đáp án câu",
]

DISPUTE_KEYWORDS = [
    "trích dẫn sai",
    "khiếu nại",
    "nhầm trang",
    "sai nguồn",
    "tài liệu lỗi thời",
    "dispute",
    "sai đoạn",
    "khiếu nại trích dẫn",
]


def _detect_cheating_intent(query: str) -> bool:
    """Kiểm tra xem sinh viên có đang yêu cầu giải hộ bài tập / thi cử để nộp điểm hay không."""
    return bool(evaluate_guardrails(query)["is_homework_cheat_attempt"])


def _detect_dispute_intent(query: str, request: dict[str, Any] | None = None) -> tuple[bool, str, str]:
    """
    Kiểm tra xem sinh viên có đang khiếu nại trích dẫn hay không.
    Trả về: (is_dispute, citation, reason)
    """
    if request and request.get("action") == "dispute_citation":
        return True, request.get("citation", ""), request.get("reason", "Khiếu nại qua API")

    query_lower = query.lower()
    is_dispute = any(kw in query_lower for kw in DISPUTE_KEYWORDS)
    if not is_dispute:
        return False, "", ""

    # Trích xuất citation từ query nếu có dạng [Tài liệu, Trang X, Đoạn Y]
    citation_match = re.search(r"\[([^\]]+)\]", query)
    citation = f"[{citation_match.group(1)}]" if citation_match else "[Trích dẫn được phản ánh trong câu hỏi]"
    reason = query

    return True, citation, reason


def qa_node(state: LearningGraphState) -> dict[str, Any]:
    """
    Study Support Agent Node:
    Thực thi truy xuất RAG học liệu, bảo vệ liêm chính học thuật và ghi nhận khiếu nại trích dẫn.
    """
    query = state.get("query") or ""
    if not query and state.get("messages"):
        last_msg = state["messages"][-1]
        query = last_msg.get("content", "") if isinstance(last_msg, dict) else getattr(last_msg, "content", "")

    guardrail = state.get("security_flags") or evaluate_guardrails(query)
    if guardrail.get("is_injection_attempt"):
        return {
            "current_node": "qa",
            "response": "Mình không thể làm theo chỉ dẫn nhằm thay đổi quy tắc hệ thống hoặc tiết lộ thông tin nội bộ. Bạn có thể đặt câu hỏi về nội dung môn học.",
            "analysis": "blocked_prompt_injection",
            "mode": "out_of_scope",
            "security_flags": guardrail,
            "retrieved_passages": [],
            "source_refs": [],
        }

    if _is_social_message(query):
        return {
            "current_node": "qa",
            "response": "Chào bạn! Mình sẵn sàng hỗ trợ nội dung của môn đang chọn. Bạn muốn hỏi phần nào?",
            "analysis": "social_conversation",
            "mode": "conversation",
            "security_flags": guardrail,
            "retrieved_passages": [],
            "source_refs": [],
        }

    if _is_obviously_out_of_scope(query):
        course_code = str(
            state.get("course_code")
            or state.get("course_id")
            or (state.get("request") or {}).get("course_code")
            or "đang chọn"
        ).strip()
        return {
            "current_node": "qa",
            "response": (
                f"Câu này không thuộc nội dung môn {course_code}, nên mình không dùng học liệu của môn "
                "để trả lời. Bạn hãy hỏi về khái niệm, bài học hoặc tài liệu của môn đang chọn."
            ),
            "analysis": "out_of_course_scope",
            "mode": "out_of_scope",
            "security_flags": guardrail,
            "retrieved_passages": [],
            "source_refs": [],
        }

    # 1. Task 2.3: Xử lý khiếu nại trích dẫn (Disputed Evidence)
    is_dispute, disputed_citation, dispute_reason = _detect_dispute_intent(query, state.get("request"))
    if is_dispute:
        dispute_res = record_disputed_evidence(
            state=state,
            citation=disputed_citation,
            reason=dispute_reason,
            student_note=query,
        )
        response_text = (
            f"### 📋 TIẾP NHẬN PHẢN HỒI KHIẾU NẠI TRÍCH DẪN\n\n"
            f"Chào bạn, Study Support Agent đã ghi nhận ý kiến đóng góp của bạn về trích dẫn **{disputed_citation}**.\n\n"
            f"- **Mã khiếu nại:** `{dispute_res['dispute']['dispute_id']}`\n"
            f"- **Lý do phản ánh:** {dispute_reason}\n"
            f"- **Trạng thái:** Đã đánh dấu cờ `flagged_for_review` và chuyển thông tin tới Giảng viên phụ trách môn học để đối soát phiên bản giáo trình.\n\n"
            f"Trong thời gian này, mình sẽ tạm thời không sử dụng đoạn trích dẫn này làm căn cứ chính. Nếu bạn có câu hỏi học thuật khác, cứ gửi cho mình nhé!"
        )
        return {
            "current_node": "qa",
            "response": response_text,
            "analysis": f"Đã ghi nhận khiếu nại trích dẫn {disputed_citation} vào state['disputed_evidence'].",
            "mode": "conversation",
            "disputed_evidence": dispute_res["disputed_evidence"],
            "audit_events": dispute_res["audit_events"],
            "output": {"citation_dispute": dispute_res["dispute"]},
        }

    # 2. Kiểm tra Liêm chính học thuật (Chế độ guided_help)
    is_cheating = bool(guardrail.get("is_homework_cheat_attempt"))
    if is_cheating:
        return {
            "current_node": "qa",
            "response": (
                "Mình không thể tạo đáp án hoặc bài hoàn chỉnh để nộp. "
                "Hãy gửi phần bạn đã thử và nói rõ bước đang vướng; mình sẽ kiểm tra lập luận, "
                "giải thích khái niệm liên quan và gợi ý bước tiếp theo bằng một ví dụ tương tự."
            ),
            "analysis": "guided_help (Academic Integrity Triggered)",
            "security_flags": guardrail,
            "retrieved_passages": [],
            "source_refs": [],
        }

    # 3. Task 2.2: Truy xuất tài liệu học tập từ Qdrant Vector Store
    request_context = state.get("request") or {}
    course_code = str(
        state.get("course_code") or state.get("course_id") or request_context.get("course_code") or ""
    ).strip()
    if not course_code:
        return {
            "current_node": "qa",
            "response": "Hãy chọn một môn học trước khi đặt câu hỏi. Chatbot chỉ sử dụng học liệu của môn đang chọn.",
            "analysis": "missing_course_scope",
            "mode": "conversation",
            "retrieved_passages": [],
            "source_refs": [],
        }
    rag_threshold = get_settings().rag_score_threshold
    search_query = retrieval_query(query, state.get("qa_history"))
    allowed_resource_ids = state.get("allowed_resource_ids")
    preferred_resource_ids = state.get("preferred_resource_ids") or []

    def retrieve(resource_ids: list[str] | None) -> dict[str, Any]:
        return search_course_materials(
            query=search_query,
            score_threshold=rag_threshold,
            course_code=course_code or None,
            institution_id=str(state.get("institution_id") or "") or None,
            course_id=str(state.get("course_id") or "") or None,
            **({"authorized_file_versions": state["authorized_file_versions"]} if "authorized_file_versions" in state else {}),
            **({"allowed_resource_ids": resource_ids} if resource_ids is not None else {}),
        )

    # Do uses a tiered scope: prefer the current assignment/module, then fall
    # back to other authorized chapters in the same course. The course filter
    # and live file versions remain mandatory in both tiers.
    initial_scope = preferred_resource_ids if preferred_resource_ids else allowed_resource_ids
    rag_result = retrieve(initial_scope)
    passages = _authorized_course_passages(state, rag_result.get("passages", []), course_code)
    is_insufficient = rag_result.get("insufficient_sources", False) or not passages
    preferred_overlap = _retrieval_scope_overlap(search_query, passages)
    can_expand_course = (
        bool(preferred_resource_ids)
        and allowed_resource_ids is not None
        and set(preferred_resource_ids) != set(allowed_resource_ids)
        and (is_insufficient or preferred_overlap == 0)
    )
    if can_expand_course:
        expanded_result = retrieve(allowed_resource_ids)
        expanded_passages = _authorized_course_passages(
            state, expanded_result.get("passages", []), course_code
        )
        if expanded_passages:
            rag_result = expanded_result
            passages = expanded_passages
            is_insufficient = expanded_result.get("insufficient_sources", False)
    if is_insufficient:
        passages = _state_resource_passages(state, search_query)
        if passages:
            rag_result = {
                "passages": passages,
                "insufficient_sources": False,
                "top_score": passages[0]["score"],
            }
            is_insufficient = False

    query_terms = _meaningful_terms(search_query)
    scope_overlap = _retrieval_scope_overlap(search_query, passages)
    if passages and len(query_terms) <= 12 and scope_overlap == 0:
        return {
            "current_node": "qa",
            "response": (
                f"Câu này không thuộc nội dung môn {course_code}, nên mình không dùng học liệu của môn "
                "để trả lời. Bạn hãy hỏi về khái niệm, bài học hoặc tài liệu của môn đang chọn."
            ),
            "analysis": "out_of_course_scope",
            "mode": "out_of_scope",
            "security_flags": guardrail,
            "retrieved_passages": [],
            "source_refs": [],
            "output": {"scope_overlap": scope_overlap},
        }

    source_refs = [
        {
            "id": f"{p.get('resource_id') or p.get('material_id') or p['citation']}:p{p['page']}:d{p['paragraph']}",
            "citation": p["citation"],
            "document_title": p["document_title"],
            "course_code": p["course_code"],
            "material_id": p.get("material_id", ""),
            "download_url": p.get("download_url", ""),
            "preview_url": p.get("preview_url", ""),
            "file_name": p.get("file_name", ""),
            "file_type": p.get("file_type", ""),
            "section_title": p.get("section_title", ""),
            "location_detail": p.get("location_detail", f"Trang {p['page']}"),
            "page": p["page"],
            "paragraph": p["paragraph"],
            "excerpt": str(p.get("content") or "")[:500],
            "score": p["score"],
        }
        for p in passages
    ]

    # Khởi tạo LLM
    if is_insufficient:
        return {"current_node": "qa", "response": "Mình chưa tìm thấy đủ học liệu được phép truy cập để trả lời có căn cứ. Hãy kiểm tra tài liệu môn học hoặc hỏi giảng viên.",
                "analysis": "insufficient_sources", "retrieved_passages": [], "source_refs": []}
    scope = hashlib.sha256(json.dumps({"student": state.get("student_id"), "institution": state.get("institution_id"),
                                     "course": state.get("course_id"), "versions": state.get("authorized_file_versions"),
                                     "passages": passages}, sort_keys=True, default=str).encode()).hexdigest()
    complexity = "complex" if len(query) > 400 or re.search(r"chứng minh|phản ví dụ|so sánh|proof|counterexample|transfer", query, re.I) else "simple"
    is_do_support = bool(state.get("do_session"))
    try:
        llm = get_agent_llm(
            temperature=0.2,
            max_tokens=min(get_settings().qa_max_output_tokens, 300),
            task="qa",
            complexity=complexity,
            cache_scope=scope if state.get("student_id") else None,
        )
    except Exception:
        llm = None

    user_prompt = grounded_prompt(query, passages, state.get("qa_history"), course_scope=course_code)
    analysis_mode = f"grounded_answer (Qdrant RAG: {len(passages)} passages, top score {rag_result.get('top_score', 0.0)})"

    # 5. Gọi LLM để sinh câu trả lời
    if llm:
        try:
            system_prompt = GROUNDED_QA_SYSTEM_PROMPT
            if is_do_support:
                system_prompt += (
                    "\nTrong phiên Do, ưu tiên câu trả lời ngắn khoảng 150–250 token; "
                    "đưa chi tiết bổ sung vào nguồn thay vì lặp lại đoạn trích dài."
                )
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
            sink = _stream_sink.get()
            if sink:
                streamed: list[str] = []
                pending_marker = ""
                for chunk in llm.stream(messages):
                    text = message_delta_text(chunk.content)
                    if text:
                        streamed.append(text)
                        pending_marker += text
                        partial = re.search(r"\[(?:S\d*)?$", pending_marker, re.I)
                        cutoff = partial.start() if partial else len(pending_marker)
                        ready, pending_marker = pending_marker[:cutoff], pending_marker[cutoff:]
                        if ready:
                            sink(expand_source_markers(ready, passages))
                if pending_marker:
                    sink(expand_source_markers(pending_marker, passages))
                response_text = expand_source_markers("".join(streamed), passages)
            else:
                res = llm.invoke(messages)
                response_text = expand_source_markers(message_text(res.content), passages)
        except Exception as exc:
            logger.warning("qa_llm_invocation_failed error_type=%s", type(exc).__name__)
            response_text = "Mình chưa thể tạo câu trả lời lúc này. Hãy thử lại sau."
    else:
        response_text = "Mình chưa thể tạo câu trả lời lúc này. Hãy thử lại sau."

    citation_validation = citation_check(response_text, passages) if passages else {
        "valid": False,
        "citations": [],
        "valid_citations": [],
        "invalid_citations": [],
        "coverage": 0.0,
    }

    # Không giữ lại nội dung do LLM sinh nếu citation không hợp lệ. Việc chỉ
    # đính kèm một nguồn hợp lệ vào câu trả lời chưa được kiểm chứng có thể làm
    # người học hiểu nhầm toàn bộ nội dung phía trên đã được nguồn đó hỗ trợ.
    if passages and not citation_validation["valid"]:
        response_text = extractive_fallback(
            passages,
            query=search_query,
            max_chars=320 if is_do_support else 360,
            max_passages=2,
        )
        citation_validation = citation_check(response_text, passages)

    # Làm sạch triệt để các tiêu đề chế độ kỹ thuật (như ### `grounded_answer`) và chuẩn hóa dấu ### thành text đẹp
    response_text = re.sub(
        r"^(#+\s*)?`?(grounded_answer|insufficient_sources|guided_help)`?\s*\n*",
        "",
        response_text.strip(),
        flags=re.IGNORECASE,
    )
    # Chuyển các dấu ### hoặc #### ở đầu dòng thành text in đậm **Tiêu đề**
    response_text = re.sub(r"^#{1,6}\s*(.+)$", r"**\1**", response_text, flags=re.MULTILINE).strip()
    cited = set(citation_validation.get("valid_citations") or [])
    source_refs = [item for item in source_refs if item["citation"] in cited]

    return {
        "current_node": "qa",
        "response": response_text,
        "analysis": f"Study Support Agent phản hồi ở chế độ: {analysis_mode}",
        "retrieved_passages": passages,
        "source_refs": source_refs,
        "disputed_evidence": state.get("disputed_evidence", []),
        "security_flags": guardrail,
        "output": {"citation_validation": citation_validation},
    }
