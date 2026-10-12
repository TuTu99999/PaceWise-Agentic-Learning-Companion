# Instructor role foundation

Status: implemented and verified on 2026-10-07.

## Goal

Keep the instructor role focused on course grounding, schedule, learning
evidence governance, feedback, and privacy-aware intervention. PaceWise does
not duplicate LMS grading or submission workflows.

## Product areas

- Overview: privacy-thresholded class progress, deadline risk, difficult topics,
  LMS structure, and low-confidence AI review count.
- Teaching schedule: create, edit, cancel, delete, and repeat PaceWise-owned
  offline/online/practice/review/quiz/office-hour events. LMS events are
  explicitly read-only.
- Course knowledge graph: instructor-approved modules, knowledge components,
  prerequisites, objectives, and misconception taxonomy.
- Materials: upload, preview, download, index, and revoke course RAG sources.
- Assessment governance: versioned question/rubric approval and evidence review.
- Feedback: class/group guidance, resources, reassessment, and intervention
  recommendations. Group delivery is filtered by LMS membership. Recommended
  study time never bypasses learner confirmation.
- Privacy settings: minimum aggregate group size, consent, individual review,
  and approved-resource publication policy.

## Contracts and decisions

- Instructor writes are immutable `InstructorAction` events and fold into a
  course-scoped `teacherWorkspace` projection.
- LMS records never enter the instructor write path.
- Student sync receives confirmed, non-cancelled PaceWise teaching events as
  read-only calendar constraints. Weekly recurrence expands to a bounded number
  of occurrences.
- Course graph writes reject unknown modules, unknown prerequisites, self
  prerequisites, and dependency cycles.
- Feedback duration is a bounded planning recommendation, not a direct calendar
  mutation.
- Small-group analytics use the instructor privacy threshold, never below five.

## Verification

- Backend: `284 passed` in `tests/`; new domain tests cover validation, folding,
  recurrence/calendar projection, deletion/cancellation, feedback bounds, and
  course graph cycles.
- Frontend: `31` test files / `110` tests passed in two Windows-safe shards.
- TypeScript typecheck passed.
- Production build passed; instructor pages are lazy-loaded chunks.
- Ruff and `git diff --check` passed.

## Honest boundary

This foundation supplies the instructor ground truth and governance required by
the future Adaptive Assessment Agent. It does not claim that real-learner
assessment validity has been established; that still requires labelled expert
cases and a learner pilot.
