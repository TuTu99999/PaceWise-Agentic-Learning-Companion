import itertools
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.services.question_design import (
    MAX_LLM_CALLS,
    MAX_SESSION_ITEMS,
    PROPERTIES,
    QuestionDesign,
    generate_candidate,
    instance_bank,
    preview_design,
    relation_facts,
)


def parent(mode="relation_template", property_name="transitive"):
    return {
        "assessment_id": "Q-1",
        "rubric_version": 1,
        "question": "Explain relation transitivity",
        "knowledge_component_ids": ["relation.transitivity"],
        "source": "Approved course source",
        "approved_rubric": [
            {"criterion_id": "c1", "description": "Correct definition"},
            {"criterion_id": "c2", "description": "Grounded reasoning"},
        ],
        "question_design": {
            "mode": mode,
            "relation_property": property_name,
            "reference_text": "A relation is transitive if aRb and bRc imply aRc.",
        },
    }


@pytest.mark.parametrize("property_name", PROPERTIES)
def test_oracle_matches_independent_truth_table_for_every_three_element_relation(property_name):
    elements = ["a", "b", "c"]
    all_pairs = list(itertools.product(elements, repeat=2))
    for mask in range(1 << len(all_pairs)):
        pairs = {pair for index, pair in enumerate(all_pairs) if mask & (1 << index)}
        reflexive = all((a, a) in pairs for a in elements)
        symmetric = all(((a, b) in pairs) == ((b, a) in pairs) for a in elements for b in elements)
        antisymmetric = all(a == b or not ((a, b) in pairs and (b, a) in pairs) for a in elements for b in elements)
        transitive = all(
            not ((a, b) in pairs and (b, c) in pairs) or (a, c) in pairs
            for a in elements
            for b in elements
            for c in elements
        )
        expected = {
            "reflexive": reflexive,
            "symmetric": symmetric,
            "antisymmetric": antisymmetric,
            "transitive": transitive,
            "equivalence": reflexive and symmetric and transitive,
            "partial_order": reflexive and antisymmetric and transitive,
        }
        assert relation_facts(elements, [list(pair) for pair in pairs])[property_name] == expected[property_name]


@pytest.mark.parametrize("property_name", PROPERTIES)
def test_transfer_variant_is_solvable_and_closure_is_minimal(property_name):
    for index in range(30):
        item = generate_candidate(
            {"stage": "transfer"}, [parent(property_name=property_name)], "relation.transitivity", f"learner-{index}"
        )
        facts = item["expected_facts"]
        elements, pairs = facts["elements"], facts["pairs"]
        if property_name == "antisymmetric":
            a, b = pairs[0]
            assert relation_facts(elements, [*pairs, [b, a]])[property_name] is False
            continue
        additions = facts["minimal_additions"]
        assert additions, "Transfer must require a nontrivial repair, not zero changes"
        assert relation_facts(elements, [*pairs, *additions])[property_name]
        for remove in additions:
            assert not relation_facts(elements, [*pairs, *(pair for pair in additions if pair != remove)])[
                property_name
            ]


def test_generation_is_session_scoped_bounded_and_source_approval_versioned():
    bank = [parent()]
    state = {"stage": "application"}
    first = generate_candidate(state, bank, "relation.transitivity", "student-1")
    second = generate_candidate(state, bank, "relation.transitivity", "student-2")
    assert first["question"] != second["question"]
    state["generated_items"] = {first["assessment_id"]: first}
    assert first in instance_bank(bank, state)
    assert instance_bank(instance_bank(bank, state), state) == instance_bank(bank, state)
    assert first not in instance_bank([{**bank[0], "rubric_version": 2}], state)
    assert first not in instance_bank([], state)
    assert generate_candidate(state, bank, "another-course-kc", "student-1") is None
    state["generated_items"] = {str(i): first for i in range(MAX_SESSION_ITEMS)}
    assert generate_candidate(state, bank, "relation.transitivity", "student-1") is None


def test_design_rejects_unbounded_or_unreferenced_llm_configuration():
    with pytest.raises(ValidationError):
        QuestionDesign(mode="llm_followup", reference_text="tiny")
    with pytest.raises(ValidationError):
        QuestionDesign(stages=["recall", "recall"])
    with pytest.raises(ValidationError):
        QuestionDesign(mode="arbitrary", reference_text="x" * 6000)


def test_llm_followup_is_formative_and_never_trusts_model_rubric_or_source(monkeypatch):
    class FakeModel:
        def invoke(self, messages):
            assert "student answer" in messages[-1].content
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "question": "Can you explain why the missing pair is necessary?",
                        "kc_id": "relation.transitivity",
                        "stage": "explain",
                        "rubric": ["Everyone passes"],
                        "source": "invented",
                    }
                )
            )

    def factory(**kwargs):
        assert kwargs == {"temperature": 0.2, "timeout": 8.0, "max_retries": 0, "max_tokens": 350, "task": "question_design"}
        return FakeModel()

    monkeypatch.setattr("src.services.question_design.get_agent_llm", factory)
    bank = [parent(mode="llm_followup")]
    state = {"stage": "explain", "previous_answer": "student answer"}
    item = generate_candidate(state, bank, "relation.transitivity", "student")
    assert item["formative_only"] and item["source"] == bank[0]["source"]
    assert item["approved_rubric"][0]["description"] == "Correct definition"
    state["llm_calls"] = MAX_LLM_CALLS
    assert generate_candidate(state, bank, "relation.transitivity", "student") is None


def test_provider_timeout_falls_back_without_persisting_unused_question(monkeypatch):
    monkeypatch.setattr("src.services.question_design.get_agent_llm", lambda **_: (_ for _ in ()).throw(TimeoutError()))
    state = {"stage": "explain", "previous_answer": "student answer"}
    assert generate_candidate(state, [parent(mode="llm_followup")], "relation.transitivity", "student") is None
    assert state["llm_calls"] == 1
    assert not state.get("generated_items")


def test_teacher_preview_is_ephemeral_and_contains_oracle_for_review():
    examples = preview_design(QuestionDesign(), ["Definition", "Reasoning"], "Source")
    assert examples == []
    examples = preview_design(QuestionDesign(mode="relation_template"), ["Definition", "Reasoning"], "Source")
    assert len(examples) == 5
    assert all("expected_facts" in example for example in examples)


def test_malformed_legacy_design_falls_back_instead_of_crashing():
    invalid = {**parent(), "question_design": {"mode": "unknown"}}
    assert generate_candidate({"stage": "recall"}, [invalid], "relation.transitivity", "student") is None


def test_generation_timeout_is_configured_on_http_client_construction(monkeypatch):
    from src.agents.llm import get_agent_llm

    captured = {}

    def construct(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("src.agents.llm.ChatOpenAI", construct)
    get_agent_llm(temperature=0.2, timeout=8.0, max_retries=0, max_tokens=350)
    assert captured["timeout"] == 8.0
    assert captured["max_retries"] == 0
    assert captured["max_tokens"] == 350
