"""Offline report and optional small real-model smoke eval without touching LMS/workspaces."""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.adaptive_evaluation import run_adaptive_evaluation  # noqa: E402
from src.agents.evaluation import run_full_evaluation  # noqa: E402
from src.agents.workflows.understanding import understanding_node  # noqa: E402
from src.config import get_settings  # noqa: E402

LIVE_CASES = [
    (
        "short_correct_explanation",
        "explain",
        "Giải thích tính bắc cầu của quan hệ R.",
        "Nếu xRy và yRz cùng đúng thì xRz phải đúng; điều kiện này phải đúng với mọi x, y, z trong tập đang xét.",
        True,
    ),
    (
        "symmetry_not_transitivity",
        "explain",
        "Giải thích tính bắc cầu của quan hệ R.",
        "Bắc cầu nghĩa là nếu xRy thì yRx. Chỉ cần kiểm tra các cặp đảo chiều.",
        False,
    ),
    (
        "self_report_only",
        "explain",
        "Giải thích tính bắc cầu của quan hệ R.",
        "Em đã hiểu hoàn toàn rồi, chắc chắn em làm được.",
        False,
    ),
    (
        "application_missing_pair",
        "application",
        "Trên A={1,2,3}, R={(1,2),(2,3)} có bắc cầu không? Nêu bằng chứng.",
        "Không. Vì (1,2) và (2,3) thuộc R nhưng (1,3) không thuộc R. Đây là phản ví dụ cho điều kiện bắc cầu.",
        True,
    ),
    (
        "right_answer_wrong_reasoning",
        "application",
        "Trên A={1,2,3}, R={(1,2),(2,3)} có bắc cầu không? Nêu bằng chứng.",
        "Không bắc cầu vì không có (2,1), nên quan hệ không đối xứng. Quan hệ không đối xứng thì không bắc cầu.",
        False,
    ),
    (
        "transfer_divisibility",
        "transfer",
        "Quan hệ aRb khi a chia hết b trên số nguyên dương có bắc cầu không? Chứng minh.",
        "Có. Nếu a chia hết b và b chia hết c thì a=kb, b=mc với k,m nguyên dương; suy ra a=kmc nên a chia hết c.",
        True,
    ),
    (
        "transfer_addition_error",
        "transfer",
        "Quan hệ aRb khi a chia hết b trên số nguyên dương có bắc cầu không? Chứng minh.",
        "Có vì a=b+k và b=c+m nên a=c+k+m; đây là định nghĩa chia hết và chứng minh bắc cầu.",
        False,
    ),
    (
        "why_universal_condition",
        "why",
        "Vì sao chỉ một chuỗi xRy, yRz mà thiếu xRz đã đủ kết luận R không bắc cầu?",
        "Định nghĩa bắc cầu yêu cầu điều kiện đúng với mọi bộ ba. Một bộ ba vi phạm là phản ví dụ nên bác bỏ mệnh đề phổ quát.",
        True,
    ),
]


def live_eval() -> dict:
    settings = get_settings()
    if not settings.openai_api_key:
        return {"status": "not_run", "reason": "no_model_credentials"}
    cases = []
    for identifier, stage, question, answer, expected in LIVE_CASES:
        start = time.perf_counter()
        result = understanding_node(
            {
                "query": answer,
                "request": {"question": question, "assessment_stage": stage},
                "approved_rubric": [
                    {
                        "criterion_id": "correct",
                        "description": "Định nghĩa và kết luận phải đúng với quan hệ được hỏi; không nhầm bắc cầu với đối xứng.",
                    },
                    {
                        "criterion_id": "reason",
                        "description": "Lập luận phải hỗ trợ kết luận, chỉ rõ điều kiện hoặc phản ví dụ; tự báo đã hiểu không là bằng chứng.",
                    },
                ],
            }
        )
        assessment = result.get("assessment_result") or {}
        dimension = {"explain": "conceptual", "why": "reasoning", "application": "application", "transfer": "transfer"}[
            stage
        ]
        actual = (
            result.get("status") != "awaiting_teacher"
            and (assessment.get("dimensions") or {}).get(dimension) == "passed"
        )
        cases.append(
            {
                "id": identifier,
                "stage": stage,
                "question": question,
                "answer": answer,
                "expected_pass": expected,
                "actual_pass": actual,
                "matches_label": expected == actual,
                "latency_seconds": round(time.perf_counter() - start, 3),
                "status": result.get("status"),
                "assessment": assessment,
                "feedback": result.get("response"),
            }
        )
        cases[-1]["model_status"] = (result.get("output") or {}).get("model_status")
        cases[-1]["model_error_type"] = (result.get("output") or {}).get("model_error_type")
        print(f"live:{identifier} expected={expected} actual={actual} status={result.get('status')}", flush=True)
        if len(cases) >= 2 and all(case.get("model_status") == "unavailable" for case in cases[-2:]):
            break
    unavailable = any(case.get("model_status") == "unavailable" for case in cases)
    return {
        "status": "provider_unavailable" if unavailable else "executed",
        "model": settings.model_name,
        "sample_count": len(cases),
        "planned_sample_count": len(LIVE_CASES),
        "cases": cases,
        "abstention_rate": sum(case["status"] == "awaiting_teacher" for case in cases) / len(cases),
        "responded_case_count": sum(case.get("model_status") == "responded" for case in cases),
        "label_agreement": None if unavailable else sum(case["matches_label"] for case in cases) / len(cases),
        "false_pass_count": sum(case["actual_pass"] and not case["expected_pass"] for case in cases),
        "limitations": [
            "8 developer-authored mathematical cases, not SME calibration or pilot.",
            "No learner identity/data submitted. No gradebook/workspace mutations.",
            "Model abstention and incorrect grading need separate review; agreement is not educational validity.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evals/reports/adaptive-assessment-2026-10-08.json")
    parser.add_argument("--live-model", action="store_true")
    args = parser.parse_args()
    report = {
        "adaptive": run_adaptive_evaluation(),
        "legacy_engineering": run_full_evaluation(),
        "live_model": live_eval() if args.live_model else {"status": "not_run", "reason": "explicit_flag_required"},
        "metric_definitions": {
            "legacy.diagnosis_macro_f1": "Parser recovery of fixture-embedded labels, NOT student diagnosis accuracy.",
            "legacy.false_mastery_acceptance_rate": "Closed-answer false acceptance on synthetic cases, NOT population false mastery.",
        },
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(path),
                "adaptive_sample_count": report["adaptive"]["sample_count"],
                "adaptive_overall_pass": report["adaptive"]["overall_pass"],
                "legacy_overall_pass": report["legacy_engineering"]["overall_pass"],
                "live_status": report["live_model"]["status"],
            }
        )
    )


if __name__ == "__main__":
    main()
