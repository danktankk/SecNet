"""Read and write the .env file from within the container.

The .env must be mounted as a volume at ENV_FILE_PATH for writes to persist.
Reads always return current file state. Writes preserve comments and structure.
"""
from __future__ import annotations
import os
import re
import logging

logger = logging.getLogger(__name__)

ENV_FILE_PATH = os.environ.get("SECNET_ENV_PATH", "/app/.env")


def _parse(content: str) -> dict[str, str]:
    result = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r'^([A-Z0-9_]+)\s*=\s*(.*)$', stripped)
        if m:
            val = m.group(2).strip().strip('"').strip("'")
            result[m.group(1)] = val
    return result


def read_env() -> dict[str, str]:
    try:
        with open(ENV_FILE_PATH, "r") as f:
            return _parse(f.read())
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"Could not read .env: {e}")
        return {}


def env_file_writable() -> bool:
    if not os.path.exists(ENV_FILE_PATH):
        # Check if directory is writable (fresh install)
        return os.access(os.path.dirname(ENV_FILE_PATH) or ".", os.W_OK)
    return os.access(ENV_FILE_PATH, os.W_OK)


def update_env(updates: dict[str, str]) -> tuple[bool, str]:
    """Update or add key=value pairs in the .env file.

    Preserves comments, blank lines, and key order.
    New keys are appended at the end with a section comment.
    Returns (success, message).
    """
    if not updates:
        return True, "No changes requested"

    for key, val in updates.items():
        if not re.match(r'^[A-Z0-9_]+$', key):
            return False, f"Invalid key name '{key}' — only uppercase letters, digits, and underscores allowed"
    # Strip newlines and null bytes from all values
    updates = {k: v.replace('\n', '').replace('\r', '').replace('\0', '') for k, v in updates.items()}

    if not env_file_writable():
        return False, (
            f"Cannot write to {ENV_FILE_PATH}. "
            "Mount your .env file as a volume: '- ./.env:/app/.env' in docker-compose.yml"
        )

    try:
        lines = open(ENV_FILE_PATH, "r").readlines() if os.path.exists(ENV_FILE_PATH) else []
        pending = dict(updates)
        new_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue
            m = re.match(r'^#?\s*([A-Z0-9_]+)\s*=', stripped)
            if m:
                key = m.group(1)
                if key in pending:
                    val = pending.pop(key)
                    new_lines.append(f"{key}={val}\n")
                    continue
            new_lines.append(line)

        # Append any keys not already present
        if pending:
            if new_lines and new_lines[-1].strip():
                new_lines.append("\n")
            new_lines.append("# Added by SecNet environment scan\n")
            for k, v in pending.items():
                new_lines.append(f"{k}={v}\n")

        with open(ENV_FILE_PATH, "w") as f:
            f.writelines(new_lines)

        keys = ", ".join(updates.keys())
        logger.info(f"Updated .env: {keys}")
        return True, f"Updated {len(updates)} key(s): {keys}. Restart the container to apply."

    except Exception as e:
        logger.error(f"Failed to write .env: {e}")
        return False, f"Write failed: {e}"
