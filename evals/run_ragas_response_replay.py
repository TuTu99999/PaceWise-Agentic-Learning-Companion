"""Regenerate QA answers from a fixed, previously retrieved RAGAS dataset.

This isolates answer-generation quality from course lifecycle and retrieval drift.
It is intended for approved evaluation data only and never reads learner state.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from unittest.mock import patch

from src.agents.workflows.qa import qa_node


def _passages(contexts: list[str], sample_index: int) -> list[dict]:
    return [
        {
            "resource_id": f"eval:{sample_index}:{context_index}",
            "document_title": "RAGAS evaluation source",
            "citation": f"[RAGAS evaluation source, Trang {context_index}, Đoạn 1]",
            "content": content,
            "course_code": "RAGAS-EVAL",
            "page": context_index,
            "paragraph": 1,
            "score": 1.0,
        }
        for context_index, content in enumerate(contexts, 1)
    ]


def replay(input_path: Path) -> tuple[list[dict], list[dict]]:
    source_rows = [
        json.loads(line)
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    samples: list[dict] = []
    cases: list[dict] = []
    for sample_index, source in enumerate(source_rows, 1):
        passages = _passages(source["retrieved_contexts"], sample_index)
        started = time.perf_counter()
        with patch(
            "src.agents.workflows.qa.search_course_materials",
            return_value={"passages": passages, "insufficient_sources": False, "top_score": 1.0},
        ):
            result = qa_node(
                {
                    "query": source["user_input"],
                    "course_code": "RAGAS-EVAL",
                    "allowed_resource_ids": [item["resource_id"] for item in passages],
                }
            )
        citation = (result.get("output") or {}).get("citation_validation") or {}
        if not result.get("source_refs") or not citation.get("valid"):
            raise RuntimeError(f"sample {sample_index} did not produce a grounded answer")
        samples.append(
            {
                "user_input": source["user_input"],
                "response": result["response"],
                "retrieved_contexts": source["retrieved_contexts"],
                "reference": source["reference"],
            }
        )
        cases.append(
            {
                "sample": sample_index,
                "latency_seconds": round(time.perf_counter() - started, 3),
                "response_words": len(result["response"].split()),
                "source_count": len(result["source_refs"]),
            }
        )
        print(json.dumps(cases[-1]), flush=True)
    return samples, cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    samples, cases = replay(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(json.dumps(sample, ensure_ascii=False) for sample in samples) + "\n",
        encoding="utf-8",
    )
    args.report.write_text(
        json.dumps(
            {
                "mode": "fixed_retrieval_context_answer_replay",
                "sample_count": len(samples),
                "cases": cases,
                "limitations": [
                    "Measures current answer generation against stored real-index contexts.",
                    "Does not re-measure live retrieval because the source course is archived.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
