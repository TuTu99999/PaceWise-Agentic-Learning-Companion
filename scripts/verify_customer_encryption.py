"""Read-only runtime check: print counts, never field values or credentials."""

import json

from sqlalchemy import Text, cast, func, select

from src import persistence_models  # noqa: F401
from src.config import get_settings
from src.course_source import models  # noqa: F401
from src.course_source.db import Base as SourceBase
from src.course_source.db import engine as source_engine
from src.db import Base, engine
from src.services.customer_crypto import PREFIX, EncryptedText


def main():
    settings = get_settings()
    print(
        json.dumps(
            {
                "private_api_required": settings.private_api_required,
                "signup_enabled": settings.google_signup_enabled,
                "production": settings.app_env == "production",
            }
        )
    )
    for label, database, metadata in [
        ("pacewise", engine, Base.metadata),
        ("course_source", source_engine, SourceBase.metadata),
    ]:
        with database.connect() as connection:
            for table in metadata.sorted_tables:
                for column in table.columns:
                    if not isinstance(column.type, EncryptedText):
                        continue
                    total, encrypted = connection.execute(
                        select(
                            func.count(column),
                            func.count().filter(cast(column, Text).like(PREFIX + "%")),
                        )
                    ).one()
                    assert total == encrypted, f"Unencrypted rows in {label}.{table.name}.{column.name}"
                    print(
                        json.dumps(
                            {
                                "table": f"{label}.{table.name}",
                                "column": column.name,
                                "rows": total,
                                "encrypted": encrypted,
                            }
                        )
                    )


if __name__ == "__main__":
    main()
