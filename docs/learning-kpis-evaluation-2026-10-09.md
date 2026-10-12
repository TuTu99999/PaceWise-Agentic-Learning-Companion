# Learning-cycle KPI evaluation — 09/10/2026

## Delivered behavior

PaceWise keeps the product scope **Plan → Do → Reflect**. The instructor overview now separates:

1. **LMS on-time submission:** authoritative first submission against the effective student deadline. Submission is not evidence of understanding.
2. **Original-plan attainment:** verified milestones by the target time frozen at the first applicable server-confirmed plan for the week. Removing or postponing milestones cannot rewrite this baseline.
3. **Current-plan attainment:** the latest confirmed plan's targets, displayed separately from the original baseline.
4. **Learning evidence:** latest accepted, valid Assessment evidence matching the milestone's approved knowledge components and required demonstrated level. Missing, below-requirement and unmapped goals remain distinct. Retention reports actual delayed probes checked/passed, not elapsed time alone.

Before/after submission comparison uses the **first `PLAN_CONFIRMED` event**, not login, and compares the same qualifying students in complete 14-day windows before and after that event. Both windows must contain eligible observations. This is an observational association, not a causal impact estimate; course difficulty and selection effects remain uncontrolled.

## Measurement contract and safeguards

- `plan-measurement-v1` is created from the canonical server draft when the student confirms. Client workspace history, timers and self-reported completion do not establish success.
- Each frozen milestone records task/milestone/block IDs, original target time, required level, requirement source and approved KC mapping. The event log preserves revisions; confirmation retry does not create a second baseline.
- Multiple blocks for a milestone produce one objective. Later block IDs can be matched only through the same stable task/milestone identity; original time and criteria are not replaced.
- Default required level is the **explicit conservative `application` policy**, unless the canonical plan has an explicit supported requirement. This default is not a teacher-validated rubric for every course. Provisional/unmapped KCs cannot pass the evidence criterion.
- A validated checkpoint supports the learning criterion tested, not proof that the entire graded assignment artifact is complete. LMS delivery can count toward plan attainment without improving the learning-evidence KPI.
- Current evidence quality can decline after a new observation. A later failure does not retroactively change an earlier, on-time verified achievement.
- Future goals and goals confirmed after their target are excluded from retrospective progress. Excused and unpublished assignments are excluded.
- Each KPI section requires at least five qualifying students. Below threshold, rates and numerators/denominators are `null`, not a misleading 0%. Records are scoped by institution, course and current enrollment; no individual IDs or responses are included in this projection.
- Legacy confirmed plans without the frozen measurement contract are not fabricated into measured milestone history. `progressBeforePaceWise` remains `null` because there is no authoritative pre-adoption milestone ledger.
- Queries for current-cycle evidence use the existing 14-day planning horizon plus current-week history (21-day lookback). First adoption uses a separate scoped SQL minimum across confirmation events. No new LLM/provider calls are needed for these KPIs.

## Executed validation

| Check | Actual result |
|---|---|
| Full backend regression | **593 passed**, isolated SQLite; [JUnit](../evals/reports/learning-kpis-backend-2026-10-09.xml) |
| Full frontend regression | **220 passed / 55 files**; [JUnit](../evals/reports/learning-kpis-frontend-2026-10-09.xml) |
| TypeScript + Vite production build | Passed, 118 modules; main JS 351.18 kB / 111.51 kB gzip |
| Docker deployment | Backend, worker and frontend rebuilt/recreated; existing databases retained |
| Encrypted HTTP instructor overview | **200**, 28 enrolled demo students, new KPI contract and privacy assertions passed; 923 ms for the final request |
| Encrypted HTTP student accessing instructor overview | **403**, 14 ms; both smoke clients logged out in `finally` |
| Live learning KPI availability | All three sections `insufficient_data`; no fake percentage or synthetic cohort was inserted |

HTTP verification: `scripts/evaluate_instructor_overview.py`. Durations above are single local observations, not latency percentiles or load-test results.

## Synthetic regression cases and observed assertions

The following are executable technical fixtures, **not real learner outcomes**:

| Scenario | Asserted output |
|---|---|
| Five students, six due milestones each, four evidenced | Original plan `20/30 = 66.67%`; learning evidence `20/30`; ten missing |
| Timer/self-report says complete, no accepted evidence or LMS delivery | `0/30`; thirty unverified |
| Re-plan removes all six milestones per student | Original denominator stays thirty, removed count thirty; current plan has insufficient data |
| Work completed after original target but before revised target | Original `0/30`; current `30/30`; latest learning evidence `30/30` |
| Authoritative LMS delivery without Assessment | Plan attainment `100%`; learning evidence `0%` |
| Correct MCQ recognition, pending human review, invalid result or failed reasoning | Application-level goal does not pass |
| New failing Assessment after the original target | Latest learning evidence drops; historical on-time attainment remains intact |
| Provisional KC mapping | Thirty goals reported unmapped; no fabricated understanding |
| Four qualifying students | Counts and rates suppressed (`null`) |
| Delayed probe due, not answered | Due five, checked zero, passed zero |
| Several required KCs | Every required KC needs acceptable evidence; one matching component is insufficient |
| Transfer fails but application is demonstrated | Application goal can pass; a transfer requirement cannot |
| Next-week plan confirmed | Does not erase current-week original goals |
| Cross-institution/course/student records | Excluded by scoped SQL projection |
| Planner `7:1` versus LMS assignment `1` | Matched only in course 7; course 8 cannot use that goal or baseline |
| Server confirmation and retry | Frozen measurement saved in `PLAN_CONFIRMED`; retry preserves it and does not add another event |
| Too early for complete post-adoption window | Before/after `insufficient_data`, not a prematurely inflated improvement |

Primary tests: `tests/test_services/test_learning_cycle_metrics.py`, `tests/test_services/test_adoption_metrics.py`, `tests/test_api/test_routes.py`, and `frontend/pacewise/src/components/domain/LearningCycleKpis.test.tsx`.

During the final verification, an added retry assertion initially assumed the shared test database had only one confirmation event. The test was corrected to compare the event-ID set immediately after the first confirmation against the set after retry (without deleting existing ledger history). The final full regression above includes this stronger assertion and the course-qualified-ID fixes.

## Remaining evidence needed

- Real cohorts with sufficient confirmed plans, course-approved KC mapping and accepted Assessment evidence. Newly confirmed plans begin generating this ledger; old workspace data is not backfilled as truth.
- Teacher review of whether each task's required level and artifact criteria are appropriate. The default application policy is a conservative engineering rule, not pedagogical calibration.
- Independent expert labels, delayed retention results and learner pilot data before claiming valid understanding measurement or educational improvement.
- Matched/control or stronger evaluation design before attributing submission gains to PaceWise.
- Dedicated concurrent workload tests before claiming acceptable latency/cost at 1,000 students. These regression and HTTP checks do not establish that capacity.
- Aggregate suppression is a privacy safeguard, not a declaration of FERPA compliance or guaranteed anonymity under arbitrary repeated queries.
