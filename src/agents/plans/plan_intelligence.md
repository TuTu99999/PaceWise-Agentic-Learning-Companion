# Plan Intelligence v2 implementation plan

1. Add pure planning-intelligence services for rubric parsing, KC mapping,
   mastery risk, Reflect adaptation, and uncertainty estimates.
2. Integrate enriched milestones and mastery-aware priority into the existing
   deterministic scheduler without changing learner-pinned-block semantics.
3. Add an independent quality evaluator and expose its report in `plan_draft`.
4. Pass trusted learner memory from the API to the planning service.
5. Add unit, integration, regression, and deterministic offline eval coverage.
6. Run backend and frontend regressions; move the task record to `complete/`
   only after all acceptance criteria pass.

## Milestones

- M1: Domain services and contracts pass focused tests.
- M2: Scheduler/API integration passes existing planning tests.
- M3: Offline eval and full repository test suites pass.
