"""Security gate — password verification for protected endpoints."""
from __future__ import annotations
import hmac
from config import settings


def check_gate_answer(answer: str) -> bool:
    if not settings.security_gate_code:
        return False
    return hmac.compare_digest(answer.strip(), settings.security_gate_code)
