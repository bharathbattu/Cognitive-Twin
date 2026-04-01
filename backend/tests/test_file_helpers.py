from app.utils.file_helpers import safe_slug


def test_safe_slug_preserves_safe_values() -> None:
    assert safe_slug("default-session") == "default-session"
    assert safe_slug("abc_123-xyz") == "abc_123-xyz"


def test_safe_slug_prevents_collisions_for_unsafe_session_ids() -> None:
    slug_colon = safe_slug("alpha:1")
    slug_slash = safe_slug("alpha/1")

    assert slug_colon != slug_slash
    assert slug_colon.startswith("alpha-1-")
    assert slug_slash.startswith("alpha-1-")
