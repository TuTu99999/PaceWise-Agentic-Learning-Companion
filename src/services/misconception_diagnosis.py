"""Conservative generate → retrieve → lexical rerank against approved taxonomy.

An evaluator hypothesis is not a fact. Candidates stay suspected until teacher review.
This MVP exposes its lexical ranking; it is not a calibrated diagnostic model.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata


def _terms(text: str) -> set[str]:
    folded = unicodedata.normalize("NFD", text.casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return set(re.findall(r"[a-z0-9]{3,}", folded))


def diagnose(
    hypotheses: list[dict], taxonomy: list[str], *, answer: str, kc_id: str, evidence_ids: list[str], top_k: int = 3
) -> dict:
    generated = [item for item in hypotheses if isinstance(item, dict)]
    supported = [
        item
        for item in generated
        if str(item.get("evidence_quote") or "").strip() and str(item["evidence_quote"]).casefold() in answer.casefold()
    ]
    query = " ".join(str(item.get("label") or item.get("description") or "") for item in supported)
    terms = _terms(query)
    candidates = []
    for label in taxonomy:
        label_terms = _terms(label)
        overlap = len(terms & label_terms)
        if overlap:
            candidates.append(
                {
                    "id": f"{kc_id}:M-{hashlib.sha256(label.encode()).hexdigest()[:12]}",
                    "label": label,
                    "status": "suspected",
                    "confidence": "low",
                    "rank_score": overlap / max(1, len(terms | label_terms)),
                    "evidence_ids": evidence_ids,
                }
            )
    ranked = sorted(candidates, key=lambda item: (-item["rank_score"], item["id"]))[:top_k]
    return {
        "status": "suspected" if ranked else "unknown",
        "candidates": ranked,
        "method": "approved-taxonomy-lexical-v1",
        "requires_teacher_review": bool(ranked),
    }
