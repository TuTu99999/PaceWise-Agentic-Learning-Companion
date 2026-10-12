from app.security import hash_password, verify_password


def test_password_round_trip() -> None:
    encoded = hash_password("demo123")

    assert verify_password("demo123", encoded)
    assert not verify_password("wrong-password", encoded)
