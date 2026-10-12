# Plan Intelligence v2

## Goal

Upgrade Plan into a hybrid planning pipeline: the LLM may interpret complex
assignments, while deterministic services own rubric coverage, knowledge
component mapping, uncertainty estimates, mastery-aware priority, scheduling,
and quality evaluation.

## Contracts

- Official LMS deadlines and rubric criteria are immutable inputs.
- Milestones carry assignment, rubric, knowledge-component, provenance, and
  uncertainty metadata.
- Unknown knowledge components remain provisional; they are never presented as
  instructor-approved concepts.
- The scheduler never positions work in the past, on busy time, or after a
  deadline.
- Mastery may add prerequisite review and break priority ties, but cannot
  override a closer hard deadline.
- P50 drives expected workload; P80 is reported as robust capacity risk.
- Reflect/Do evidence is normalized into parameters, not injected as free text.
- Every draft includes an independent, deterministic quality report.
- Student confirmation remains mandatory before applying a draft.

## Acceptance criteria

1. Rubric criteria are normalized and milestone coverage gaps are reported.
2. Milestones map only to known or explicitly provisional knowledge components.
3. Low mastery creates a bounded prerequisite-review milestone.
4. Historical actual/planned ratios influence P50/P80 estimates.
5. Structured Reflect feedback changes only documented planning parameters.
6. Quality evaluation detects temporal, overlap, deadline, dependency,
   provenance, rubric-coverage, and capacity violations.
7. Offline plan-intelligence eval meets its release thresholds.
