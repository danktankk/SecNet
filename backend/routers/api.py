import asyncio
from collections import defaultdict
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from services import aggregator
from services import network
from services import hosts as hosts_svc
from services import unifi
from services import chat as chat_svc
from services.data_layer import get_alerts
from services import workstations as ws_svc
from services import environment_scan as env_scan_svc
from services import env_manager
from config import settings

# ── Manual rate limiter for gate-check ───────────────────
_gate_attempts: dict[str, list[float]] = defaultdict(list)
GATE_RATE_LIMIT = 5  # max attempts
GATE_RATE_WINDOW = 60  # per 60 seconds


def _check_rate_limit(client_ip: str):
    now = time.time()
    if len(_gate_attempts) > 500:
        for ip in list(_gate_attempts.keys()):
            _gate_attempts[ip] = [t for t in _gate_attempts[ip] if now - t < GATE_RATE_WINDOW]
            if not _gate_attempts[ip]:
                del _gate_attempts[ip]
    _gate_attempts[client_ip] = [t for t in _gate_attempts[client_ip] if now - t < GATE_RATE_WINDOW]
    if len(_gate_attempts[client_ip]) >= GATE_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
    _gate_attempts[client_ip].append(now)

router = APIRouter(prefix="/api")


async def _require_gate(x_gate_token: str = Header(default="")):
    if not chat_svc.check_gate_answer(x_gate_token):
        raise HTTPException(status_code=403, detail="Gate locked")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/features")
async def features():
    def _status(enabled: bool, *required_settings: str) -> dict:
        configured = all(bool(s) for s in required_settings)
        return {"enabled": enabled and configured, "configured": configured}

    return {
        "crowdsec":   _status(settings.enable_crowdsec, settings.crowdsec_url, settings.crowdsec_api_key),
        "unifi":      _status(settings.enable_unifi, settings.unifi_url, settings.unifi_username, settings.unifi_password),
        "proxmox":    _status(settings.enable_proxmox, settings.pve1_url),
        "loki":       _status(settings.enable_loki, settings.loki_url),
        "prometheus": _status(settings.enable_prometheus, settings.prometheus_url),
        "openai":     _status(settings.enable_openai, settings.openai_api_key),
        "workstations": _status(settings.enable_workstations, settings.workstation_agent_key),
    }


@router.get("/summary")
async def summary():
    return await aggregator.get_summary()


@router.get("/decisions")
async def decisions():
    return await aggregator.get_decisions_with_geo()


@router.get("/alerts")
async def alerts(since: str = Query("1h")):
    return await get_alerts(since=since)


@router.get("/timeline")
async def timeline(range: str = Query("24h")):
    hours = 24
    if range.endswith("h"):
        try:
            hours = int(range[:-1])
        except ValueError:
            pass
    return await aggregator.get_timeline(hours)


@router.get("/logs/unifi")
async def unifi_logs(limit: int = Query(50, le=200)):
    return await aggregator.get_unifi_logs(limit)


@router.get("/logs/traefik")
async def traefik_logs(limit: int = Query(50, le=200)):
    return await aggregator.get_traefik_logs(limit)


@router.get("/logs/crowdsec")
async def crowdsec_alerts(limit: int = Query(50, le=200)):
    return await aggregator.get_crowdsec_alerts(limit)


# ── Chat ──────────────────────────────────────────────────

class ChatRequest(BaseModel):
    messages: list[dict]


@router.post("/chat")
async def chat_endpoint(req: ChatRequest, x_gate_token: str = Header(default="")):
    # Check gate server-side instead of trusting client
    session_unlocked = False
    if x_gate_token:
        session_unlocked = chat_svc.check_gate_answer(x_gate_token)

    try:
        s = await aggregator.get_summary()
        ctx = (
            f"Active Bans: {s.get('active_bans', 0)}, CF Blocks: {s.get('cf_blocks', 0)}, "
            f"Unique IPs: {s.get('unique_ips', 0)}, SSH Failures: {s.get('ssh_failures', 0)}, "
            f"Threat Level: {s.get('threat_level', 'unknown')}, Alerts: {s.get('alerts', 0)}"
        )
    except Exception:
        ctx = "Dashboard data unavailable"

    reply = await chat_svc.chat(req.messages, session_unlocked, ctx)
    return {"reply": reply}


class GateCheckRequest(BaseModel):
    answer: str


@router.post("/chat/gate-check")
async def gate_check(req: GateCheckRequest, request: Request):
    _check_rate_limit(request.client.host)
    return {"unlocked": chat_svc.check_gate_answer(req.answer)}


# ── Infrastructure (Proxmox) ──────────────────────────────

@router.get("/network/inventory")
async def network_inventory():
    return await network.get_full_inventory()


@router.post("/network/scan/{ip}", dependencies=[Depends(_require_gate)])
async def network_scan(ip: str):
    result = await network.scan_host(ip, force=True)
    return result


@router.get("/network/scan/{ip}/results")
async def network_scan_results(ip: str):
    result = await network.get_scan_results(ip)
    if result is None:
        return {"ip": ip, "ports": [], "scanned_at": None, "error": "No scan results cached"}
    return result


@router.post("/network/scan-all", dependencies=[Depends(_require_gate)])
async def network_scan_all():
    inventory = await network.get_full_inventory()
    ips = set()
    for node in inventory:
        host = node.get("url", "").replace("https://", "").replace(":8006", "")
        if host:
            ips.add(host)
    import asyncio
    results = await asyncio.gather(*[network.scan_host(ip, force=True) for ip in ips])
    return list(results)


# ── UniFi Network Health ──────────────────────────────────

@router.get("/unifi/health")
async def unifi_health():
    return await unifi.get_health()


@router.get("/unifi/devices")
async def unifi_devices():
    return await unifi.get_devices()


@router.get("/unifi/clients")
async def unifi_clients():
    return await unifi.get_clients()


@router.get("/unifi/alarms")
async def unifi_alarms():
    return await unifi.get_alarms()


# ── Infrastructure Hosts ─────────────────────────────────

@router.get("/network/hosts")
async def network_hosts():
    return await hosts_svc.get_hosts()


# ── Security Breakdown ────────────────────────────────────

@router.get("/breakdown")
async def breakdown():
    return await aggregator.get_breakdown()


@router.get("/threat-intel")
async def threat_intel():
    return await aggregator.get_threat_intel()

# ── Workstations ──────────────────────────────────────────

class WorkstationReport(BaseModel):
    hostname: str
    ip: str = ""
    mac: str = ""
    os: str = ""
    domain: str = ""
    user: str = ""
    session_start: int = 0
    cpu: int = 0
    ram: int = 0
    disk: int = 0
    processes: list[dict] = []
    events: list[dict] = []


@router.post("/workstations/report")
async def workstation_report(report: WorkstationReport, x_agent_key: str = Header(default="")):
    if not settings.workstation_agent_key or x_agent_key != settings.workstation_agent_key:
        raise HTTPException(status_code=403, detail="Invalid agent key")
    ws_svc.upsert_workstation(report.model_dump())
    return {"status": "ok"}


@router.get("/workstations")
async def workstations():
    return ws_svc.get_all()


# ── Environment Discovery ─────────────────────────────────

_scan_lock = asyncio.Lock()
_last_scan: dict | None = None


class ConfigUpdateRequest(BaseModel):
    updates: dict[str, str]


@router.post("/discovery/scan", dependencies=[Depends(_require_gate)])
async def discovery_scan(include_subnet: bool = True):
    global _last_scan
    if _scan_lock.locked():
        raise HTTPException(status_code=409, detail="Scan already in progress")
    async with _scan_lock:
        result = await env_scan_svc.run_scan(include_subnet=include_subnet)
        _last_scan = result
    return {"status": "complete", **result}


@router.get("/discovery/last", dependencies=[Depends(_require_gate)])
async def discovery_last():
    if _last_scan is None:
        return {"status": "none", "message": "No scan has been run yet"}
    return {"status": "complete", **_last_scan}


@router.post("/config/update", dependencies=[Depends(_require_gate)])
async def config_update(req: ConfigUpdateRequest):
    ok, msg = env_manager.update_env(req.updates)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg, "writable": env_manager.env_file_writable()}


@router.get("/config/status", dependencies=[Depends(_require_gate)])
async def config_status():
    return {
        "writable": env_manager.env_file_writable(),
        "env_path": env_manager.ENV_FILE_PATH,
        "current": env_manager.read_env(),
    }
