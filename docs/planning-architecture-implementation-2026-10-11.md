# Evidence-aware planning architecture — implementation 2026-10-11

## Decision

PaceWise keeps one deterministic scheduler. Deadline awareness, adaptive evidence and dynamic replanning are services around that scheduler, not three schedulers and not three new agents.

```text
Course/calendar facts + learner constraints
                  +
Do evidence + accepted assessment + confirmed reflection
                  ↓
       Multi-course planning memory
                  ↓
Task decomposition → P50/P80 estimate → cumulative deadline slack
                  ↓
        Deterministic scheduler
                  ↓
 Constraint validation → plan diff → learner confirmation
```

## Implemented boundaries

- The LLM may decompose tasks and explain a proposal. It does not position calendar blocks.
- `deadline_risk.py` computes P50/P80 cumulative slack at each exact deadline window.
- `replan_policy.py` emits a bounded repair context only after observed drift, an authoritative calendar/deadline event, or accepted assessment evidence.
- Do progress is reconciled conservatively: incomplete work may increase remaining workload, while a self-report never reduces it.
- Reflection from any enrolled course is visible to a multi-course Plan. Mastery remains namespaced by course.
- Plan diff records moved blocks/minutes/days and student-pinned violations. A draft is never auto-applied.

## Replan contract

```json
{
  "action": "propose_draft",
  "auto_apply": false,
  "repair_context": {
    "affected_task_ids": ["course:assignment"],
    "cause": "estimate_error",
    "observed_remaining_minutes": 30,
    "signal_follow_up_minutes": 0
  }
}
```

The Plan UI forwards only navigation context. Backend learner memory is authoritative for the repair signal and observed Do session.

## Benchmark

Run:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_replan_architecture.py
```

Synthetic replay compares a context-free scheduler rerun with evidence-aware repair:

| Scenario | Context-free rerun | Evidence-aware repair | Expected result |
|---|---:|---:|---|
| Slow progress: 90/60 minutes, 50% complete | 120 min | 180 min | Add 60 min and produce a visible diff |
| Accepted knowledge gap | 120 min | 165 min | Add a 45-minute retrieval/review step |
| Unexpected interruption | 120 min | 120 min | Do not inflate workload |
| Deadline overload | 240 min short | 300 min short | Report shortage; never place work after deadline |

These fixtures validate scheduling behavior and safety invariants. They do not establish educational effectiveness; that requires a learner pilot and calibrated outcome measures.

## Promotion gates before CP-SAT

Keep the rule-based scheduler in production until a shadow CP-SAT adapter beats it on the same replay set for:

1. zero hard-constraint violations;
2. lower deadline shortfall;
3. lower unnecessary schedule churn;
4. equal or better preference fit;
5. acceptable runtime and explainability.

