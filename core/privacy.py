import re
import time
from typing import List, Tuple, Union

from core.identity import Principal, normalize_tenant
from core.proto.trilith_pb2 import ContextItem, Scope


class PolicyEngine:
    """Decides which candidate items a principal may see, and redacts PII.

    Checks run in this order — the cheapest and most absolute first:

        1. Expiry        — past `expires_at` is gone for everyone
        2. Tenant        — hard boundary; only Scope.GLOBAL crosses it
        3. Scope kind    — TENANT / USER / SESSION narrowing inside the tenant
        4. PII redaction — applied to a copy, never to the stored item
    """

    def __init__(self):
        # Regex PII patterns
        # 1. Email pattern
        self.email_regex = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
        # 2. Phone numbers (standard formats)
        self.phone_regex = re.compile(r'\b(?:\+?\d{1,3}[- ]?)?\(?\d{3}\)?[- ]?\d{3}[- ]?\d{4}\b')
        # 3. National ID (e.g. US SSN format xxx-xx-xxxx)
        self.national_id_regex = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')

    def redact(self, text: str) -> str:
        """Helper to redact PII in place using regular expressions."""
        if not text:
            return ""
        text = self.email_regex.sub("[REDACTED_EMAIL]", text)
        text = self.phone_regex.sub("[REDACTED_PHONE]", text)
        text = self.national_id_regex.sub("[REDACTED_ID]", text)
        return text

    @staticmethod
    def _scope_name(item: ContextItem) -> str:
        try:
            return Scope.Name(item.scope)
        except ValueError:
            return "SCOPE_UNSPECIFIED"

    def _check_visibility(
        self,
        item: ContextItem,
        principal: Principal,
    ) -> Tuple[bool, str]:
        """Return (allowed, reason_if_denied) for one item."""
        scope_name = self._scope_name(item)

        # GLOBAL is deliberately cross-tenant: shared system knowledge.
        if scope_name == "GLOBAL":
            return True, ""

        # Hard tenant boundary. Everything below is same-tenant only.
        item_tenant = normalize_tenant(item.tenant_id)
        if item_tenant != principal.tenant_id:
            return False, (
                f"Tenant isolation: item belongs to tenant '{item_tenant}', "
                f"requester is '{principal.tenant_id}'"
            )

        if scope_name == "TENANT":
            return True, ""

        if scope_name == "USER":
            if item.owner_id:
                if item.owner_id == principal.owner_id:
                    return True, ""
                return False, (
                    f"Owner mismatch: item belongs to owner '{item.owner_id}', "
                    f"requester is '{principal.owner_id or '(none)'}'"
                )
            # The item names no owner, so there is no one to isolate it from.
            # It degrades to tenant visibility for any identified caller.
            # (Chiefly v0.1 rows, which predate owner_id.)
            return self._unowned(scope_name, principal)

        if scope_name == "SESSION":
            if item.session_id:
                if item.session_id == principal.session_id:
                    return True, ""
                return False, (
                    f"Session mismatch: item belongs to session '{item.session_id}', "
                    f"requester is '{principal.session_id or '(none)'}'"
                )
            return self._unowned(scope_name, principal)

        return False, f"Unsupported item scope '{scope_name}'"

    def _unowned(self, scope_name: str, principal: Principal) -> Tuple[bool, str]:
        """Decide an item that carries a narrowing scope but no identity to narrow by."""
        if principal.owner_id or principal.session_id:
            return True, ""
        # Anonymous caller: fall back to v0.1 scope-name matching.
        return self._legacy_match(scope_name, principal)

    @staticmethod
    def _legacy_match(scope_name: str, principal: Principal) -> Tuple[bool, str]:
        """v0.1 behaviour: the requester's scope *name* had to equal the item's.

        Reached only when neither side carries the identity the scope needs —
        i.e. pre-multi-tenancy data queried by a pre-multi-tenancy caller.
        """
        if principal.legacy_scope and scope_name.lower() == principal.legacy_scope.lower():
            return True, ""
        return False, (
            f"Scope mismatch: item scope is '{scope_name}' but requester is "
            f"'{principal.legacy_scope}'"
        )

    def filter(
        self,
        candidates: List[ContextItem],
        requester: Union[Principal, str, None] = None,
        requester_scope: Union[str, None] = None,
    ) -> Tuple[List[ContextItem], List[Tuple[ContextItem, str]]]:
        """Run the security policy over candidates.

        `requester` accepts a Principal, or a bare v0.1 scope string. The
        `requester_scope=` keyword is kept so existing callers still work.

        Returns:
            allowed: ContextItems (copies) with PII redacted.
            denied: (ContextItem, reason) pairs.
        """
        if requester is None:
            requester = requester_scope if requester_scope is not None else ""
        if isinstance(requester, str):
            principal = Principal(legacy_scope=requester)
        else:
            principal = requester

        allowed: List[ContextItem] = []
        denied: List[Tuple[ContextItem, str]] = []

        current_time = time.time()

        for item in candidates:
            # 1. Expiry check
            if item.HasField("expires_at"):
                exp_time = item.expires_at.seconds + (item.expires_at.nanos / 1e9)
                if current_time >= exp_time:
                    denied.append((item, f"Item expired at timestamp {item.expires_at.seconds}"))
                    continue

            # 2 + 3. Tenant isolation, then scope-kind narrowing
            visible, reason = self._check_visibility(item, principal)
            if not visible:
                denied.append((item, reason))
                continue

            # 4. PII redaction on a copy — never mutate stored/cached items.
            redacted_item = ContextItem()
            redacted_item.CopyFrom(item)
            redacted_item.content = self.redact(item.content)

            allowed.append(redacted_item)

        return allowed, denied
