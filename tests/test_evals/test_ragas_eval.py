import json

import pytest

from evals.run_ragas_eval import QUALITY_THRESHOLDS, load_samples


def test_release_gate_requires_high_answer_relevancy():
    assert QUALITY_THRESHOLDS["answer_relevancy"] == 0.9


def test_ragas_dataset_requires_at_least_one_hundred_samples(tmp_path):
    path = tmp_path / "small.jsonl"
    sample = {
        "user_input": "Câu hỏi",
        "response": "Câu trả lời",
        "retrieved_contexts": ["Tài liệu"],
        "reference": "Đáp án tham chiếu",
    }
    path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="at least 100 samples"):
        load_samples(path)


def test_ragas_dataset_accepts_one_hundred_complete_samples(tmp_path):
    path = tmp_path / "valid.jsonl"
    sample = {
        "user_input": "Câu hỏi",
        "response": "Câu trả lời",
        "retrieved_contexts": ["Tài liệu"],
        "reference": "Đáp án tham chiếu",
    }
    path.write_text(
        "\n".join(json.dumps({**sample, "user_input": f"Câu hỏi {i}"}, ensure_ascii=False) for i in range(100)),
        encoding="utf-8",
    )

    assert len(load_samples(path)) == 100


def test_pilot_requires_explicit_lower_minimum_and_valid_contexts(tmp_path):
    path = tmp_path / 'pilot.jsonl'
    sample = dict(user_input='Question', response='Answer', retrieved_contexts=['Source'], reference='Reference')
    path.write_text('\n'.join(json.dumps({**sample, 'user_input': f'Question {i}'}) for i in range(3)), encoding='utf-8')
    assert len(load_samples(path, min_samples=3)) == 3
    sample['retrieved_contexts'] = 'not a list'
    path.write_text('\n'.join(json.dumps(sample) for _ in range(3)), encoding='utf-8')
    with pytest.raises(ValueError, match='invalid contexts'):
        load_samples(path, min_samples=3)
