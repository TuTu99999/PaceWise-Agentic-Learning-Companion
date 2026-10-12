"""Private snapshot audit; prints counts only, never row content or keys."""

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import MetaData, select, text

from src.course_source.migration import canonical, decode
from src.db import engine


def baseline_rows(path):
    rows = defaultdict(list)
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            item = json.loads(line)
            if "table" in item:
                rows[item["table"]].append({
                    key: decode(value) if not isinstance(value, dict) or set(value) in ({"$bytes"}, {"$datetime"}, {"$date"}) else value
                    for key, value in item["row"].items()
                })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    rows = baseline_rows(args.snapshot)
    metadata = MetaData()
    metadata.reflect(engine)
    with engine.connect() as connection:
        native_users = set(connection.execute(text("SELECT id FROM course_source.users")).scalars())
        for table in metadata.sorted_tables:
            if table.name not in rows:
                continue
            keys = list(table.primary_key.columns.keys())
            def index(row):
                return tuple(row[key] for key in keys)
            before = {index(row): row for row in rows[table.name]}
            now = {index(row): dict(row) for row in connection.execute(select(table)).mappings()}
            missing = before.keys() - now.keys()
            added = now.keys() - before.keys()
            changed = {key for key in before.keys() & now.keys() if canonical(before[key]) != canonical(now[key])}
            if missing or added or changed:
                print(json.dumps({"table": table.name, "baseline": len(before), "current": len(now),
                                  "missing": len(missing), "added": len(added), "changed": len(changed),
                                  "changed_native_user_rows": sum(any(now[key].get(col) in native_users for col in
                                                                     ("user_id", "student_user_id", "instructor_user_id")) for key in changed),
                                  "added_native_user_rows": sum(any(now[key].get(col) in native_users for col in
                                                                   ("user_id", "student_user_id", "instructor_user_id")) for key in added),
                                  "changed_columns": sorted({col for key in changed for col in before[key]
                                                             if canonical({col: before[key][col]}) != canonical({col: now[key][col]})}),
                                  "added_test_marked": sum(any(isinstance(value, str) and any(marker in value.lower()
                                                           for marker in ("test", "fixture", "qa", "synthetic"))
                                                           for value in now[key].values()) for key in added)}))


if __name__ == "__main__":
    main()
