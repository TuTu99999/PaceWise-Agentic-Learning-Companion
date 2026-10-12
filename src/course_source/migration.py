"""Offline, lossless source snapshot/import. Never overwrite existing records.

Run export inside the old service (uses its DATABASE_URL), import inside the
PaceWise backend. Snapshot includes credential hashes: keep it private, never
commit it or expose it through the application API.
"""

import argparse
import base64
import gzip
import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, select, text

FORMAT = "pacewise-course-source-v1"


def encode(value):
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, bytes):
        return {"$bytes": base64.b64encode(value).decode()}
    return value


def decode(value):
    if isinstance(value, dict):
        if set(value) == {"$datetime"}:
            return datetime.fromisoformat(value["$datetime"])
        if set(value) == {"$date"}:
            return date.fromisoformat(value["$date"])
        if set(value) == {"$bytes"}:
            return base64.b64decode(value["$bytes"], validate=True)
        raise ValueError("Invalid snapshot value")
    return value


def canonical(row):
    return json.dumps({key: encode(value) for key, value in row.items()},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def ordered_rows(connection, table):
    keys = list(table.primary_key.columns)
    if not keys:
        raise ValueError(f"No primary key: {table.name}")
    return connection.execute(select(table).order_by(*keys)).mappings()


def inventory(connection, tables):
    result = {}
    for table in tables:
        digest, count = hashlib.sha256(), 0
        for row in ordered_rows(connection, table):
            digest.update((canonical(dict(row)) + "\n").encode())
            count += 1
        result[table.name] = {"rows": count, "sha256": digest.hexdigest()}
    return result


def export_snapshot(path: Path, url: str):
    source = create_engine(url)
    metadata = MetaData()
    metadata.reflect(source)
    tables = list(metadata.sorted_tables)
    # The source must be frozen by the operator before export. Repeatable-read
    # also protects all relational rows against a torn multi-table snapshot.
    isolation = "REPEATABLE READ" if source.dialect.name == "postgresql" else "SERIALIZABLE"
    with source.connect().execution_options(isolation_level=isolation) as connection:
        sequences = {}
        if source.dialect.name == "postgresql":
            for table in tables:
                for column in table.primary_key:
                    sequence = connection.scalar(text("SELECT pg_get_serial_sequence(:tbl, :col)"),
                                                 {"tbl": table.name, "col": column.name})
                    if sequence:
                        # Name originates in the catalog, never user input.
                        quoted = ".".join(connection.dialect.identifier_preparer.quote(x) for x in sequence.split("."))
                        highwater = connection.execute(text(f"SELECT last_value, is_called FROM {quoted}")).one()
                        sequences[table.name] = {"column": column.name, "last_value": highwater[0], "is_called": highwater[1]}
        header = {"format": FORMAT, "columns": {t.name: list(t.columns.keys()) for t in tables},
                  "sequences": sequences}
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create: a new export cannot silently replace a backup.
        with path.open("xb") as raw:
            try:
                os.chmod(path, 0o600)
                with gzip.open(raw, "wt", encoding="utf-8") as output:
                    output.write(json.dumps(header) + "\n")
                    checks = {}
                    for table in tables:
                        digest, count = hashlib.sha256(), 0
                        for row in ordered_rows(connection, table):
                            encoded = canonical(dict(row))
                            output.write('{"table":' + json.dumps(table.name) + ',"row":' + encoded + '}\n')
                            digest.update((encoded + "\n").encode())
                            count += 1
                        checks[table.name] = {"rows": count, "sha256": digest.hexdigest()}
                    output.write(json.dumps({"inventory": checks}) + "\n")
            except Exception:
                path.unlink(missing_ok=True)
                raise
    source.dispose()
    return {"format": FORMAT, "tables": len(checks), "total_rows": sum(v["rows"] for v in checks.values()),
            "inventory": checks}


def import_snapshot(path: Path):
    from src.course_source.db import SCHEMA, Base, engine, initialize_database

    initialize_database()
    from sqlalchemy import Text

    from src.services.customer_crypto import EncryptedText

    # Preserve raw ciphertext without application decode / double encryption.
    raw_metadata = MetaData()
    for original in Base.metadata.sorted_tables:
        copied = original.to_metadata(raw_metadata)
        for column in copied.columns:
            if isinstance(column.type, EncryptedText):
                column.type = Text()
    tables = list(raw_metadata.sorted_tables)
    lookup = {t.name: t for t in tables}
    with gzip.open(path, "rt", encoding="utf-8") as source, engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(782019261010)"))
        header = json.loads(source.readline())
        if header.get("format") != FORMAT or set(header.get("columns", {})) != set(lookup):
            raise ValueError("Snapshot schema mismatch; refusing partial migration")
        for name, columns in header["columns"].items():
            if set(columns) != set(lookup[name].columns.keys()):
                raise ValueError(f"Snapshot column mismatch: {name}")
        populated = any(connection.scalar(select(func.count()).select_from(t)) for t in tables)
        digest = {name: hashlib.sha256() for name in lookup}
        counts = dict.fromkeys(lookup, 0)
        footer = None
        current_name, batch = None, []

        def flush():
            if batch and not populated:
                connection.execute(lookup[current_name].insert(), batch)
            batch.clear()

        for line in source:
            item = json.loads(line)
            if "inventory" in item:
                flush()
                footer = item["inventory"]
                if source.readline():
                    raise ValueError("Unexpected records after snapshot footer")
                break
            name = item.get("table")
            if name not in lookup or set(item.get("row", {})) != set(header["columns"][name]):
                raise ValueError("Invalid snapshot row")
            if current_name != name:
                flush()
                current_name = name
            row = {key: decode(value) for key, value in item["row"].items()}
            digest[name].update((canonical(row) + "\n").encode())
            counts[name] += 1
            batch.append(row)
            if len(batch) >= 250:
                flush()
        expected = {name: {"rows": counts[name], "sha256": digest[name].hexdigest()} for name in lookup}
        if footer != expected:
            raise ValueError("Incomplete or corrupt snapshot; transaction rolled back")
        actual = inventory(connection, tables)
        if actual != expected:
            raise ValueError("Destination differs; refusing to overwrite existing accounts/history")
        if not populated and engine.dialect.name == "postgresql":
            for name, spec in header.get("sequences", {}).items():
                table = lookup[name]
                column = table.c[spec["column"]]
                maximum = connection.scalar(select(func.max(column))) or 0
                sequence = connection.scalar(text("SELECT pg_get_serial_sequence(:tbl, :col)"),
                                             {"tbl": f"{SCHEMA}.{name}", "col": column.name})
                if not sequence:
                    raise ValueError(f"Missing destination sequence: {name}")
                value = max(spec["last_value"], maximum, 1)
                connection.execute(text("SELECT setval(CAST(:seq AS regclass), :value, :called)"),
                                   {"seq": sequence, "value": value,
                                    "called": bool(spec["is_called"] or maximum)})
    return {"format": FORMAT, "verified": True, "already_imported": bool(populated),
            "tables": len(expected), "total_rows": sum(counts.values()), "inventory": actual}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--export", type=Path)
    mode.add_argument("--import-snapshot", type=Path)
    parser.add_argument("--report", type=Path, help="Write a counts/checksums-only evaluation report")
    args = parser.parse_args()
    result = export_snapshot(args.export, os.environ["DATABASE_URL"]) if args.export else import_snapshot(args.import_snapshot)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "inventory"}))


if __name__ == "__main__":
    main()
