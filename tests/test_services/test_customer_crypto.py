import json

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import create_engine, text

from src.services.customer_crypto import EncryptedText, migrate_encrypted_columns


def test_production_cannot_disable_transport_and_cookie_protection(tmp_path):
    from src.config import Settings
    from tests.production_settings import valid_production_settings

    settings = Settings(
        **valid_production_settings(
            tmp_path,
            force_https=False,
            session_cookie_secure=False,
            private_api_required=False,
        )
    )
    assert settings.force_https and settings.session_cookie_secure and settings.private_api_required


def test_randomized_name_and_searchable_email_are_authenticated():
    names = EncryptedText("name")
    emails = EncryptedText("email", deterministic=True)
    first, second = names.process_bind_param("Sensitive name", None), names.process_bind_param("Sensitive name", None)
    assert first != second and "Sensitive" not in first
    assert names.process_result_value(first, None) == "Sensitive name"
    assert emails.process_bind_param("person@gmail.com", None) == emails.process_bind_param("person@gmail.com", None)
    with pytest.raises(InvalidTag):
        EncryptedText("different-purpose").process_result_value(first, None)


def test_migration_preserves_raw_ids_encrypted_workspace_opt_in_and_is_idempotent():
    from src.db import Base
    from src.persistence_models import UserWorkspace

    isolated = create_engine("sqlite://")
    Base.metadata.create_all(isolated)
    original = json.dumps(
        {"reminders": {"preferences": {"browserEnabled": True, "pushEnabled": True}}, "name": "Private learner"}
    )
    with isolated.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO pacewise_workspaces (user_id, state_json, version, updated_at) VALUES (5,:state,1,CURRENT_TIMESTAMP)"
            ),
            {"state": original},
        )
    assert migrate_encrypted_columns(isolated, Base.metadata) == 1
    assert migrate_encrypted_columns(isolated, Base.metadata) == 0
    with isolated.connect() as conn:
        row = conn.execute(text("SELECT user_id, state_json, push_opted_in FROM pacewise_workspaces")).first()
    assert row.user_id == 5 and row.state_json.startswith("pwenc:v1:") and row.push_opted_in
    assert UserWorkspace.state_json.type.process_result_value(row.state_json, None) == original
