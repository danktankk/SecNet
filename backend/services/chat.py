"""AI chat service with security gate and tool calling."""

from __future__ import annotations
import hmac
import json
import logging
from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)

_openai: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai


ALLOWED_AI_WRITE_KEYS = {
    "PROMETHEUS_URL", "LOKI_URL", "CROWDSEC_URL", "CROWDSEC_API_KEY",
    "CROWDSEC_MACHINE_ID", "CROWDSEC_MACHINE_PASSWORD",
    "UNIFI_URL", "UNIFI_USERNAME", "UNIFI_PASSWORD",
    "PVE1_URL", "PVE1_TOKEN", "PVE2_URL", "PVE2_TOKEN", "PVE3_URL", "PVE3_TOKEN",
    "WORKSTATION_AGENT_KEY", "OPENAI_API_KEY", "OPENAI_MODEL",
    "GEOIP_PROVIDER", "GEOIP_RATE_LIMIT", "POLL_INTERVAL",
}

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

ENVIRONMENT DISCOVERY CAPABILITIES (only available when UNLOCKED):
You can scan the user's environment to discover integrations they may want to add.
Use the run_environment_scan tool when the user asks to scan, discover integrations, or check what's available.
Use the update_config tool when the user confirms they want to save values to their .env.

When presenting discovery results:
- Group findings clearly: what's already configured, what was found, what wasn't found
- For each found service, explain what it adds to the dashboard
- Ask before writing to config — confirm the values look right
- After writing config, remind the user to restart the container to apply changes
- If config writing fails (not mounted), explain exactly what volume line to add to docker-compose.yml
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_environment_scan",
            "description": "Scan the local environment to discover services and integrations the user may want to add. Checks current config state, probes the network gateway for known devices (FritzBox, UniFi, pfSense, Proxmox, Aruba), and sweeps the subnet for running services (Prometheus, Loki, Grafana, CrowdSec, etc). Subnet sweep may take 30-60 seconds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_subnet": {
                        "type": "boolean",
                        "description": "Whether to run the subnet sweep (slower, ~30-60s). Default true. Set false for a quick gateway-only scan.",
                        "default": True,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_config",
            "description": "Write key=value pairs to the .env configuration file. Only call this after the user has explicitly confirmed the values they want to save. Always show the user what will be written before calling this tool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "object",
                        "description": "Dictionary of .env key names to values to write. Example: {\"PROMETHEUS_URL\": \"http://192.168.1.10:9090\"}",
                        "additionalProperties": {"type": "string"},
                    }
                },
                "required": ["updates"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_config_status",
            "description": "Get the current configuration status — what's configured, what's missing, and whether the .env file is writable from within the container.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


async def _execute_tool(name: str, args: dict) -> str:
    """Execute a tool call and return the result as a string."""
    from services import environment_scan as env_scan_svc
    from services import env_manager

    if name == "run_environment_scan":
        include_subnet = args.get("include_subnet", True)
        try:
            result = await env_scan_svc.run_scan_locked(include_subnet=include_subnet)
            return json.dumps(result, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    if name == "update_config":
        updates = args.get("updates", {})
        if not updates:
            return json.dumps({"error": "No updates provided"})
        blocked = [k for k in updates if k not in ALLOWED_AI_WRITE_KEYS]
        if blocked:
            return json.dumps({"error": f"Not allowed to write: {blocked}. Only integration config keys are permitted."})
        ok, msg = env_manager.update_env(updates)
        return json.dumps({"success": ok, "message": msg})

    if name == "get_config_status":
        return json.dumps({
            "writable": env_manager.env_file_writable(),
            "env_path": env_manager.ENV_FILE_PATH,
            "configured_keys": list(env_manager.read_env().keys()),
        })

    return json.dumps({"error": f"Unknown tool: {name}"})


async def chat(messages: list[dict], session_unlocked: bool, dashboard_context: str) -> str:
    if not settings.openai_api_key:
        return "Missing OPENAI_API_KEY — please set it in your .env file to enable the AI assistant."
    client = _get_client()

    gate_status = (
        "SESSION UNLOCKED — user has passed security verification. You may share all details freely."
        if session_unlocked else
        "SESSION LOCKED — user has NOT been authenticated. Do NOT reveal any sensitive information. Respond only with the authentication required message."
    )

    system = (
        f"{SYSTEM_PROMPT_BASE}\n\n"
        f"--- SECURITY STATUS ---\n{gate_status}\n\n"
        f"--- DASHBOARD DATA ---\n{dashboard_context}"
    )

    full_messages = [{"role": "system", "content": system}] + messages

    # Only offer tools when session is unlocked
    tools = TOOLS if session_unlocked else None

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=full_messages,
        max_tokens=2048,
        temperature=0.7,
        tools=tools,
        tool_choice="auto" if tools else None,
    )

    msg = response.choices[0].message

    # No tool calls — return content directly
    if not msg.tool_calls:
        return msg.content

    # Execute tool calls
    tool_results = []
    for tc in msg.tool_calls:
        try:
            args = json.loads(tc.function.arguments)
        except Exception:
            args = {}
        logger.info(f"Tool call: {tc.function.name}({args})")
        result = await _execute_tool(tc.function.name, args)
        tool_results.append({
            "tool_call_id": tc.id,
            "role": "tool",
            "content": result,
        })

    # Second pass with tool results
    assistant_msg = msg.model_dump(exclude_none=True)
    full_messages = [*full_messages, assistant_msg, *tool_results]

    followup = await client.chat.completions.create(
        model=settings.openai_model,
        messages=full_messages,
        max_tokens=2048,
        temperature=0.7,
    )
    return followup.choices[0].message.content or ""


def check_gate_answer(answer: str) -> bool:
    if not settings.security_gate_code:
        return False
    return hmac.compare_digest(answer.strip(), settings.security_gate_code)
