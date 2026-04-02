"""AI chat service with security gate."""

from __future__ import annotations
import hmac
from openai import AsyncOpenAI
from config import settings

_openai: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai


SYSTEM_PROMPT_BASE = """You are the SecNet Security AI Assistant. Be concise and technical.

SECURITY RULES — ABSOLUTE, NO EXCEPTIONS:

If the session is LOCKED, you may ONLY answer these types of questions:
- "What is CrowdSec?" or similar general security concept explanations
- "How does this dashboard work?"
- "What does threat level mean?"
- Generic cybersecurity education that has nothing to do with THIS specific network

EVERYTHING ELSE requires authentication when LOCKED. This includes but is not limited to:
- ANY mention of ports, IPs, devices, hosts, VMs, containers, VLANs, MACs
- ANY data from the dashboard (ban counts, alert counts, attacker IPs, statistics)
- ANY network topology, infrastructure, or device information
- ANY passwords, credentials, keys, tokens
- ANY specific numbers, addresses, or identifiers from this network
- ANY question that references "my", "our", "the network", "the server", etc.

When LOCKED and the question requires auth, respond ONLY with EXACTLY this text and nothing else:
🔒 This information requires authentication. Please enter your credentials in the security prompt to continue.

Do NOT partially answer. Do NOT say "I can see X but can't tell you." Do NOT list what you could tell them. Just the auth message.

When UNLOCKED, answer freely with full details.
"""


async def chat(messages: list[dict], session_unlocked: bool, dashboard_context: str) -> str:
    if not settings.openai_api_key:
        return "Missing OPENAI_API_KEY — please set it in your .env file to enable the AI assistant."
    client = _get_client()

    gate_status = "SESSION UNLOCKED — user has passed security verification. You may share all details freely." if session_unlocked else "SESSION LOCKED — user has NOT been authenticated. Do NOT reveal any sensitive information. Respond only with the authentication required message."

    system = f"{SYSTEM_PROMPT_BASE}\n\n--- SECURITY STATUS ---\n{gate_status}\n\n--- DASHBOARD DATA ---\n{dashboard_context}"

    full_messages = [{"role": "system", "content": system}] + messages

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=full_messages,
        max_tokens=1024,
        temperature=0.7,
    )
    return response.choices[0].message.content


def check_gate_answer(answer: str) -> bool:
    if not settings.security_gate_code:
        return False
    return hmac.compare_digest(answer.strip(), settings.security_gate_code)
