"""Small encrypted read cache; identity + refresh grant + window form its key."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from src.persistence_models import GoogleReadCache


def cache_key(user_id, refresh_ciphertext, operation, window=None):
    return hashlib.sha256(
        json.dumps([user_id, refresh_ciphertext, operation, window], sort_keys=True).encode()
    ).hexdigest()


def read_cache(db, key, cipher):
    row = db.get(GoogleReadCache, key)
    if row:
        expires = row.expires_at.replace(tzinfo=UTC) if row.expires_at.tzinfo is None else row.expires_at
        if expires > datetime.now(UTC):
            try:
                return json.loads(cipher.decrypt(row.encrypted_json))
            except Exception:
                pass
    return None


def store_cache(db, key, user_id, value, cipher, ttl):
    if ttl <= 0:
        return
    db.execute(delete(GoogleReadCache).where(GoogleReadCache.expires_at < datetime.now(UTC)))
    row = db.get(GoogleReadCache, key) or GoogleReadCache(id=key, user_id=user_id)
    row.encrypted_json = cipher.encrypt(json.dumps(value))
    row.expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
    db.merge(row)
