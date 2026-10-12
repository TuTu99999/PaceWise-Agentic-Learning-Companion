# LangSmith cloud connection — 09/10/2026

## Result

Backend and worker have been rebuilt/recreated with metadata-only tracing enabled. Both services created synthetic connectivity traces and read them back from the real LangSmith cloud project `pacewise-private-metadata`.

| Service | Cloud readback | Completed spans | Empty inputs / outcome-only outputs | Hierarchy / project |
|---|---|---|---|---|
| backend | passed | 5/5 | passed | passed |
| worker | passed | 5/5 | passed | passed |

Span names: `coordinator`, `plan`, `do`, `assessment`, `reflect`. Assessment is nested under Do; Plan–Do–Reflect remain the product phases. No LLM calls or learner records were used in these connectivity probes.

Backend root run: `4a164010-4e92-48cc-b9e6-f0a49224267f`.

Worker root run: `4bca7e5c-4cf6-406f-ba8d-275bd88cb08d`.

## Configuration and fixes

- Settings supports the existing `LANGCHAIN_API_KEY` as a legacy alias. An explicitly configured modern `LANGSMITH_API_KEY` takes precedence, including an empty value. No credential was copied into source, arguments, reports or Git.
- `LANGSMITH_ENABLED=true`; native `LANGCHAIN_TRACING_V2` and `LANGSMITH_TRACING` remain false to avoid exporting raw prompts and graph state.
- The service key initially received 403 on workspace-scoped APIs. The read-only workspace-list endpoint returned one authorized workspace. That workspace was selected in local `.env`; its identifier and key are not reproduced here.
- Settings supports `LANGSMITH_WORKSPACE_ID` and legacy `LANGCHAIN_WORKSPACE_ID`. The SDK sends the target workspace header. Organization-scoped service keys require a target workspace according to [LangSmith administration documentation](https://docs.langchain.com/langsmith/administration-overview).
- Initial create/PATCH probes exposed incomplete child spans. Tracing now queues **completed spans once**, with start/end timestamps, empty inputs, application-owned names, parent/trace identifiers, outcome and exception class only.
- A bounded queue of 128 spans coalesces at most 32 completed spans per synchronous batch ingestion, off the request path. Native SDK background batching is disabled to avoid a second queue and misleading delivery counters. Runtime metadata enrichment is disabled.
- Queue overflow and delivery errors are counted; they do not propagate into a learner request. This is best-effort tracing, not a durable audit log: a process crash can lose queued/unfinished spans.

## Verification

Targeted configuration, opt-in/privacy, completed-span batching and telemetry tests: **23 passed**, [JUnit](../evals/reports/langsmith-connect-2026-10-09.xml). Lint passes for the changed tracing/configuration/test/probe files.

Full backend regression: **569 passed**, [JUnit](../evals/reports/langsmith-backend-2026-10-09.xml). Cloud readback outputs are recorded in the [runtime snapshot](../evals/reports/langsmith-runtime-2026-10-09.json). `.env` remains Git-ignored and no key appears in this evidence.

Backend is healthy; Prometheus target `pacewise-backend` is `up` with empty `lastError` after recreation.

Reproduce without printing credentials:

```powershell
Get-Content scripts/evaluate_langsmith_connection.py -Raw -Encoding UTF8 |
  docker compose exec -T backend python - --service backend

Get-Content scripts/evaluate_langsmith_connection.py -Raw -Encoding UTF8 |
  docker compose exec -T worker python - --service worker
```

The probe emits only configuration presence, synthetic run IDs and validation results. It creates five synthetic spans per invocation. For read-only re-verification, append `--root-run-id <synthetic root ID>` to avoid creating another trace. Reads use bounded backoff for indexing lag, not repeated retries of auth/quota failures.

## Limits

This proves cloud connectivity, project selection, completion, hierarchy and privacy for synthetic spans emitted by the same tracing component used by the application. It does not prove educational effectiveness, end-to-end behavior of every real agent workflow, 1,000-user capacity, zero trace loss under overload, or production security certification. Earlier failed/unfinished connectivity probes may remain in the project; no cloud learner records or existing projects were deleted.
