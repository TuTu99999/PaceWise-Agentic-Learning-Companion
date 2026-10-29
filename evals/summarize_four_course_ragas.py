"""Join RAGAS per-sample scores back to the four course labels."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("samples", type=Path)
    parser.add_argument("ragas", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    samples = _jsonl(args.samples)
    ragas = json.loads(args.ragas.read_text(encoding="utf-8"))
    scores = ragas["per_sample"]
    if len(samples) != len(scores):
        raise ValueError(f"Sample/score mismatch: {len(samples)} != {len(scores)}")
    metric_names = list(ragas["metrics"])
    grouped: dict[str, list[dict]] = defaultdict(list)
    joined = []
    for sample, score in zip(samples, scores, strict=True):
        row = {
            "case_id": sample["case_id"],
            "course_code": sample["course_code"],
            "retrieval_grounded": sample.get("retrieved_contexts") != ["[NO_CONTEXT_RETRIEVED]"],
            **{name: score.get(name) for name in metric_names},
        }
        joined.append(row)
        grouped[row["course_code"]].append(row)

    def aggregate(rows: list[dict]) -> dict:
        result = {"count": len(rows)}
        for name in metric_names:
            values = [float(row[name]) for row in rows if row.get(name) is not None and math.isfinite(float(row[name]))]
            result[name] = round(sum(values) / len(values), 4) if values else None
            result[f"{name}_scored"] = len(values)
        return result

    report = {
        "sample_count": len(joined),
        "overall": {"metrics": ragas["metrics"], "scored_samples": ragas["scored_samples"]},
        "grounded_only": aggregate([row for row in joined if row["retrieval_grounded"]]),
        "by_course": {
            code: {
                "all_samples": aggregate(rows),
                "grounded_only": aggregate([row for row in rows if row["retrieval_grounded"]]),
            }
            for code, rows in sorted(grouped.items())
        },
        "per_sample": joined,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "per_sample"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
