"""One-time recovery of the documented QA fixture incident; private backups only.

Writers must be stopped. No source, account, Google token, checkpoint or file
table is modified. Current rows must exactly match the frozen recovery snapshot.
"""

import json
from pathlib import Path

from sqlalchemy import MetaData, and_, select

from scripts.audit_standalone_baseline import baseline_rows
from src.course_source.migration import inventory
from src.db import engine

ROOT = Path("data/standalone-migration-20261010-1910")
TABLES = frozenset({
    "pacewise_agent_review_cases", "pacewise_course_projections",
    "pacewise_instructor_actions", "pacewise_knowledge_state_snapshots",
    "pacewise_learner_memories", "pacewise_learning_events",
    "pacewise_learning_evidence", "pacewise_lms_course_contexts",
    "pacewise_lms_event_projections", "pacewise_rag_ingestion_jobs",
    "pacewise_sync_cursors", "pacewise_workspaces",
})


def main():
    assert engine.dialect.name == "postgresql"
    baseline = baseline_rows(ROOT / "pacewise-before.jsonl.gz")
    frozen = baseline_rows(ROOT / "pacewise-before-qa-repair.jsonl.gz")
    metadata = MetaData()
    metadata.reflect(engine)
    tables = list(metadata.sorted_tables)
    assert TABLES <= set(baseline) <= set(metadata.tables)
    # Canonical hashes include every row and column, not just counts.
    with engine.begin() as connection:
        from src.course_source.migration import canonical

        before = inventory(connection, tables)
        for table in tables:
            expected_rows = frozen.get(table.name, [])
            actual_rows = list(connection.execute(select(table).order_by(*table.primary_key)).mappings())
            assert sorted(canonical(row) for row in actual_rows) == sorted(canonical(row) for row in expected_rows), "Writer changed frozen recovery state"
        for table in reversed(tables):
            if table.name not in TABLES:
                continue
            keys = list(table.primary_key.columns.keys())
            known = {tuple(row[key] for key in keys) for row in baseline[table.name]}
            for row in frozen[table.name]:
                if tuple(row[key] for key in keys) not in known:
                    connection.execute(table.delete().where(and_(*(table.c[key] == row[key] for key in keys))))
        for table in tables:
            if table.name not in TABLES:
                continue
            keys = list(table.primary_key.columns.keys())
            for row in baseline[table.name]:
                where = and_(*(table.c[key] == row[key] for key in keys))
                exists = connection.execute(select(table).where(where)).first()
                if exists:
                    connection.execute(table.update().where(where).values(**row))
                else:
                    connection.execute(table.insert().values(**row))
        after = inventory(connection, tables)
        expected = json.loads((ROOT / "pacewise-inventory-before.json").read_text(encoding="utf-8-sig"))["inventory"]
        assert all(after[name] == expected[name] for name in TABLES), "Recovery did not match baseline"
        assert all(before[name] == after[name] for name in before if name not in TABLES), "Recovery changed an unrelated table"
    report = {"passed": True, "recovered_tables": len(TABLES), "recovered_baseline_checksums": True,
              "unrelated_tables_unchanged": True, "private_recovery_snapshot_preserved": True}
    Path("evals/reports/standalone-qa-recovery-2026-10-10.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
