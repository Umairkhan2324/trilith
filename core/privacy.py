import re
import time
from typing import List, Tuple
from core.proto.trilith_pb2 import ContextItem, Scope
from google.protobuf.timestamp_pb2 import Timestamp

class PolicyEngine:
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

    def filter(self, candidates: List[ContextItem], requester_scope: str) -> Tuple[List[ContextItem], List[Tuple[ContextItem, str]]]:
        """Runs security policy check over candidates.

        Returns:
            allowed: List of ContextItems with PII matches redacted.
            denied: List of tuples (ContextItem, reason_string).
        """
        allowed = []
        denied = []
        
        current_time = time.time()
        
        for item in candidates:
            # 1. Expiry Check
            if item.HasField("expires_at"):
                exp_time = item.expires_at.seconds + (item.expires_at.nanos / 1e9)
                if current_time >= exp_time:
                    denied.append((item, f"Item expired at timestamp {item.expires_at.seconds}"))
                    continue
            
            # 2. Scope Matching Check
            # Convert item's Scope enum to string name (e.g., 'GLOBAL', 'USER')
            try:
                item_scope_str = Scope.Name(item.scope)
            except ValueError:
                item_scope_str = "SCOPE_UNSPECIFIED"

            # Rules:
            # - GLOBAL items are visible to all.
            # - Otherwise item_scope must match (case-insensitive) the requester_scope.
            if item_scope_str != "GLOBAL":
                if not requester_scope or item_scope_str.lower() != requester_scope.lower():
                    denied.append((item, f"Scope mismatch: item scope is '{item_scope_str}' but requester is '{requester_scope}'"))
                    continue
            
            # 3. PII Redaction
            # Create a copy so we do not mutate the query cache or original store references directly.
            # We copy key fields to a new ContextItem
            redacted_item = ContextItem()
            redacted_item.CopyFrom(item)
            redacted_item.content = self.redact(item.content)
            
            allowed.append(redacted_item)

        return allowed, denied
