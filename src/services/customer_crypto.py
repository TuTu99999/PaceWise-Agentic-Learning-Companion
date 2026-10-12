"""Versioned field encryption. Keys live outside SQL and must survive restores."""

import base64
import json
import os
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM, AESSIV
from sqlalchemy import Text, inspect, text
from sqlalchemy.types import TypeDecorator

from src.config import get_settings

PREFIX = "pwenc:v1:"
AAD = b"pacewise:customer-data:v1"


def push_opted_in(state_json: str) -> bool:
    preferences = (json.loads(state_json).get("reminders") or {}).get("preferences") or {}
    return (
        preferences.get("pushEnabled") is True
        and preferences.get("browserEnabled") is True
        and preferences.get("enabled", True) is True
    )


@lru_cache(maxsize=8)
def data_key(path: str, production: bool = False) -> bytes:
    target = Path(path)
    if not target.exists():
        if production:
            raise RuntimeError("Customer encryption key must be mounted before production startup")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as stream:
                stream.write(os.urandom(64))
                stream.flush()
                os.fsync(stream.fileno())
            target.chmod(0o600)
        except FileExistsError:
            pass  # Another process initialized the same persistent mount.
    key = target.read_bytes()
    if len(key) != 64:
        raise RuntimeError("Invalid customer encryption key")
    return key


def _key() -> bytes:
    settings = get_settings()
    return data_key(settings.customer_data_key_file, settings.app_env in {"staging", "production"})


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, purpose: str, *, deterministic: bool = False):
        super().__init__()
        self.purpose, self.deterministic = purpose, deterministic

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        raw = str(value).encode()
        aad = AAD + b":" + self.purpose.encode()
        if self.deterministic:
            encrypted = AESSIV(_key()).encrypt(raw, [aad])
        else:
            nonce = os.urandom(12)
            encrypted = nonce + AESGCM(_key()[:32]).encrypt(nonce, raw, aad)
        return PREFIX + base64.urlsafe_b64encode(encrypted).decode()

    def process_result_value(self, value, dialect):
        if value is None or not value.startswith(PREFIX):
            return value  # Legacy read during the transactional migration only.
        raw = base64.urlsafe_b64decode(value[len(PREFIX) :])
        aad = AAD + b":" + self.purpose.encode()
        if self.deterministic:
            result = AESSIV(_key()).decrypt(raw, [aad])
        else:
            result = AESGCM(_key()[:32]).decrypt(raw[:12], raw[12:], aad)
        return result.decode()


def migrate_encrypted_columns(engine, metadata, *, schema=None) -> int:
    """Preserve IDs/relations; encrypt legacy fields atomically and idempotently."""
    changed = 0
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(73422011)"))
        inspector = inspect(conn)
        for table in metadata.sorted_tables:
            fields = [c for c in table.columns if isinstance(c.type, EncryptedText)]
            if not fields:
                continue
            prefix = f'"{schema}".' if schema else ""
            target = prefix + f'"{table.name}"'
            if table.name == "pacewise_workspaces":
                present = {c["name"] for c in inspector.get_columns(table.name, schema=schema)}
                if "push_opted_in" not in present:
                    conn.execute(text(f"ALTER TABLE {target} ADD COLUMN push_opted_in BOOLEAN NOT NULL DEFAULT FALSE"))
                conn.execute(
                    text(f"CREATE INDEX IF NOT EXISTS ix_pacewise_workspaces_push_opted_in ON {target} (push_opted_in)")
                )
            if engine.dialect.name == "postgresql":
                types = {c["name"]: c["type"] for c in inspector.get_columns(table.name, schema=schema)}
                for field in fields:
                    if str(types[field.name]).upper() != "TEXT":
                        conn.execute(text(f'ALTER TABLE {target} ALTER COLUMN "{field.name}" TYPE TEXT'))
            keys = [c.name for c in table.primary_key]
            columns = keys + [c.name for c in fields]
            if table.name == "pacewise_workspaces":
                columns.append("push_opted_in")
            query = ", ".join(f'"{name}"' for name in columns)
            rows = conn.execute(text(f"SELECT {query} FROM {target}")).mappings().all()
            for row in rows:
                for field in fields:
                    if row[field.name] is not None and row[field.name].startswith(PREFIX):
                        field.type.process_result_value(row[field.name], engine.dialect)  # Fail closed on wrong key.
                updates = {
                    c.name: c.type.process_bind_param(row[c.name], engine.dialect)
                    for c in fields
                    if row[c.name] is not None and not row[c.name].startswith(PREFIX)
                }
                if table.name == "pacewise_workspaces":
                    state_field = table.c.state_json.type
                    opted = push_opted_in(state_field.process_result_value(row["state_json"], engine.dialect))
                    if bool(row["push_opted_in"]) != opted:
                        updates["push_opted_in"] = opted
                if not updates:
                    continue
                setters = ", ".join(f'"{name}" = :{name}' for name in updates)
                where = " AND ".join(f'"{name}" = :key_{name}' for name in keys)
                parameters = updates | {f"key_{name}": row[name] for name in keys}
                conn.execute(text(f"UPDATE {target} SET {setters} WHERE {where}"), parameters)
                changed += 1
    return changed
