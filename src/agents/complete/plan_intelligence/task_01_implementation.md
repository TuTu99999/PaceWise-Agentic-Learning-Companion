# Completed — Plan Intelligence v2

## Delivered

- Hybrid assignment routing: structured assignments use deterministic templates;
  incomplete/complex assignments retain LLM decomposition with a safe fallback.
- Deep rubric normalization with criterion IDs, weights, source references, and
  deterministic milestone-coverage reporting.
- Knowledge-component mapping that distinguishes approved LMS metadata from
  provisional AI suggestions and lowers confidence for unapproved concepts.
- Mastery-aware priority and bounded prerequisite-review milestones without
  allowing mastery to override a closer deadline.
- Confirmed Reflect/Do evidence adapter with bounded duration factors and
  targeted follow-up milestones; free text is never executed as a schedule command.
- P50/P80 estimates with evidence count, confidence, source, and robust-capacity
  shortfalls alongside ordinary feasibility.
- Independent quality evaluation for past blocks, overlaps, deadlines,
  dependencies, provenance, rubric coverage, and robust capacity.
- Trusted learner memory is supplied by the API; client input cannot replace it.
- Plan prompts and parsers preserve rubric/KC/provenance metadata while the
  deterministic scheduler remains the only component that positions blocks.

## Verification evidence

- Focused Plan/agent tests: 72 passed.
- Full backend suite: 278 passed.
- Frontend suite: 107 passed.
- Frontend production build: passed.
- Ruff on the full `src` and `tests` trees: passed.
- Plan Intelligence v2 offline eval: 120 labelled deterministic cases, all six
  release metrics passed at 1.0.

## Honest limitations

- Offline cases demonstrate deterministic correctness, not educational impact.
- Rubric/KC quality still depends on official LMS/instructor metadata.
- LLM semantic decomposition needs a separate live, human-labelled evaluation.
- Better on-time submission and learning outcomes require a longitudinal pilot
  against deadline-only and student-authored-plan baselines.
