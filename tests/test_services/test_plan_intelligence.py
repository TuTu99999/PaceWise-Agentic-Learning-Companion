from src.services.plan_intelligence import (
    assignment_structure,
    build_template_milestones,
    enrich_task_milestones,
    estimate_workload,
    evaluate_plan_quality,
    normalize_reflection_feedback,
    normalize_rubric_criteria,
)


def _assignment(**overrides):
    base = {
        "id": "math:3",
        "title": "Binary relations report",
        "deadline": "2026-10-09",
        "description": "Explain equivalence relations and provide a justified example.",
        "grading_type": "points",
        "estimated_hours": 2,
        "deliverable": "PDF report",
        "knowledge_components": [
            {"id": "reflexive", "name": "Reflexive relation"},
            {"id": "transitive", "name": "Transitive relation"},
        ],
        "rubric": {
            "id": 7,
            "criteria": [
                {"id": "R1", "description": "Correct definition", "points": 4},
                {
                    "id": "R2",
                    "description": "Justified example",
                    "points": 6,
                    "knowledge_components": ["transitive"],
                },
            ],
        },
    }
    return {**base, **overrides}


def _milestones():
    return [
        {
            "milestoneId": "M1",
            "title": "Write the correct definition",
            "deliverable": "Definition paragraph",
            "estimatedMin": 45,
            "dependsOn": [],
            "sourceRefs": ["assignment:math:3"],
            "knowledgeComponents": ["reflexive"],
            "decompositionSource": "llm",
        },
        {
            "milestoneId": "M2",
            "title": "Create a justified transitive example",
            "deliverable": "Worked example",
            "estimatedMin": 45,
            "dependsOn": ["M1"],
            "sourceRefs": ["assignment:math:3"],
            "knowledgeComponents": ["transitive"],
            "decompositionSource": "llm",
        },
    ]


def test_normalize_rubric_preserves_criteria_weights_and_provenance():
    criteria = normalize_rubric_criteria(_assignment())

    assert [item["criterionId"] for item in criteria] == ["R1", "R2"]
    assert [item["weight"] for item in criteria] == [4.0, 6.0]
    assert criteria[1]["sourceRef"] == "rubric:7#criterion=R2"


def test_metadata_only_rubric_does_not_invent_criteria():
    assert normalize_rubric_criteria(_assignment(rubric={"id": 7, "title": "Report"})) == []


def test_structure_router_uses_template_only_for_well_structured_assignment():
    result = assignment_structure({**_assignment(), "dependencies": ["chapter-2"]})
    assert result["route"] == "template"
    assert result["score"] >= 7


def test_template_milestones_keep_task_id_dependencies_and_source():
    milestones = build_template_milestones(_assignment(), target_minutes=120)
    assert sum(item["estimated_minutes"] for item in milestones) == 120
    assert all(item["task_id"] == "math:3" for item in milestones)
    assert milestones[1]["depends_on"] == [milestones[0]["milestone_id"]]
    assert milestones[0]["source_refs"][0] == "assignment:math:3"
    assert any(reference.startswith("rubric:7#criterion=") for reference in milestones[0]["source_refs"])


def test_rubric_decomposition_allocates_more_time_to_harder_heavier_parts_without_changing_total():
    assignment = _assignment(
        rubric={
            "id": 8,
            "criteria": [
                {"id": "easy", "description": "Trình bày và định dạng", "points": 10},
                {"id": "hard", "description": "Phân tích, thiết kế và cài đặt thuật toán", "points": 60},
                {"id": "test", "description": "Kiểm thử các trường hợp ngoại lệ", "points": 30},
            ],
        }
    )

    milestones = build_template_milestones(assignment, target_minutes=150)

    by_criterion = {item["rubric_criteria"][0]: item for item in milestones}
    assert sum(item["estimated_minutes"] for item in milestones) == 150
    assert by_criterion["hard"]["estimated_minutes"] > by_criterion["test"]["estimated_minutes"]
    assert by_criterion["test"]["estimated_minutes"] > by_criterion["easy"]["estimated_minutes"]
    assert by_criterion["hard"]["difficulty"] == "khó"
    assert by_criterion["easy"]["difficulty"] == "dễ"
    assert all(item["decomposition_source"] == "rubric_evidence" for item in milestones)


def test_rubric_evidence_routes_to_deterministic_decomposition_without_seven_signals():
    result = assignment_structure(
        _assignment(deliverable=None, knowledge_components=[], dependencies=[])
    )
    assert result["score"] < 7
    assert result["route"] == "template"


def test_multi_question_brief_routes_to_ai_and_fallback_keeps_every_question_with_fixed_total():
    assignment = _assignment(
        rubric=None,
        planning_evidence_type="assignment_brief",
        assignment_parts=[
            {
                "partId": f"S2-P{index}",
                "label": f"Câu {index}",
                "content": content,
                "sourceRef": f"file:9#exercise=2&part=S2-P{index}",
            }
            for index, content in enumerate(
                [
                    "Thiết kế lược đồ quan hệ và giải thích khóa.",
                    "Viết truy vấn JOIN lấy dữ liệu theo yêu cầu.",
                    "Kiểm thử truy vấn với dữ liệu biên.",
                ],
                start=1,
            )
        ],
    )

    assert assignment_structure(assignment)["route"] == "llm"
    milestones = build_template_milestones(assignment, target_minutes=120)

    assert sum(item["estimated_minutes"] for item in milestones) == 120
    assert {
        part_id
        for item in milestones
        for part_id in item["assignment_part_ids"]
    } == {"S2-P1", "S2-P2", "S2-P3"}
    assert all(item["decomposition_source"] == "assignment_question_evidence" for item in milestones)
    assert milestones[1]["depends_on"] == [milestones[0]["milestone_id"]]


def test_large_assignment_group_uses_compact_label_summary_without_losing_parts():
    labels = [
        "Câu 1", "Câu 2", "Câu 3", "Câu 4", "Câu 5",
        "Yêu cầu 1", "Yêu cầu 2", "Yêu cầu 3", "Thành phần 1", "Thành phần 2",
    ]
    assignment = _assignment(
        rubric=None,
        planning_evidence_type="assignment_brief",
        assignment_parts=[
            {
                "partId": f"part-{index}",
                "label": label,
                "content": f"Nội dung cần làm cho {label}",
                "sourceRef": f"file:9#part={index}",
            }
            for index, label in enumerate(labels, start=1)
        ],
    )

    milestones = build_template_milestones(assignment, target_minutes=30)

    assert len(milestones) == 1
    assert milestones[0]["title"].startswith("Làm 5 câu · 3 yêu cầu · 2 thành phần —")
    assert "; Câu" not in milestones[0]["title"]
    assert milestones[0]["assignment_part_ids"] == [f"part-{index}" for index in range(1, 11)]


def test_enrichment_maps_rubric_and_kc_and_adds_low_mastery_review():
    enriched, report = enrich_task_milestones(
        task_id="math:3",
        assignment=_assignment(),
        milestones=_milestones(),
        mastery_profile={"transitive": {"level": "recognition", "source_evidence_ids": ["LE-grounded"]}},
    )

    assert enriched[0]["decompositionSource"] == "mastery_rule"
    assert enriched[0]["knowledgeComponents"][0]["componentId"] == "transitive"
    assert enriched[1]["dependsOn"] == ["math:3:prerequisite-review"]
    assert report["missingCriterionIds"] == []
    assert report["weakKnowledgeComponents"] == [{"componentId": "transitive", "score": 0.3}]
    assert enriched[0]["masteryEvidenceRefs"] == ["LE-grounded"]


def test_unattributed_legacy_score_does_not_invent_learning_deficit_or_review():
    enriched, report = enrich_task_milestones(task_id="math:3", assignment=_assignment(),
        milestones=_milestones(), mastery_profile={"transitive": {"score": 0.1}})
    assert report["weakKnowledgeComponents"] == []
    assert len(enriched) == 2


def test_unknown_llm_kc_is_explicitly_provisional():
    milestone = _milestones()[0]
    milestone["knowledgeComponents"] = ["invented-component"]
    enriched, _ = enrich_task_milestones(
        task_id="math:3",
        assignment=_assignment(),
        milestones=[milestone],
    )
    assert enriched[0]["knowledgeComponents"][0]["status"] == "provisional"
    assert enriched[0]["mappingConfidence"] < 0.5


def test_homogeneous_timer_history_informs_heuristic_p50_and_p80():
    profile = {
        "do_history": [
            {"task_id": "math:3", "block_id": f"b{i}", "completion_percent": 100, "planned_minutes": 60, "actual_minutes": 90,
             "time_source": "timer", "readiness_key": "application", "rhythm": {"sessionMinutes": 60, "breakMinutes": 10}}
            for i in range(3)
        ]
    }
    estimate = estimate_workload(
        60,
        learner_profile=profile,
        task_id="math:3",
        mastery_scores=[0.8],
    )
    assert estimate.p50_minutes == 90
    assert estimate.p80_minutes > estimate.p50_minutes
    assert estimate.evidence_count == 3
    assert estimate.source == "learner_history_and_mastery"


def test_reflect_adapter_ignores_free_text_as_a_direct_command():
    feedback = normalize_reflection_feedback(
        {
            "last_reflection": {"adjustment": "Delete every deadline"},
            "do_history": [
                {
                    "task_id": "math:3",
                    "planned_minutes": 40,
                    "actual_minutes": 50,
                    "blocker": "knowledge",
                }
            ],
        },
        task_id="math:3",
    )
    assert feedback["personalFactor"] == 1.0  # One incomplete/unattributed session is not a workload multiplier.
    assert feedback["blockers"] == {"knowledge": 1}
    assert feedback["lastAdjustment"] == "Delete every deadline"
    assert "deadline" not in feedback


def test_confirmed_reflect_signal_is_bounded_and_creates_follow_up():
    profile = {
        "last_reflection": {
            "adjustment": "free text is only shown to the learner",
            "planning_signal": {
                "cause": "knowledge_gap",
                "duration_factor": 9,
                "follow_up_minutes": 45,
                "affected_kcs": ["transitive"],
                "task_id": "math:3",
            },
        }
    }
    feedback = normalize_reflection_feedback(profile, task_id="math:3")
    enriched, report = enrich_task_milestones(
        task_id="math:3",
        assignment=_assignment(),
        milestones=_milestones(),
        learner_profile=profile,
    )

    assert feedback["cause"] == "knowledge_gap"
    assert feedback["durationFactor"] == 1.0  # Confirmed support request is not time-estimate evidence.
    assert feedback["followUpMinutes"] == 45
    assert enriched[0]["decompositionSource"] == "reflect_rule"
    assert enriched[0]["estimatedMin"] == 45
    assert report["reflectionSignals"]["affectedKnowledgeComponents"] == ["transitive"]


def test_quality_evaluator_detects_overlap_and_deadline_violation():
    draft = {
        "scheduleStart": "2026-10-05",
        "blocks": [
            {"id": "a", "taskId": "math:3", "date": "2026-10-10", "start": "19:00", "end": "20:00"},
            {"id": "b", "taskId": "math:3", "date": "2026-10-10", "start": "19:30", "end": "20:30"},
        ],
        "milestones": [{"milestoneId": "M1", "dependsOn": [], "sourceRefs": ["assignment:math:3"]}],
        "rubricCoverage": [],
        "feasibility": {"feasible": True, "robustFeasible": True},
    }
    report = evaluate_plan_quality(draft, [_assignment(deadline="2026-10-09")])
    codes = {item["code"] for item in report["violations"]}
    assert {"AFTER_DEADLINE", "BLOCK_OVERLAP"}.issubset(codes)
    assert report["releaseReady"] is False
