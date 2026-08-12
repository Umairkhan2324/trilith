"""API-key auth: the mechanism that makes a tenant_id unforgeable."""

import pytest

from core.auth import AuthEnforcer, AuthError, parse_authorization
from core.runtime import build_runtime


@pytest.fixture
def rt():
    return build_runtime(":memory:")


def test_auth_is_off_until_a_key_exists(rt):
    """A fresh install stays open, so the local quickstart needs no credentials."""
    assert rt.auth.enabled is False

    principal = rt.auth.resolve(None, tenant_id="acme")
    assert principal.tenant_id == "acme"


def test_minting_a_key_turns_auth_on(rt):
    rt.keys.create(tenant_id="acme")
    assert rt.auth.enabled is True

    with pytest.raises(AuthError, match="Missing API key"):
        rt.auth.resolve(None, tenant_id="acme")


def test_require_auth_flag_enforces_before_any_key_exists(rt):
    enforcer = AuthEnforcer(rt.keys, require_auth=True)
    assert enforcer.enabled is True
    with pytest.raises(AuthError):
        enforcer.resolve(None)


def test_key_pins_the_tenant_and_body_cannot_override_it(rt):
    raw, _ = rt.keys.create(tenant_id="acme")

    # The caller asks for globex; the key says acme. The key wins.
    principal = rt.auth.resolve(f"Bearer {raw}", tenant_id="globex")
    assert principal.tenant_id == "acme"


def test_key_can_pin_an_owner(rt):
    raw, _ = rt.keys.create(tenant_id="acme", owner_id="alice")

    principal = rt.auth.resolve(f"Bearer {raw}", owner_id="bob")
    assert principal.owner_id == "alice"


def test_unpinned_key_accepts_a_caller_supplied_owner(rt):
    raw, _ = rt.keys.create(tenant_id="acme")

    principal = rt.auth.resolve(f"Bearer {raw}", owner_id="bob", session_id="s1")
    assert (principal.tenant_id, principal.owner_id, principal.session_id) == (
        "acme",
        "bob",
        "s1",
    )


def test_invalid_and_revoked_keys_are_rejected(rt):
    raw, record = rt.keys.create(tenant_id="acme")

    with pytest.raises(AuthError, match="Invalid API key"):
        rt.auth.resolve("Bearer tri_not-a-real-key")

    assert rt.keys.revoke(record.fingerprint) == 1
    with pytest.raises(AuthError, match="revoked"):
        rt.auth.resolve(f"Bearer {raw}")


def test_raw_key_is_never_stored(rt):
    raw, record = rt.keys.create(tenant_id="acme")

    cursor = rt.keys._conn.cursor()
    cursor.execute("SELECT key_hash, fingerprint FROM api_keys")
    key_hash, fingerprint = cursor.fetchone()

    assert raw not in key_hash
    assert raw not in fingerprint
    assert record.fingerprint == fingerprint
    assert rt.keys.lookup(raw) is not None


def test_listing_keys_does_not_expose_secrets(rt):
    raw, _ = rt.keys.create(tenant_id="acme", name="prod")
    records = rt.keys.list(tenant_id="acme")

    assert len(records) == 1
    assert raw not in str(records[0])


def test_revoking_the_last_key_does_not_reopen_the_instance(rt):
    """Enabling auth is a one-way door — revocation must never unlock the server."""
    _, record = rt.keys.create(tenant_id="acme")
    assert rt.auth.enabled is True

    rt.keys.revoke(record.fingerprint)
    assert rt.auth.enabled is True
    with pytest.raises(AuthError):
        rt.auth.resolve(None)


@pytest.mark.parametrize(
    "header,expected",
    [
        ("Bearer tri_abc", "tri_abc"),
        ("bearer tri_abc", "tri_abc"),
        ("ApiKey tri_abc", "tri_abc"),
        ("tri_abc", "tri_abc"),
        ("  Bearer   tri_abc  ", "tri_abc"),
        ("", None),
        (None, None),
    ],
)
def test_authorization_header_parsing(header, expected):
    assert parse_authorization(header) == expected
