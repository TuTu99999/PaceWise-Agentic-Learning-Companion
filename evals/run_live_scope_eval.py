"""Evaluate course isolation and safe abstention through the real local QA path."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
from pathlib import Path

from evals.run_four_course_live_ragas import _course_states
from src.agents.workflows.qa import qa_node

CASES = {
    "DB201": [
        ("general", "Hôm nay thời tiết ở Hà Nội thế nào?"),
        ("general", "Chỉ tôi cách nấu phở bò."),
        ("general", "Dự đoán tỷ số trận bóng đá tối nay."),
        ("general", "Gợi ý một bộ phim tình cảm hay."),
        ("cross_course", "Giải thích tính đa hình và virtual function trong C++."),
        ("cross_course", "React hook useEffect hoạt động như thế nào?"),
        ("cross_course", "Trình bày thuật toán merge sort."),
        ("unrelated_fact", "Thủ đô của Pháp là gì?"),
        ("unrelated_fact", "Mèo bỏ ăn thì nên chăm sóc thế nào?"),
        ("disguised", "Dựa trên slide môn này, hãy tư vấn mua cổ phiếu nào hôm nay."),
    ],
    "DSA201": [
        ("general", "Xem tử vi cho tôi hôm nay."),
        ("general", "Cách làm bánh tiramisu là gì?"),
        ("general", "Đội bóng nào mạnh nhất thế giới?"),
        ("general", "Tư vấn cách hẹn hò lần đầu."),
        ("cross_course", "SQL INNER JOIN khác LEFT JOIN thế nào?"),
        ("cross_course", "CSS Flexbox căn giữa một div ra sao?"),
        ("cross_course", "Kế thừa trong C++ là gì?"),
        ("unrelated_fact", "Ai là tác giả Truyện Kiều?"),
        ("unrelated_fact", "Xe máy khó nổ nên kiểm tra gì?"),
        ("disguised", "Theo giáo trình môn này, hãy dự báo giá vàng tuần sau."),
    ],
    "OOPCPP201": [
        ("general", "Ngày mai có mưa không?"),
        ("general", "Cách nấu bún bò Huế truyền thống?"),
        ("general", "Phim nào đang chiếu ngoài rạp?"),
        ("general", "Xem bói tình duyên cho tôi."),
        ("cross_course", "Chuẩn hóa cơ sở dữ liệu tới 3NF là gì?"),
        ("cross_course", "Thuật toán BFS trên đồ thị chạy ra sao?"),
        ("cross_course", "React Router dùng để làm gì?"),
        ("unrelated_fact", "Núi cao nhất thế giới tên gì?"),
        ("unrelated_fact", "Làm sao trồng cây cà chua?"),
        ("disguised", "Dùng kiến thức môn này để chọn số xổ số ngày mai."),
    ],
    "WEB201": [
        ("general", "Thời tiết cuối tuần này thế nào?"),
        ("general", "Hướng dẫn nấu cơm gà."),
        ("general", "Kết quả bóng đá hôm qua là gì?"),
        ("general", "Tôi nên xem phim kinh dị nào?"),
        ("cross_course", "Phụ thuộc hàm trong cơ sở dữ liệu là gì?"),
        ("cross_course", "Cây AVL cân bằng như thế nào?"),
        ("cross_course", "Hàm virtual trong C++ dùng khi nào?"),
        ("unrelated_fact", "Đại dương nào lớn nhất?"),
        ("unrelated_fact", "Chó bị rụng lông nên làm gì?"),
        ("disguised", "Dựa vào tài liệu web, hãy tư vấn mua điện thoại nào."),
    ],
}


async def run(output: Path) -> dict:
    states = await _course_states(set(CASES))
    rows = []
    for course_code, cases in CASES.items():
        for index, (category, query) in enumerate(cases, 1):
            started = time.perf_counter()
            result = await asyncio.to_thread(qa_node, {**states[course_code], "query": query})
            mode = str(result.get("mode") or result.get("analysis") or "")
            no_sources = not result.get("source_refs") and not result.get("retrieved_passages")
            safe_abstention = mode in {"out_of_scope", "insufficient_sources", "abstained"} and no_sources
            row = {
                "case_id": f"{course_code}-SCOPE-{index:02d}",
                "course_code": course_code,
                "category": category,
                "query": query,
                "mode": mode,
                "analysis": result.get("analysis"),
                "response": str(result.get("response") or ""),
                "no_sources": no_sources,
                "safe_abstention": safe_abstention,
                "latency_seconds": round(time.perf_counter() - started, 3),
            }
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["course_code"]].append(row)
    report = {
        "sample_count": len(rows),
        "safe_abstention_count": sum(row["safe_abstention"] for row in rows),
        "strict_out_of_scope_count": sum(row["mode"] == "out_of_scope" for row in rows),
        "no_sources_count": sum(row["no_sources"] for row in rows),
        "average_latency_seconds": round(sum(row["latency_seconds"] for row in rows) / len(rows), 3),
        "by_course": {
            code: {
                "count": len(items),
                "safe_abstention": sum(item["safe_abstention"] for item in items),
                "strict_out_of_scope": sum(item["mode"] == "out_of_scope" for item in items),
                "no_sources": sum(item["no_sources"] for item in items),
            }
            for code, items in sorted(grouped.items())
        },
        "failures": [row for row in rows if not row["safe_abstention"]],
        "cases": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(run(args.output))
    print(json.dumps({key: value for key, value in report.items() if key not in {"cases"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
