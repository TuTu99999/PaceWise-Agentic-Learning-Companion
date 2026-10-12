"""Read-only pg_dump, encrypted before disk. Prints counts/checksum, never SQL."""

import hashlib
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.config import get_settings
from src.services.customer_crypto import data_key


def main():
    settings = get_settings()
    key = data_key(settings.customer_data_key_file, settings.app_env == "production")[:32]
    output = Path("data/backups")
    output.mkdir(parents=True, exist_ok=True)
    target = output / ("before-customer-encryption-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".pwdb")
    command = [
        "docker",
        "exec",
        "pacewise-pacewise-postgres-1",
        "sh",
        "-c",
        'exec pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"',
    ]
    dump = subprocess.run(command, check=True, capture_output=True).stdout
    if len(dump) < 1000 or b"PostgreSQL database dump" not in dump[:1000]:
        raise RuntimeError("Backup validation failed; do not migrate")
    nonce = os.urandom(12)
    header = b"pacewise-db-backup:v1\n"
    encrypted = header + nonce + AESGCM(key).encrypt(nonce, dump, header)
    with target.open("xb") as stream:
        stream.write(encrypted)
    recovered = AESGCM(key).decrypt(nonce, target.read_bytes()[len(header) + 12 :], header)
    if recovered != dump:
        raise RuntimeError("Encrypted backup round-trip failed")
    print(
        {
            "encrypted_backup": str(target),
            "sql_bytes": len(dump),
            "sha256": hashlib.sha256(recovered).hexdigest(),
            "verified": True,
        }
    )


if __name__ == "__main__":
    main()
